"""任務狀態機：整場比賽的流程，不碰 ROS。

讀這個檔案就能知道程式「打算怎麼比」：

    開始 → 取得 CheckPoint → 規劃（含時間預算）→ 移動到下一點 → 穩定並自我判定
    → 回報通過 → 下一點 …… → Goal → 完成回報

所有跟機器人說話的動作都透過 `Robot` 介面。ROS 版在 `ros/user_node.py`，假的版本在
`kibo/fake_robot.py`，所以這裡的邏輯可以在沒有模擬器的電腦上整場跑完。

安全原則（手冊第 5 章、6.5）：每個迴圈都有次數上限，每個等待都有時間上限，
失敗有重試上限，收到停止要求就立刻收尾。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, NamedTuple, Optional

from kibo.budget import DEFAULT_BUDGET, BudgetConfig, plan_within_budget
from kibo.checkpoints import Checkpoint, CheckpointSet, parse_checkpoints
from kibo.field import TIME_LIMIT_SEC
from kibo.geometry import Vec3, norm
from kibo.judge import CAMERA_OFFSET, Judgement, Pose, judge, target_attitude
from kibo.vision import body_correction, expected_marker_in_body

MOVE_SUCCESS = "success"
MOVE_TIMEOUT = "timeout"
MOVE_ABORTED = "aborted"
MOVE_INVALID = "invalid"


class Robot(ABC):
    """任務邏輯需要機器人提供的全部能力。方法都是同步的、會阻塞到完成或逾時。"""

    @abstractmethod
    def now(self) -> float:
        """目前時間（秒）。只用來算差，基準不重要。"""

    @abstractmethod
    def pose(self) -> Optional[Pose]:
        """目前位置與姿態；沒有導航資料時回 None。"""

    @abstractmethod
    def move_to(self, target: Pose, timeout_sec: float) -> str:
        """絕對移動，回傳 MOVE_* 其中之一。"""

    @abstractmethod
    def sleep(self, sec: float) -> None:
        """等待 sec 秒。"""

    @abstractmethod
    def mission_start(self) -> bool:
        """呼叫 /event/mission_start。"""

    @abstractmethod
    def get_checkpoints_message(self) -> Optional[str]:
        """`/mission/get_checkpoints` 回應裡的 JSON 字串；失敗回 None。"""

    @abstractmethod
    def notify_checkpoint(self, checkpoint_id: int) -> bool:
        """呼叫 /event/checkpoint_passed，回傳伺服器是否接受。"""

    @abstractmethod
    def mission_finish(self) -> bool:
        """呼叫 /event/mission_finished。"""

    def stop_requested(self) -> bool:
        return False

    def marker_in_body(self, marker_id: int) -> Optional[Vec3]:
        """相機看到的 marker 中心在機體座標系的位置；沒有相機或沒看到就回 None（選用）。"""
        return None

    def move_relative(self, delta: Vec3, timeout_sec: float) -> str:
        """以機體座標系平移 delta、姿態不變；不支援就回 MOVE_INVALID（選用）。"""
        return MOVE_INVALID

    def log(self, message: str) -> None:
        """預設印到標準輸出；ROS 版改用 rospy.loginfo。"""
        print(message)


class MissionConfig(NamedTuple):
    time_limit_sec: float = float(TIME_LIMIT_SEC)
    budget: BudgetConfig = DEFAULT_BUDGET
    move_timeout_sec: float = 60.0
    max_move_attempts: int = 2  # 總共嘗試幾次（含第一次）
    settle_samples: int = 5  # 連續幾次取樣都達標才算穩定；5 次、間隔 0.25 秒剛好涵蓋 1 秒
    settle_interval_sec: float = 0.25
    settle_timeout_sec: float = 6.0
    target_level: int = 3
    hurry_sec: float = 40.0  # 剩餘時間少於這個就不再追求 Lv3
    notify_attempts: int = 2
    checkpoints_attempts: int = 3
    checkpoints_retry_sec: float = 1.0
    pose_attempts: int = 5
    camera_offset_m: Vec3 = CAMERA_OFFSET  # 對中用相機位置；伺服器若用機體中心就設成 (0, 0, 0)
    camera_fix_max_m: float = 0.3  # 相機算出的修正量超過這個就不信它，改用絕對移動


DEFAULT_MISSION = MissionConfig()


class Settled(NamedTuple):
    """穩定階段的結果：最後一次判定，以及是否真的連續達標。"""

    judgement: Optional[Judgement]  # None 代表整段期間都沒有導航資料
    stable: bool

    @property
    def level(self) -> int:
        return self.judgement.level if self.judgement is not None else 0


class Visit(NamedTuple):
    checkpoint_id: int
    moved: bool
    judged_level: int
    stable: bool
    notified: bool


class MissionReport(NamedTuple):
    visits: List[Visit]
    dropped: List[int]
    goal_reached: bool
    finished: bool
    elapsed_sec: float
    aborted: str  # 空字串代表正常結束


class _Run:
    """一場任務的執行狀態；只在 run_mission 裡面用。"""

    def __init__(self, robot: Robot, config: MissionConfig) -> None:
        self.robot = robot
        self.cfg = config
        self.t0 = robot.now()  # 假設：/ib2_user/start 到來時 Release 剛完成；待模擬器驗證
        self.visits: List[Visit] = []
        self.dropped: List[int] = []
        self.last_pose: Optional[Pose] = None

    def elapsed(self) -> float:
        return self.robot.now() - self.t0

    def remaining(self) -> float:
        return self.cfg.time_limit_sec - self.elapsed()

    def log(self, message: str) -> None:
        self.robot.log("[%6.1fs left] %s" % (self.remaining(), message))

    def current_pose(self) -> Optional[Pose]:
        """幾次都讀不到導航資料就回 None；呼叫端自己決定怎麼辦，不假裝知道位置。"""
        for _ in range(self.cfg.pose_attempts):
            pose = self.robot.pose()
            if pose is not None:
                self.last_pose = pose
                return pose
            self.robot.sleep(self.cfg.settle_interval_sec)
        self.log("no navigation data")
        return None

    def fetch_checkpoints(self) -> Optional[CheckpointSet]:
        for attempt in range(self.cfg.checkpoints_attempts):
            message = self.robot.get_checkpoints_message()
            if message:
                try:
                    return parse_checkpoints(message)
                except ValueError as exc:
                    self.log("checkpoints parse failed: %s" % exc)
            self.log("get_checkpoints attempt %d failed" % (attempt + 1))
            if attempt + 1 < self.cfg.checkpoints_attempts:
                self.robot.sleep(self.cfg.checkpoints_retry_sec)
        return None

    def required_level(self) -> int:
        return 1 if self.remaining() < self.cfg.hurry_sec else self.cfg.target_level

    def move_timeout(self) -> float:
        return max(5.0, min(self.cfg.move_timeout_sec, self.remaining()))

    def settle(self, cp: Checkpoint) -> Settled:
        """等到連續幾次自我判定都達標（stable=True），或逾時（回傳最後一次判定）。"""
        deadline = self.robot.now() + self.cfg.settle_timeout_sec
        streak = 0
        last: Optional[Judgement] = None
        max_samples = int(self.cfg.settle_timeout_sec / self.cfg.settle_interval_sec) + 2
        for _ in range(max_samples):
            if self.robot.now() > deadline or self.robot.stop_requested():
                break
            pose = self.current_pose()
            if pose is None:
                return Settled(None, False)
            last = judge(pose, cp, self.cfg.camera_offset_m)
            streak = streak + 1 if last.level >= self.required_level() else 0
            if streak >= self.cfg.settle_samples:
                return Settled(last, True)
            self.robot.sleep(self.cfg.settle_interval_sec)
        return Settled(last, False)

    def move(self, cp: Checkpoint, attempts: int) -> bool:
        target = Pose(cp.position, target_attitude(cp))
        for attempt in range(attempts):
            if self.robot.stop_requested():
                return False
            result = self.robot.move_to(target, self.move_timeout())
            self.log("move to #%d attempt %d: %s" % (cp.id, attempt + 1, result))
            if result == MOVE_SUCCESS:
                return True
            if result == MOVE_INVALID:
                return False  # 再試也不會變合法
        return False

    def notify(self, cp: Checkpoint) -> bool:
        for attempt in range(self.cfg.notify_attempts):
            if self.robot.notify_checkpoint(cp.id):
                self.log("checkpoint #%d accepted" % cp.id)
                return True
            self.log("checkpoint #%d rejected (attempt %d)" % (cp.id, attempt + 1))
            self.robot.sleep(self.cfg.settle_interval_sec)
        return False

    def describe(self, cp: Checkpoint, settled: Settled) -> str:
        if settled.judgement is None:
            return "at #%d: no navigation data" % cp.id
        j = settled.judgement
        return "at #%d: dist=%.2fm centering=%.1f roll=%.1f -> Lv%d%s" % (
            cp.id,
            j.distance_m,
            j.centering_deg,
            j.roll_deg,
            j.level,
            " (stable)" if settled.stable else " (unstable)",
        )

    def camera_fix(self, cp: Checkpoint) -> bool:
        """用相機看到的 marker 位置修正幾公分；沒有相機、沒看到或修正量太大就回 False。"""
        observed = self.robot.marker_in_body(cp.id)
        if observed is None:
            return False
        expected = expected_marker_in_body(cp.position, target_attitude(cp), cp.marker_position)
        delta = body_correction(observed, expected)
        if norm(delta) > self.cfg.camera_fix_max_m:
            self.log("camera correction %.2fm too large, ignoring" % norm(delta))
            return False
        result = self.robot.move_relative(delta, self.move_timeout())
        self.log(
            "camera correction (%.3f, %.3f, %.3f): %s" % (delta[0], delta[1], delta[2], result)
        )
        return result == MOVE_SUCCESS

    def visit(self, cp: Checkpoint) -> Visit:
        moved = self.move(cp, self.cfg.max_move_attempts)
        settled = self.settle(cp)
        self.log(self.describe(cp, settled))
        if not settled.stable and moved and self.remaining() > self.cfg.hurry_sec:
            # 再修正一次通常就夠了；只做一次，不無限修正。有相機就用相機，沒有就再絕對移動一次。
            if self.camera_fix(cp) or self.move(cp, 1):
                settled = self.settle(cp)
                self.log("refined: " + self.describe(cp, settled))
        # 穩定達標就回報；沒穩定但最後一次判定至少 Lv1 也回報（伺服器才是裁判，
        # 不回報一定 0 分）；完全沒有導航資料就不回報，因為我們根本不知道在哪。
        notified = settled.level > 0 and self.notify(cp)
        record = Visit(cp.id, moved, settled.level, settled.stable, notified)
        self.visits.append(record)
        return record

    def report(self, goal_reached: bool, finished: bool, aborted: str) -> MissionReport:
        return MissionReport(
            list(self.visits), list(self.dropped), goal_reached, finished, self.elapsed(), aborted
        )


def run_mission(robot: Robot, config: MissionConfig = DEFAULT_MISSION) -> MissionReport:
    run = _Run(robot, config)
    if not robot.mission_start():
        run.log("mission_start failed")
        return run.report(False, False, "mission_start failed")
    run.log("mission started")

    cps = run.fetch_checkpoints()
    if cps is None:
        robot.mission_finish()
        return run.report(False, True, "no checkpoints")
    run.log("%d checkpoints, goal #%d" % (len(cps.checkpoints), cps.goal_id))

    pending: List[Checkpoint] = list(cps.waypoints)
    by_id: Dict[int, Checkpoint] = {cp.id: cp for cp in cps.checkpoints}
    goal_reached = False
    for _ in range(len(cps.checkpoints) + 1):  # 每輪至少消化一個點，所以有上限
        if robot.stop_requested():
            return run.report(goal_reached, False, "stop requested")
        here = run.current_pose() or run.last_pose or Pose(cps.goal.position, cps.goal.attitude)
        plan = plan_within_budget(
            here.position, here.orientation, pending, cps.goal, run.remaining(), config.budget
        )
        if plan.dropped:
            run.log("dropping %s to protect the goal" % plan.dropped)
            run.dropped.extend(plan.dropped)
            pending = [cp for cp in pending if cp.id not in plan.dropped]
        run.log("route %s (~%.0fs)" % (plan.route.order, plan.estimated_sec))
        target = by_id[plan.route.order[0]]
        record = run.visit(target)
        if target.id == cps.goal.id:
            goal_reached = record.notified
            break
        pending = [cp for cp in pending if cp.id != target.id]

    finished = robot.mission_finish()
    run.log("mission finished: %s" % finished)
    return run.report(goal_reached, finished, "")
