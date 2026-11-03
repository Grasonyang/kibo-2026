"""任務狀態機：整場比賽的流程，不碰 ROS。

讀這個檔案就能知道程式「打算怎麼比」：

    開始 → 取得 CheckPoint → 規劃（含時間預算）→ 移動到下一點 → 穩定並自我判定
    → 回報通過 → 下一點 …… → Goal → 完成回報

所有跟機器人說話的動作都透過 `Robot` 介面。ROS 版在 `krpc_user/`，假的版本在
`kibo/fake_robot.py`，所以這裡的邏輯可以在沒有模擬器的電腦上整場跑完。

安全原則（手冊第 5 章、6.5）：每個迴圈都有次數上限，每個等待都有時間上限，
失敗有重試上限，收到停止要求就立刻收尾。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, NamedTuple, Optional

from kibo.budget import DEFAULT_BUDGET, BudgetConfig, plan_within_budget
from kibo.checkpoints import Checkpoint, CheckpointSet, parse_checkpoints
from kibo.judge import Judgement, Pose, judge

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
        pass

    @abstractmethod
    def mission_start(self) -> bool:
        pass

    @abstractmethod
    def get_checkpoints_message(self) -> Optional[str]:
        """`/mission/get_checkpoints` 回應裡的 JSON 字串；失敗回 None。"""

    @abstractmethod
    def notify_checkpoint(self, checkpoint_id: int) -> bool:
        pass

    @abstractmethod
    def mission_finish(self) -> bool:
        pass

    def stop_requested(self) -> bool:
        return False

    def log(self, message: str) -> None:
        """預設印到標準輸出；ROS 版改用 rospy.loginfo。"""
        print(message)


class MissionConfig(NamedTuple):
    time_limit_sec: float = 300.0
    budget: BudgetConfig = DEFAULT_BUDGET
    move_timeout_sec: float = 60.0
    max_move_attempts: int = 2
    settle_samples: int = 3  # 連續幾次取樣都達標才算穩定
    settle_interval_sec: float = 0.3
    settle_timeout_sec: float = 6.0
    target_level: int = 3
    hurry_sec: float = 40.0  # 剩餘時間少於這個就不再追求 Lv3
    notify_attempts: int = 2
    checkpoints_attempts: int = 3
    pose_attempts: int = 5


DEFAULT_MISSION = MissionConfig()


class Visit(NamedTuple):
    checkpoint_id: int
    moved: bool
    judged_level: int
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
        self.t0 = robot.now()
        self.visits: List[Visit] = []
        self.dropped: List[int] = []
        self.last_pose: Optional[Pose] = None

    def elapsed(self) -> float:
        return self.robot.now() - self.t0

    def remaining(self) -> float:
        return self.cfg.time_limit_sec - self.elapsed()

    def log(self, message: str) -> None:
        self.robot.log("[%6.1fs left] %s" % (self.remaining(), message))

    def current_pose(self, fallback: Pose) -> Pose:
        for _ in range(self.cfg.pose_attempts):
            pose = self.robot.pose()
            if pose is not None:
                self.last_pose = pose
                return pose
            self.robot.sleep(self.cfg.settle_interval_sec)
        self.log("no navigation data, using last known pose")
        return self.last_pose or fallback

    def fetch_checkpoints(self) -> Optional[CheckpointSet]:
        for attempt in range(self.cfg.checkpoints_attempts):
            message = self.robot.get_checkpoints_message()
            if message:
                try:
                    return parse_checkpoints(message)
                except (ValueError, KeyError, TypeError) as exc:
                    self.log("checkpoints parse failed: %s" % exc)
            self.robot.sleep(1.0)
            self.log("get_checkpoints attempt %d failed" % (attempt + 1))
        return None

    def required_level(self) -> int:
        return 1 if self.remaining() < self.cfg.hurry_sec else self.cfg.target_level

    def settle(self, cp: Checkpoint) -> Judgement:
        """等到連續幾次自我判定都達標，或逾時；回傳最後一次判定。"""
        deadline = self.robot.now() + self.cfg.settle_timeout_sec
        streak = 0
        best = judge(self.current_pose(Pose(cp.position, cp.attitude)), cp)
        max_samples = int(self.cfg.settle_timeout_sec / self.cfg.settle_interval_sec) + 2
        for _ in range(max_samples):
            if self.robot.now() > deadline or self.robot.stop_requested():
                break
            result = judge(self.current_pose(Pose(cp.position, cp.attitude)), cp)
            if result.level > best.level:
                best = result
            streak = streak + 1 if result.level >= self.required_level() else 0
            if streak >= self.cfg.settle_samples:
                return result
            self.robot.sleep(self.cfg.settle_interval_sec)
        return best

    def move(self, cp: Checkpoint) -> bool:
        target = Pose(cp.position, cp.attitude)
        for attempt in range(self.cfg.max_move_attempts):
            if self.robot.stop_requested():
                return False
            timeout = max(5.0, min(self.cfg.move_timeout_sec, self.remaining()))
            result = self.robot.move_to(target, timeout)
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

    def visit(self, cp: Checkpoint) -> Visit:
        moved = self.move(cp)
        result = self.settle(cp)
        self.log(
            "at #%d: dist=%.2fm centering=%.1f roll=%.1f -> Lv%d"
            % (cp.id, result.distance_m, result.centering_deg, result.roll_deg, result.level)
        )
        if result.level < self.required_level() and moved and self.remaining() > self.cfg.hurry_sec:
            # 再靠近一次通常就夠了；只做一次，不無限修正。
            self.robot.move_to(Pose(cp.position, cp.attitude), self.cfg.move_timeout_sec)
            result = self.settle(cp)
            self.log("refined #%d -> Lv%d" % (cp.id, result.level))
        notified = result.level > 0 and self.notify(cp)
        visit = Visit(cp.id, moved, result.level, notified)
        self.visits.append(visit)
        return visit

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
        here = run.current_pose(run.last_pose or Pose(cps.goal.position, cps.goal.attitude))
        plan = plan_within_budget(
            here.position,
            here.orientation,
            pending,
            cps.goal,
            run.remaining(),
            config.budget,
            config.target_level,
        )
        if plan.dropped:
            run.log("dropping %s to protect the goal" % plan.dropped)
            run.dropped.extend(plan.dropped)
            pending = [cp for cp in pending if cp.id not in plan.dropped]
        run.log("route %s (~%.0fs)" % (plan.route.order, plan.estimated_sec))
        target = by_id[plan.route.order[0]]
        visit = run.visit(target)
        if target.id == cps.goal.id:
            goal_reached = visit.notified
            break
        pending = [cp for cp in pending if cp.id != target.id]

    finished = robot.mission_finish()
    run.log("mission finished: %s" % finished)
    return run.report(goal_reached, finished, "")
