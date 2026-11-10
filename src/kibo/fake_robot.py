"""假機器人：在沒有模擬器的電腦上把整場任務跑完。

它不是物理模擬：移動秒數直接用 `kibo.motion` 的模型算（可以乘一個 slowdown 假裝比較慢），
到點有一點誤差、偶爾失敗，外加一個照官方 judge.py 判定等級的假裁判。
用途是比較策略（例如時間預算的參數）與測試流程不卡死；
分數只能相對比較，不能拿來預測真實成績。
"""

import random
from typing import List, NamedTuple, Optional

from kibo.checkpoints import CheckpointSet, parse_checkpoints
from kibo.ctl_result import MOVE_ABORTED, MOVE_SUCCESS, MOVE_TIMEOUT
from kibo.field import START_POSE
from kibo.geometry import Pose, Quat, Vec3, add, axis_angle_quat, normalize, quat_mul, rotate
from kibo.judge import judge
from kibo.mission import Robot
from kibo.motion import Speeds, leg_seconds
from kibo.navlog import NavLog
from kibo.scoring import DEFAULT_SCORING, Scoring
from kibo.vision import expected_marker_in_body


class FakeRobotConfig(NamedTuple):
    speeds: Speeds = Speeds()  # 真實的節奏；slowdown 設成 2 就是「比模型慢一倍的機器人」
    move_overhead_sec: float = 0.0  # 每次移動額外多花的秒數（模型沒算到的）
    position_noise_m: float = 0.01  # 到點後的位置誤差（標準差）；模擬器實測約 1 cm
    attitude_noise_deg: float = 1.0  # 到點後的姿態誤差（標準差）；模擬器實測約 1°
    nav_jitter_m: float = 0.005  # 每次讀取位置的抖動
    move_fail_prob: float = 0.0
    checkpoints_fail_times: int = 0  # 前幾次 get_checkpoints 故意失敗
    notify_sec: float = 0.3  # 一次通過通知來回的時間
    # 移動回報成功之前，機器人已經在目標上停了幾秒（這段會留在導航紀錄裡）。模擬器實測約 1.5 秒；
    # 預設 0 = 沒有尾段紀錄，任務邏輯要自己等滿 1 秒。
    settled_before_return_sec: float = 0.0
    scoring: Scoring = DEFAULT_SCORING
    start_pose: Pose = START_POSE
    camera: bool = False  # 開了才會回 marker_in_body
    vision_noise_m: float = 0.005  # 相機算出的 marker 位置誤差（標準差）


DEFAULT_FAKE = FakeRobotConfig()

# 本機「資格賽」（simulate、tune）用的數字，兩邊共用：
CAMERA_FIX_MAX_M = 0.3  # 開相機修正的實驗時，修正量的上限（公尺）
MEASURED_SETTLED_BEFORE_RETURN_SEC = 1.5  # 模擬器實測：action 回報成功前已經停了約 1.5 秒


def fake_config(
    noise_m: float, fail_prob: float, slowdown: float, camera: bool = False
) -> FakeRobotConfig:
    """命令列參數 -> 假機器人的設定；其餘用實測值。"""
    base = FakeRobotConfig()
    return base._replace(
        position_noise_m=noise_m,
        move_fail_prob=fail_prob,
        speeds=base.speeds._replace(slowdown=slowdown),
        settled_before_return_sec=MEASURED_SETTLED_BEFORE_RETURN_SEC,
        camera=camera,
    )


def _random_rotation(rng: random.Random, sigma_deg: float) -> Quat:
    axis = normalize((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
    return axis_angle_quat(axis, rng.gauss(0, sigma_deg))


class FakeRobot(Robot):
    def __init__(
        self,
        checkpoints_message: str,
        config: FakeRobotConfig = DEFAULT_FAKE,
        seed: int = 0,
    ) -> None:
        self.cfg = config
        self.rng = random.Random(seed)
        self.message = checkpoints_message
        self.checkpoints: CheckpointSet = parse_checkpoints(checkpoints_message)
        self.t = 0.0
        self.true_pose = config.start_pose
        self.started = False
        self.finished_at: Optional[float] = None
        self.passed_levels: List[int] = []
        self.passed_ids: List[int] = []
        self.judged_ids: List[int] = []  # 已經被判過的點（過或沒過都算）
        self.goal_reached = False
        self.move_calls = 0
        self.relative_calls = 0
        self.checkpoints_calls = 0
        self.logs: List[str] = []
        self.stop = False
        self.navlog = NavLog()  # 與真的節點同一種導航紀錄

    # ---- Robot 介面 ----
    def now(self) -> float:
        return self.t

    def sleep(self, sec: float) -> None:
        self.t += sec

    def pose(self) -> Optional[Pose]:
        jitter = tuple(self.rng.gauss(0, self.cfg.nav_jitter_m) for _ in range(3))
        return Pose(
            add(self.true_pose.position, (jitter[0], jitter[1], jitter[2])),
            self.true_pose.orientation,
            stamp=self.t,
        )

    def move_to(self, target: Pose, timeout_sec: float) -> str:
        self.move_calls += 1
        duration = self.cfg.move_overhead_sec + leg_seconds(
            self.true_pose.position,
            self.true_pose.orientation,
            target.position,
            target.orientation,
            self.cfg.speeds,
        )
        if duration > timeout_sec:
            self.t += timeout_sec
            return MOVE_TIMEOUT
        if self.rng.random() < self.cfg.move_fail_prob:
            self.t += duration / 2.0
            return MOVE_ABORTED
        self.t += duration
        noise: Vec3 = (
            self.rng.gauss(0, self.cfg.position_noise_m),
            self.rng.gauss(0, self.cfg.position_noise_m),
            self.rng.gauss(0, self.cfg.position_noise_m),
        )
        wobble = _random_rotation(self.rng, self.cfg.attitude_noise_deg)
        self.true_pose = Pose(add(target.position, noise), quat_mul(target.orientation, wobble))
        self._record_tail()
        return MOVE_SUCCESS

    def _record_tail(self) -> None:
        """把「回報成功前已經停在這裡的那幾秒」寫進導航紀錄，每 0.05 秒一筆。"""
        steps = int(round(self.cfg.settled_before_return_sec / 0.05))
        if steps <= 0:
            return
        for k in range(steps, -1, -1):
            stamp = self.t - 0.05 * k
            self.navlog.add(Pose(self.true_pose.position, self.true_pose.orientation, stamp))

    def recent_poses(self, seconds: float) -> List[Pose]:
        return self.navlog.recent(self.t, seconds)

    def marker_in_body(self, marker_id: int) -> Optional[Vec3]:
        """假相機：由真實姿態反推 marker 在機體座標系的位置，加一點雜訊。"""
        if not self.cfg.camera:
            return None
        marker = self.checkpoints.by_id(marker_id).marker_position
        truth = expected_marker_in_body(self.true_pose.position, self.true_pose.orientation, marker)
        return add(truth, tuple(self.rng.gauss(0, self.cfg.vision_noise_m) for _ in range(3)))  # type: ignore[arg-type]

    def move_relative(self, delta: Vec3, timeout_sec: float) -> str:
        self.relative_calls += 1
        here = self.true_pose
        there = add(here.position, rotate(here.orientation, delta))
        self.t += self.cfg.move_overhead_sec + leg_seconds(
            here.position, here.orientation, there, here.orientation, self.cfg.speeds
        )
        self.true_pose = Pose(there, here.orientation)
        return MOVE_SUCCESS

    def mission_start(self) -> bool:
        self.started = True
        return True

    def get_checkpoints_message(self) -> Optional[str]:
        self.checkpoints_calls += 1
        if self.checkpoints_calls <= self.cfg.checkpoints_fail_times:
            return None
        return self.message

    def notify_checkpoint(self, checkpoint_id: int) -> bool:
        """假裁判，照官方 judge.py：通知一律被「接受」（回 True 不代表通過），
        而且**每個點只判第一次**，沒過也不能重來；判定用通知當下的真實姿態。"""
        self.t += self.cfg.notify_sec
        if not self.started or self.finished_at is not None:
            return True  # 任務開始前、完成回報後的通知，官方只記一行警告
        if checkpoint_id in self.judged_ids:
            return True  # 官方只記一行 "already processed"
        self.judged_ids.append(checkpoint_id)
        if checkpoint_id not in [cp.id for cp in self.checkpoints.checkpoints]:
            return True  # 不存在的 id：官方記成「判過、沒過」
        result = judge(self.true_pose, self.checkpoints.by_id(checkpoint_id))
        if result.passed:
            self.passed_ids.append(checkpoint_id)
            self.passed_levels.append(result.level)
        return True

    def mission_finish(self) -> bool:
        """官方的完成回報：Goal 點先前通過就算到達；否則用當下姿態再判一次，
        通過的話 Goal 點也補記為通過（即使先前那次通知沒過）。"""
        self.finished_at = self.t
        goal_id = self.checkpoints.goal_id
        if goal_id in self.passed_ids:
            self.goal_reached = True
        else:
            result = judge(self.true_pose, self.checkpoints.goal)
            self.goal_reached = result.passed
            if result.passed:
                self.passed_ids.append(goal_id)
                self.passed_levels.append(result.level)
        return True

    def stop_requested(self) -> bool:
        return self.stop

    def log(self, message: str) -> None:
        self.logs.append(message)

    # ---- 假裁判的結算 ----
    def remaining_at_finish(self) -> float:
        if self.finished_at is None:
            return 0.0
        return max(0.0, self.cfg.scoring.time_limit_sec - self.finished_at)

    def score(self, scoring: Optional[Scoring] = None) -> float:
        """假分數。不給 scoring 就用設定裡的；給 `kibo.scoring.WORLDS` 的某一個可看其他世界。"""
        rules = scoring or self.cfg.scoring
        goal = self.goal_reached
        late = self.finished_at is None or self.finished_at > rules.time_limit_sec
        all_passed = len(self.passed_ids) == len(self.checkpoints.checkpoints)
        return rules.total(self.passed_levels, goal, self.remaining_at_finish(), all_passed, late)
