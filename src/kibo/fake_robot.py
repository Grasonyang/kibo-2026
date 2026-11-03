"""假機器人：在沒有模擬器的電腦上把整場任務跑完。

它不是物理模擬，只是「等速移動、到點有誤差、偶爾失敗」的簡化模型，外加一個
照規則書判定等級的假裁判。用途是比較策略（例如時間預算的參數）與測試流程不卡死；
分數只能相對比較，不能拿來預測真實成績。
"""

import math
import random
from typing import List, NamedTuple, Optional

from kibo.checkpoints import CheckpointSet, parse_checkpoints
from kibo.geometry import Quat, Vec3, add, normalize, quat_mul, quat_normalize
from kibo.judge import Pose, judge
from kibo.mission import MOVE_ABORTED, MOVE_SUCCESS, MOVE_TIMEOUT, Robot
from kibo.planner import Speeds, leg_seconds
from kibo.scoring import DEFAULT_SCORING, Scoring


class FakeRobotConfig(NamedTuple):
    speeds: Speeds = Speeds(linear_mps=0.12, angular_dps=20.0)  # 真實速度，可與規劃假設不同
    move_overhead_sec: float = 3.0  # 每次移動的起停時間
    position_noise_m: float = 0.03  # 到點後的位置誤差（標準差）
    attitude_noise_deg: float = 2.0  # 到點後的姿態誤差（標準差）
    nav_jitter_m: float = 0.005  # 每次讀取位置的抖動
    move_fail_prob: float = 0.0
    checkpoints_fail_times: int = 0  # 前幾次 get_checkpoints 故意失敗
    scoring: Scoring = DEFAULT_SCORING
    start_pose: Pose = Pose((0.2, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))


DEFAULT_FAKE = FakeRobotConfig()


def _random_rotation(rng: random.Random, sigma_deg: float) -> Quat:
    axis = normalize((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
    half = math.radians(rng.gauss(0, sigma_deg)) / 2.0
    s = math.sin(half)
    return quat_normalize((axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half)))


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
        self.move_calls = 0
        self.checkpoints_calls = 0
        self.logs: List[str] = []
        self.stop = False

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
        """假裁判：照真實姿態判定；同一點只給一次分。"""
        if checkpoint_id in self.passed_ids:
            return False
        result = judge(self.true_pose, self.checkpoints.by_id(checkpoint_id))
        self.t += 1.0  # 規則：維持 1 秒
        if not result.passed:
            return False
        self.passed_ids.append(checkpoint_id)
        self.passed_levels.append(result.level)
        return True

    def mission_finish(self) -> bool:
        self.finished_at = self.t
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

    def score(self) -> float:
        goal = self.checkpoints.goal_id in self.passed_ids
        if self.finished_at is None or self.finished_at > self.cfg.scoring.time_limit_sec:
            return 0.0  # 沒在時限內完成回報
        return self.cfg.scoring.total(self.passed_levels, goal, self.remaining_at_finish())
