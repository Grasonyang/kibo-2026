"""假機器人：在沒有模擬器的電腦上把整場任務跑完。

它不是物理模擬：移動秒數直接用 `kibo.motion` 的模型算（可以乘一個 slowdown 假裝比較慢），
到點有一點誤差、偶爾失敗。過不過、幾分由假裁判（`kibo_lab.fake_judge`）記，在 `robot.judge`。
用途是比較策略（例如時間預算的參數）與測試流程不卡死；
分數只能相對比較，不能拿來預測真實成績。

測試要不同的機器人時，先看 `FakeRobotConfig` 有沒有現成的欄位（到點偏移、還沒轉完的滾轉、
移動一律失敗）；沒有才寫子類別，而且只覆寫 `Robot` 介面的方法、用 `now()` 與 `sleep()` 動時鐘，
不直接改這裡的內部狀態（要讀真實姿態用 `truth()`，要中途換設定用 `reconfigure()`）。
"""

import random
from typing import Dict, List, NamedTuple, Optional, Tuple

from kibo.checkpoints import CheckpointSet, parse_checkpoints
from kibo.ctl_result import MOVE_ABORTED, MOVE_SUCCESS, MOVE_TIMEOUT
from kibo.field import START_POSE
from kibo.geometry import (
    FORWARD,
    Pose,
    Quat,
    Vec3,
    add,
    axis_angle_quat,
    normalize,
    quat_mul,
    rotate,
)
from kibo.mission import Robot
from kibo.motion import Speeds, leg_seconds
from kibo.navlog import NavLog
from kibo.vision import expected_marker_in_body
from kibo_lab.fake_judge import FakeJudge
from kibo_lab.scoring import DEFAULT_SCORING, Scoring


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
    # 到點偏移：絕對移動成功後，停在目標旁邊這麼遠的地方（公尺，目標姿態的機體座標）。
    # 第 k 次到同一個目標用第 k 個，用完了就一直用最後一個；空的就是不偏。
    # 例：`((0, 0.15, 0),)` 每次都偏 15 cm；`((0, 0.15, 0), (0, 0, 0))` 第一次偏、再去一次就準。
    arrival_offsets_m: Tuple[Vec3, ...] = ()
    # 還沒轉完：絕對移動回報成功後的 residual_roll_sec 秒內，機體繞前方軸還差 residual_roll_deg 度，
    # 之後才到位（真的控制器在姿態進到 0.5 rad 以內就回報成功，不等轉完）。導航與假裁判都看得到。
    # 兩欄要一起給：只給角度、秒數是 0，等於沒有。
    residual_roll_deg: float = 0.0
    residual_roll_sec: float = 0.0
    # 不是空字串的話，每次絕對移動都不動、直接回這個結果（kibo.ctl_result 的 MOVE_*）；
    # MOVE_TIMEOUT 會花掉整個逾時，其他的不花時間。
    move_always: str = ""


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
        self.judge = FakeJudge(self.checkpoints, config.scoring)
        self._t = 0.0  # 時鐘從 0 起算；任務一開始就呼叫 mission_start，所以也是任務時間
        self._true_pose = config.start_pose  # 轉完之後會停在的姿態；現在真正的姿態是 truth()
        self._turning_until = 0.0
        self._arrivals: Dict[Vec3, int] = {}  # 目標位置 -> 成功到過幾次
        self.move_calls = 0
        self.relative_calls = 0
        self.checkpoints_calls = 0
        self.logs: List[str] = []
        self.stop = False
        self.navlog = NavLog()  # 與真的節點同一種導航紀錄

    def truth(self) -> Pose:
        """機器人現在真正的姿態：還沒轉完的那幾秒多一個滾轉。假裁判看的是這個；測試可以讀。"""
        if self.cfg.residual_roll_deg and self._t < self._turning_until:
            rolled = axis_angle_quat(FORWARD, self.cfg.residual_roll_deg)
            return Pose(self._true_pose.position, quat_mul(self._true_pose.orientation, rolled))
        return self._true_pose

    def reconfigure(self, **changes) -> None:
        """任務進行到一半換設定（例如中途變慢）；給測試的子類別用。"""
        self.cfg = self.cfg._replace(**changes)

    def _arrival_offset(self, target: Pose) -> Vec3:
        """這次到 target 要偏多少（世界座標），並記下又到了一次。"""
        offsets = self.cfg.arrival_offsets_m
        if not offsets:
            return (0.0, 0.0, 0.0)
        earlier = self._arrivals.get(target.position, 0)
        self._arrivals[target.position] = earlier + 1
        return rotate(target.orientation, offsets[min(earlier, len(offsets) - 1)])

    # ---- Robot 介面 ----
    def now(self) -> float:
        return self._t

    def sleep(self, sec: float) -> None:
        self._t += sec

    def pose(self) -> Optional[Pose]:
        truth = self.truth()
        jitter = tuple(self.rng.gauss(0, self.cfg.nav_jitter_m) for _ in range(3))
        return Pose(
            add(truth.position, (jitter[0], jitter[1], jitter[2])),
            truth.orientation,
            stamp=self._t,
        )

    def move_to(self, target: Pose, timeout_sec: float) -> str:
        self.move_calls += 1
        if self.cfg.move_always:
            if self.cfg.move_always == MOVE_TIMEOUT:
                self._t += timeout_sec
            return self.cfg.move_always
        here = self.truth()
        duration = self.cfg.move_overhead_sec + leg_seconds(
            here.position, here.orientation, target.position, target.orientation, self.cfg.speeds
        )
        if duration > timeout_sec:
            self._t += timeout_sec
            return MOVE_TIMEOUT
        if self.rng.random() < self.cfg.move_fail_prob:
            self._t += duration / 2.0
            return MOVE_ABORTED
        self._t += duration
        noise: Vec3 = (
            self.rng.gauss(0, self.cfg.position_noise_m),
            self.rng.gauss(0, self.cfg.position_noise_m),
            self.rng.gauss(0, self.cfg.position_noise_m),
        )
        wobble = _random_rotation(self.rng, self.cfg.attitude_noise_deg)
        position = add(add(target.position, self._arrival_offset(target)), noise)
        self._true_pose = Pose(position, quat_mul(target.orientation, wobble))
        self._turning_until = self._t + self.cfg.residual_roll_sec
        self._record_tail()
        return MOVE_SUCCESS

    def _record_tail(self) -> None:
        """把「回報成功前已經停在這裡的那幾秒」寫進導航紀錄，每 0.05 秒一筆。"""
        steps = int(round(self.cfg.settled_before_return_sec / 0.05))
        if steps <= 0:
            return
        truth = self.truth()
        for k in range(steps, -1, -1):
            stamp = self._t - 0.05 * k
            self.navlog.add(Pose(truth.position, truth.orientation, stamp))

    def recent_poses(self, seconds: float) -> List[Pose]:
        return self.navlog.recent(self._t, seconds)

    def marker_in_body(self, marker_id: int) -> Optional[Vec3]:
        """假相機：由真實姿態反推 marker 在機體座標系的位置，加一點雜訊。"""
        if not self.cfg.camera:
            return None
        marker = self.checkpoints.by_id(marker_id).marker_position
        here = self.truth()
        seen = expected_marker_in_body(here.position, here.orientation, marker)
        return add(seen, tuple(self.rng.gauss(0, self.cfg.vision_noise_m) for _ in range(3)))  # type: ignore[arg-type]

    def move_relative(self, delta: Vec3, timeout_sec: float) -> str:
        self.relative_calls += 1
        # 相對移動是從「轉完之後會停在的姿態」算的：殘餘滾轉是疊在它上面的暫時量，
        # 拿正在轉的姿態當起點，會把那幾度永久寫進去。
        here = self._true_pose
        there = add(here.position, rotate(here.orientation, delta))
        self._t += self.cfg.move_overhead_sec + leg_seconds(
            here.position, here.orientation, there, here.orientation, self.cfg.speeds
        )
        self._true_pose = Pose(there, here.orientation)
        return MOVE_SUCCESS

    def mission_start(self) -> bool:
        self.judge.mission_start()
        return True

    def get_checkpoints_message(self) -> Optional[str]:
        self.checkpoints_calls += 1
        if self.checkpoints_calls <= self.cfg.checkpoints_fail_times:
            return None
        return self.message

    def notify_checkpoint(self, checkpoint_id: int, timeout_sec: float = float("inf")) -> bool:
        """通知一律被「接受」（回 True 不代表通過）；過不過由假裁判用送出當下的真實姿態判。

        來回要 notify_sec；比 timeout_sec 久就是逾時：花掉 timeout_sec、回 False，
        假裁判當作沒收到（真的伺服器有沒有收到不知道，這裡取不利的那一邊）。
        測試直接呼叫時可以不給 timeout_sec，等於不限時。"""
        if self.cfg.notify_sec > timeout_sec:
            self._t += timeout_sec
            return False
        sent_from = self.truth()
        self._t += self.cfg.notify_sec
        self.judge.checkpoint_passed(checkpoint_id, sent_from)
        return True

    def mission_finish(self) -> bool:
        self.judge.mission_finish(self.truth(), self._t)
        return True

    def stop_requested(self) -> bool:
        return self.stop

    def log(self, message: str) -> None:
        self.logs.append(message)
