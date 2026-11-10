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
from typing import Dict, List, NamedTuple, Optional, Tuple

from kibo.budget import DEFAULT_BUDGET, BudgetConfig, plan_within_budget
from kibo.checkpoints import Checkpoint, CheckpointSet, parse_checkpoints
from kibo.field import TIME_LIMIT_SEC
from kibo.geometry import Vec3, distance, norm, quat_angle
from kibo.judge import JUDGE_ORIGIN, Judgement, Pose, judge, target_attitude
from kibo.planner import Speeds, leg_seconds
from kibo.vision import body_correction, expected_marker_in_body

ABORT_STOP = "stop requested"

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
    settle_samples: int = 5  # 連續幾筆新的導航資料都達標才算穩定；5 筆、間隔 0.25 秒約涵蓋 1 秒
    settle_interval_sec: float = 0.25
    settle_timeout_sec: float = 6.0
    target_level: int = 3
    hurry_sec: float = 40.0  # 剩餘時間少於這個就不再追求 Lv3
    notify_attempts: int = 2
    checkpoints_attempts: int = 3
    checkpoints_retry_sec: float = 1.0
    pose_attempts: int = 5
    camera_offset_m: Vec3 = JUDGE_ORIGIN  # 官方 judge.py 的對中從機體中心量；不要改，留著只為對照
    camera_fix_max_m: float = (
        0.0  # 相機修正量的上限；0 = 關（預設關：ROS 端座標未驗證，增益 fake-sensitive）
    )
    calibrate_speed: bool = True  # 用實測的移動秒數修正時間預算（只往慢的方向）
    min_speed_ratio: float = 0.5  # 校正的上限：最多當作比模型慢 1/0.5 = 2 倍
    calibrate_below_ratio: float = 0.8  # 死區：實測在模型的 1/0.8 = 1.25 倍以內不校正
    calibrate_min_leg_m: float = 0.5  # 只用這麼長以上的腿校正
    # 探針旗標：只在資格賽的模擬器上做實驗用，預設全關，決賽程式不得開啟。
    notify_even_if_level0: bool = False  # 自判沒過也回報一次，拿伺服器的判定來校準自判
    skip_one_waypoint: bool = False  # 故意漏掉一個中途點，看 Goal 分數是否還給
    deliberate_late_after: int = 0  # 成功回報這麼多點之後故意等到逾時，看逾時規則；0 = 關
    calibrate_min_predicted_sec: float = 20.0  # 長腿的模型秒數累積到這麼多才校正，一段腿不算數

    @property
    def probes_on(self) -> bool:
        """任一探針旗標開著。決賽程式必須是 False。"""
        return bool(
            self.notify_even_if_level0 or self.skip_one_waypoint or self.deliberate_late_after
        )


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
        self.speeds: Speeds = config.budget.speeds  # 會被實測往慢的方向修
        self.predicted_sec = 0.0  # 長腿的模型預測秒數累積
        self.actual_sec = 0.0  # 同一批腿的實際秒數累積

    def elapsed(self) -> float:
        return self.robot.now() - self.t0

    def remaining(self) -> float:
        return self.cfg.time_limit_sec - self.elapsed()

    def log(self, message: str) -> None:
        """前綴：機器人時鐘的絕對秒數（對結果 JSON 的事件時間用）與剩餘秒數。"""
        self.robot.log("[t=%.1f %6.1fs left] %s" % (self.robot.now(), self.remaining(), message))

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

    def move_timeout(self, target: Optional[Pose] = None) -> float:
        """至少 move_timeout_sec，長腿放大到估計秒數的三倍；不超過剩餘時間，但最少 5 秒。

        三倍：校正最多只認「慢 2 倍」，逾時要比那更寬，否則慢 2 倍多的機器人
        每段長腿都會被自己取消。"""
        timeout = self.cfg.move_timeout_sec
        if target is not None and self.last_pose is not None:
            estimate = leg_seconds(
                self.last_pose.position,
                self.last_pose.orientation,
                target.position,
                target.orientation,
                self.speeds,
            )
            timeout = max(timeout, 3.0 * estimate)
        return max(5.0, min(timeout, self.remaining()))

    def record_leg(
        self, start: Optional[Pose], target: Pose, seconds: float, timed_out: bool = False
    ) -> None:
        """一段移動：記錄距離與秒數，必要時把規劃用的速度往慢修。

        逾時的腿也算證據：實際秒數至少是逾時值，所以算出來的「慢幾倍」是下界，
        只會把速度往慢修，方向安全；沒有它，比假設慢很多的機器人會一直逾時、永遠學不到。

        比的是「模型預測的秒數」對「實際秒數」。模型在本機模擬器上每段腿只差一兩秒，
        所以這是保險：Web 模擬器或實機若整體比較慢，實測會把規劃用的秒數等比例放大。
        慢超過死區才動，只往慢修，最多 2 倍；很短的腿不算（一兩秒的誤差佔比太大）。
        """
        if start is None or seconds <= 0.0:
            return
        metres = distance(start.position, target.position)
        default = self.cfg.budget.speeds
        predicted = leg_seconds(
            start.position, start.orientation, target.position, target.orientation, default
        )
        self.log(
            "leg: %.2fm %.0fdeg in %.1fs (model %.1fs)%s"
            % (
                metres,
                quat_angle(start.orientation, target.orientation),
                seconds,
                predicted,
                " TIMED OUT, lower bound" if timed_out else "",
            )
        )
        if not self.cfg.calibrate_speed or metres < self.cfg.calibrate_min_leg_m:
            return
        self.predicted_sec += predicted
        self.actual_sec += seconds
        if self.predicted_sec < self.cfg.calibrate_min_predicted_sec:
            return  # 一兩段腿不足以下結論
        slowdown = self.actual_sec / self.predicted_sec
        if slowdown <= 1.0 / self.cfg.calibrate_below_ratio:
            slowdown = 1.0  # 在死區內：用預設值（已校正過的也拉回預設，不留棘輪）
        slowdown = min(slowdown, 1.0 / self.cfg.min_speed_ratio)
        calibrated = default._replace(slowdown=default.slowdown * slowdown)
        if abs(calibrated.slowdown - self.speeds.slowdown) > 1e-9:
            self.log(
                "speed calibrated: slowdown %.2f -> %.2f (x%.2f vs model, over %.0fs of legs)"
                % (self.speeds.slowdown, calibrated.slowdown, slowdown, self.predicted_sec)
            )
            self.speeds = calibrated

    def settle(self, cp: Checkpoint) -> Settled:
        """等到連續幾次自我判定都達標（stable=True），或逾時（回傳最後一次判定）。

        同一筆導航資料只算一次：若 stamp 沒變，不計入連續次數，免得導航更新慢時
        把同一筆讀五次當成「穩定 1 秒」。
        """
        deadline = self.robot.now() + self.cfg.settle_timeout_sec
        streak = 0
        last: Optional[Judgement] = None
        last_stamp: Optional[float] = None
        max_samples = int(self.cfg.settle_timeout_sec / self.cfg.settle_interval_sec) + 2
        for _ in range(max_samples):
            if self.robot.now() > deadline or self.robot.stop_requested():
                break
            pose = self.current_pose()
            if pose is None:
                return Settled(None, False)
            if pose.stamp is not None and pose.stamp == last_stamp:
                self.robot.sleep(self.cfg.settle_interval_sec)
                continue
            last_stamp = pose.stamp
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
            start, started_at = self.last_pose, self.robot.now()
            result = self.robot.move_to(target, self.move_timeout(target))
            self.log("move to #%d attempt %d: %s" % (cp.id, attempt + 1, result))
            elapsed = self.robot.now() - started_at
            if result == MOVE_SUCCESS:
                if attempt == 0:  # 重試時起點已經不是 last_pose，這段腿不拿來校正
                    self.record_leg(start, target, elapsed)
                return True
            if result == MOVE_TIMEOUT and attempt == 0:
                self.record_leg(start, target, elapsed, timed_out=True)
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
        age = ""
        if self.last_pose is not None and self.last_pose.stamp is not None:
            age = " nav_age=%.2fs" % (self.robot.now() - self.last_pose.stamp)
        return "at #%d: dist=%.2fm centering=%.1f roll=%.1f -> Lv%d%s%s" % (
            cp.id,
            j.distance_m,
            j.centering_deg,
            j.roll_deg,
            j.level,
            " (stable)" if settled.stable else " (unstable)",
            age,
        )

    def camera_fix(self, cp: Checkpoint) -> bool:
        """用相機看到的 marker 位置修正幾公分；沒有相機、沒看到或修正量太大就回 False。"""
        if self.cfg.camera_fix_max_m <= 0.0:
            return False
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
        # 不回報一定 0 分）。沒有成功移動到點就不回報（手冊 6.5），完全沒有導航資料
        # 也不回報。探針旗標 notify_even_if_level0 可以在模擬器上覆寫這兩條。
        should_notify = (settled.level > 0 and moved) or self.cfg.notify_even_if_level0
        notified = should_notify and self.notify(cp)
        notified_so_far = sum(1 for v in self.visits if v.notified) + (1 if notified else 0)
        if self.cfg.deliberate_late_after and notified_so_far == self.cfg.deliberate_late_after:
            self.log("PROBE: deliberately waiting past the time limit")
            for _ in range(int(self.cfg.time_limit_sec) + 10):  # 每秒看一次停止要求
                if self.remaining() < -5.0 or self.robot.stop_requested():
                    break
                self.robot.sleep(1.0)
        record = Visit(cp.id, moved, settled.level, settled.stable, notified)
        self.visits.append(record)
        return record

    def report(self, goal_reached: bool, finished: bool, aborted: str) -> MissionReport:
        return MissionReport(
            list(self.visits), list(self.dropped), goal_reached, finished, self.elapsed(), aborted
        )


def run_mission(robot: Robot, config: MissionConfig = DEFAULT_MISSION) -> MissionReport:
    """整場任務。不管中間發生什麼（例外也算），只要任務開始了就一定會呼叫 mission_finish，
    因為完成回報與剩餘時間倍率是乘在全部分數上的。唯一例外是收到 /ib2_user/stop：
    那是操作員要我們停，不再送任何東西。"""
    run = _Run(robot, config)
    if not robot.mission_start():
        run.log("mission_start failed")
        return run.report(False, False, "mission_start failed")
    run.log("mission started")
    goal_reached = False
    aborted = ""
    try:
        goal_reached, aborted = _fly(run, robot, config)
    except Exception as exc:  # 任何未預期的錯都不能吃掉完成回報
        run.log("mission flow failed: %r" % (exc,))
        aborted = "exception: %r" % (exc,)
    if aborted == ABORT_STOP:
        return run.report(goal_reached, False, aborted)
    finished = robot.mission_finish()
    run.log("mission finished: %s" % finished)
    return run.report(goal_reached, finished, aborted)


def _fly(run: _Run, robot: Robot, config: MissionConfig) -> Tuple[bool, str]:
    """從取得 CheckPoint 到抵達 Goal。回傳 (goal_reached, aborted)。"""
    cps = run.fetch_checkpoints()
    if cps is None:
        return False, "no checkpoints"
    for warning in cps.warnings:
        run.log("checkpoints warning: " + warning)
    run.log("%d checkpoints, goal #%d" % (len(cps.checkpoints), cps.goal_id))
    if config.probes_on:
        run.log("PROBE FLAGS ON: this build is for simulator experiments only")

    pending: List[Checkpoint] = list(cps.waypoints)
    if config.skip_one_waypoint and pending:
        skipped = pending.pop(0)
        run.log("PROBE: skipping waypoint #%d on purpose" % skipped.id)
    by_id: Dict[int, Checkpoint] = {cp.id: cp for cp in cps.checkpoints}
    goal_reached = False
    for _ in range(len(cps.checkpoints) + 1):  # 每輪至少消化一個點，所以有上限
        if robot.stop_requested():
            return goal_reached, ABORT_STOP
        here = run.current_pose() or run.last_pose or Pose(cps.goal.position, cps.goal.attitude)
        plan = plan_within_budget(
            here.position,
            here.orientation,
            pending,
            cps.goal,
            run.remaining(),
            config.budget._replace(speeds=run.speeds),
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
    return goal_reached, ""
