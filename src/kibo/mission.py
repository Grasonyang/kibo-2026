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
from kibo.checkpoints import Checkpoint, CheckpointSet, parse_checkpoints, target_attitude
from kibo.ctl_result import MOVE_INVALID, MOVE_SUCCESS, MOVE_TIMEOUT
from kibo.field import TIME_LIMIT_SEC
from kibo.geometry import Pose, Vec3, distance, norm, quat_angle
from kibo.judge import Judgement
from kibo.motion import Speeds, leg_seconds
from kibo.settle import SettleRule, Steadiness
from kibo.vision import body_correction, expected_marker_in_body

ABORT_STOP = "stop requested"

TOP_LEVEL = 3  # 最高的通過等級；notify_margin 的緩衝只在追求這一級時才有意義


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
        """絕對移動，回傳 kibo.ctl_result 的 MOVE_* 其中之一。"""

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

    def recent_poses(self, seconds: float) -> List[Pose]:
        """最近 seconds 秒內收到的導航資料，舊的在前，每筆都要有 stamp；沒有紀錄就回空清單（選用）。

        移動的 action 還沒回來時機器人其實已經停在目標附近幾秒了；有這段紀錄，
        「在容差內待滿 1 秒」就不用從 action 回來才開始數。"""
        return []

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
    hurry_sec: float = 5.0  # 這一點的餘裕（剩餘時間扣掉後面還要飛的）少於這個，就不再追求 Lv3
    refine_sec: float = 15.0  # 餘裕多於這個，沒穩定時才值得再移動一次去修正
    notify_margin: float = 0.8  # 有餘裕時，先等到三個量都在 Lv3 上限的這個比例以內才回報
    settle_strict_sec: float = 3.0  # 上面那個較嚴的標準最多等這麼久，之後照一般的 Lv3 標準
    notify_attempts: int = 2
    checkpoints_attempts: int = 3
    checkpoints_retry_sec: float = 1.0
    pose_attempts: int = 5
    camera_fix_max_m: float = (
        0.0  # 相機修正量的上限；0 = 關（預設關：ROS 端座標未驗證，增益 fake-sensitive）
    )
    calibrate_speed: bool = True  # 用實測的移動秒數修正時間預算（只往慢的方向）
    min_speed_ratio: float = 0.5  # 校正的上限：最多當作比模型慢 1/0.5 = 2 倍
    # 死區：實測在模型的 1/0.9 = 1.11 倍以內不校正。原本是 1.25 倍；慢 20% 到 24% 落在裡面完全不修，
    # 15 秒的保險被吃光（council sim-bringup-review 的 S1）。模型在模擬器上每段腿只差一兩秒
    # （docs/kibo/motion-model.md 的各場實測）。
    calibrate_below_ratio: float = 0.9
    calibrate_min_leg_m: float = 0.5  # 只用這麼長以上的腿校正
    # 探針旗標：只在資格賽的模擬器上做實驗用，預設全關，決賽程式不得開啟。
    notify_even_if_level0: bool = False  # 自判沒過也回報一次，拿伺服器的判定來校準自判
    skip_one_waypoint: bool = False  # 故意漏掉一個中途點，看 Goal 分數是否還給
    deliberate_late_after: int = 0  # 成功回報這麼多點之後故意等到逾時，看逾時規則；0 = 關
    # 以下兩欄不是探針；排在後面只因為欄位順序是介面的一部分，不隨意更動。
    calibrate_min_predicted_sec: float = 20.0  # 長腿的模型秒數累積到這麼多才校正，一段腿不算數
    log_marker: bool = True  # 每到一點記一行「相機看到的 marker 位置 vs 導航算的預期位置」，只記錄
    # 收尾保留：完成回報晚於時限可能整場沒分，所以到點後的等待最晚只等到時限前 finish_reserve_sec
    # （之後還要回報這一點、送完成回報）；移動的逾時再早 cancel_reserve_sec（逾時後取消 action
    # 最多等這麼久，對應 ros/user_node.py 的 CANCEL_WAIT_SEC）。
    finish_reserve_sec: float = 3.0
    cancel_reserve_sec: float = 5.0

    @property
    def probes_on(self) -> bool:
        """任一探針旗標開著。決賽程式必須是 False。"""
        return bool(
            self.notify_even_if_level0 or self.skip_one_waypoint or self.deliberate_late_after
        )


DEFAULT_MISSION = MissionConfig()

# 逾時比這個還短的移動不送：一定來不及，只會多花一次取消的時間。
MIN_MOVE_TIMEOUT_SEC = 1.0


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
        # 我們的時鐘從 /ib2_user/start 到來起算。評分模組記的任務時間是從它收到 mission_start 起算
        # （docs/kibo/simulator-internals.md），比我們晚一點（起跑前最多等 10 秒確認它連上），
        # 所以我們的剩餘時間只會偏少、不會偏多。Web 模擬器的時限若從起跑訊號算，這樣也安全。
        self.t0 = robot.now()
        self.visits: List[Visit] = []
        self.dropped: List[int] = []
        self.last_pose: Optional[Pose] = None
        self.speeds: Speeds = config.budget.speeds  # 會被實測往慢的方向修
        self.reserved_sec = 0.0  # 目前這一點之後還要飛多久（_fly 每一點更新）
        self.stops: List[float] = []  # 每一點實際停留的秒數（到點到回報完），見 stop_sec
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

    def stop_sec(self) -> float:
        """規劃時每一點要留幾秒停留：設定值，或最近三點實際停留秒數的中位數，取大的。

        到點一直不穩時，一點會花到十幾秒（等到逾時、再移動一次、再等）；預算若還照 1 秒估，
        後面的點會排得太滿，最後擠掉 Goal。只往上修，不會比設定值小。

        用中位數而不是平均：只有一點特別久（第一次通知卡了幾秒、某一點剛好不穩）不該讓之後
        每一點都多留那麼久，那會白白刪掉來得及的點；連續兩點都久才採用。還沒有三點時，
        缺的用設定值補。"""
        planned = self.cfg.budget.settle_sec
        recent = sorted(([planned, planned] + self.stops)[-3:])
        return max(planned, recent[1])

    def slack(self) -> float:
        """這一點還能多花幾秒：剩餘時間扣掉後面的路線需要的秒數（reserved_sec，_fly 每一點更新）。
        保險（budget.margin_sec）不在裡面：等待可以把它花掉，之後靠重新規劃刪點補回來。

        用「剩餘時間」的絕對值來判斷趕不趕是錯的：到 Goal 時剩 26 秒其實很充裕（後面沒事了），
        中途剩 100 秒卻可能已經落後。"""
        return self.remaining() - self.reserved_sec

    def required_level(self) -> int:
        return 1 if self.slack() < self.cfg.hurry_sec else self.cfg.target_level

    def move_timeout(
        self, target: Optional[Pose] = None, limit_sec: Optional[float] = None
    ) -> float:
        """至少 move_timeout_sec，長腿放大到估計秒數的三倍；不超過 limit_sec，
        也不越過時限前的收尾保留（逾時後還要取消、回報、送完成回報）。回傳值可能很小甚至是負的：
        代表已經沒有時間移動，由呼叫端決定不送。

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
        reserve = self.cfg.finish_reserve_sec + self.cfg.cancel_reserve_sec
        timeout = min(timeout, self.remaining() - reserve)
        if limit_sec is not None:
            timeout = min(timeout, limit_sec)
        return timeout

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

    def settle_rule(self) -> SettleRule:
        """設定裡與穩定有關的幾欄，換成 kibo.settle 的規則。1 秒 = (筆數 - 1) x 取樣間隔。"""
        return SettleRule(
            samples=self.cfg.settle_samples,
            window_sec=(self.cfg.settle_samples - 1) * self.cfg.settle_interval_sec,
            max_age_sec=self.cfg.settle_interval_sec,
            notify_margin=self.cfg.notify_margin,
            top_level=TOP_LEVEL,
        )

    def settle(self, cp: Checkpoint, wait: bool = True) -> Settled:
        """等到在容差內連續待滿 1 秒（stable=True），或逾時（回傳最後一次判定）。
        `wait=False` 只讀一筆不等：移動沒成功的點不會回報，等它穩定是白花時間。

        「連續待滿」怎麼算在 kibo.settle；這裡只負責拿姿態、看時鐘、決定要求幾級。
        先看移動尾段留下的導航紀錄：夠格就不用再等。否則每 settle_interval_sec 讀一筆，
        前 settle_strict_sec 秒用較嚴的標準（離 Lv3 上限留 notify_margin 的緩衝），之後照一般標準。
        """
        rule = self.settle_rule()
        watch = Steadiness(cp, rule)
        tail = self.robot.recent_poses(rule.window_sec + self.cfg.settle_interval_sec)
        if watch.feed_tail(tail, self.robot.now(), self.required_level()):
            self.last_pose = watch.last_pose
            return Settled(watch.last, True)
        if watch.tail_report:
            self.log("tail of the move not usable: " + watch.tail_report)

        # 最多等 settle_timeout_sec，而且不超過這一點的餘裕（等待不能花掉後面路線要用的時間），
        # 也不越過時限前的收尾保留（到 Goal 時餘裕就是剩餘時間，不能等到見底）。
        # 沒得等的時候仍然讀一筆：那一筆不算穩定，但有判定才能決定要不要回報。
        spare = min(self.slack(), self.remaining() - self.cfg.finish_reserve_sec)
        if not wait:
            spare = 0.0
        deadline = self.robot.now() + min(self.cfg.settle_timeout_sec, max(0.0, spare))
        strict_until = self.robot.now() + self.cfg.settle_strict_sec
        max_samples = int(self.cfg.settle_timeout_sec / self.cfg.settle_interval_sec) + 2
        for _ in range(max_samples):
            if self.robot.stop_requested():
                break
            pose = self.current_pose()
            if pose is None:
                return Settled(None, False)
            strict = self.robot.now() < strict_until
            judgement = watch.feed(pose, self.required_level(), strict)
            if judgement is not None and watch.stable:
                return Settled(judgement, True)
            if self.robot.now() + self.cfg.settle_interval_sec > deadline:
                break
            self.robot.sleep(self.cfg.settle_interval_sec)
        return Settled(watch.last, False)

    def move(self, cp: Checkpoint, attempts: int, limit_sec: Optional[float] = None) -> bool:
        """移動到 cp，最多試 attempts 次；沒有時間了就不送（含重試）。

        `limit_sec` 是每次移動額外的時間上限，只有修正用的再移動才給。再移動的腿不拿來校正速度：
        它的起點是一筆沒穩定的讀數，算出來的預測秒數不可信。"""
        target = Pose(cp.position, target_attitude(cp))
        for attempt in range(attempts):
            if self.robot.stop_requested():
                return False
            timeout = self.move_timeout(target, limit_sec)
            if timeout < MIN_MOVE_TIMEOUT_SEC:
                self.log("no time left to move to #%d" % cp.id)
                return False
            start, started_at = self.last_pose, self.robot.now()
            result = self.robot.move_to(target, timeout)
            self.log("move to #%d attempt %d: %s" % (cp.id, attempt + 1, result))
            elapsed = self.robot.now() - started_at
            evidence = attempt == 0 and limit_sec is None  # 重試時起點已經不是 last_pose
            if result == MOVE_SUCCESS:
                if evidence:
                    self.record_leg(start, target, elapsed)
                return True
            if result == MOVE_TIMEOUT and evidence:
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
        timeout = self.move_timeout(limit_sec=self.slack() - self.cfg.hurry_sec)
        if timeout < MIN_MOVE_TIMEOUT_SEC:
            return False
        result = self.robot.move_relative(delta, timeout)
        self.log(
            "camera correction (%.3f, %.3f, %.3f): %s" % (delta[0], delta[1], delta[2], result)
        )
        return result == MOVE_SUCCESS

    def log_marker(self, cp: Checkpoint) -> None:
        """只記錄、不影響任務：相機看到的 marker 在哪，照導航算又該在哪。

        兩者差多少，就是相機這條路（字典、marker 邊長、座標換算）可不可信的證據；
        在開啟相機修正之前，先用這行 log 累積資料。任何失敗都只記一行。"""
        if not self.cfg.log_marker or self.last_pose is None:
            return
        try:
            observed = self.robot.marker_in_body(cp.id)
        except Exception as exc:  # 診斷碼不能讓任務出事
            self.log("marker #%d check failed: %r" % (cp.id, exc))
            return
        if observed is None:
            self.log("marker #%d not seen" % cp.id)
            return
        pose = self.last_pose
        expected = expected_marker_in_body(pose.position, pose.orientation, cp.marker_position)
        self.log(
            "marker #%d seen at body (%.3f, %.3f, %.3f), nav expects (%.3f, %.3f, %.3f), "
            "apart %.3fm"
            % (
                cp.id,
                observed[0],
                observed[1],
                observed[2],
                expected[0],
                expected[1],
                expected[2],
                distance(observed, expected),
            )
        )

    def visit(self, cp: Checkpoint) -> Visit:
        moved = self.move(cp, self.cfg.max_move_attempts)
        arrived_at = self.robot.now()
        settled = self.settle(cp, wait=moved or self.cfg.notify_even_if_level0)
        self.log(self.describe(cp, settled))
        if not settled.stable and moved and self.slack() > self.cfg.refine_sec:
            # 再修正一次通常就夠了；只做一次，不無限修正。有相機就用相機，沒有就再絕對移動一次。
            # 再移動的時間上限是餘裕扣掉 hurry_sec：修正不能把後面路線要用的時間花掉。
            if self.camera_fix(cp) or self.move(cp, 1, self.slack() - self.cfg.hurry_sec):
                settled = self.settle(cp)
                self.log("refined: " + self.describe(cp, settled))
        # 穩定達標就回報；沒穩定但最後一次判定至少 Lv1 也回報（伺服器才是裁判，
        # 不回報一定 0 分）。沒有成功移動到點就不回報（手冊 6.5），完全沒有導航資料
        # 也不回報。探針旗標 notify_even_if_level0 可以在模擬器上覆寫這兩條。
        should_notify = (settled.level > 0 and moved) or self.cfg.notify_even_if_level0
        notified = should_notify and self.notify(cp)
        self.log_marker(cp)  # 通知送出之後才做，不拖慢回報
        self.stops.append(self.robot.now() - arrived_at)
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
        goal_reached, aborted = _fly(run)
    except Exception as exc:  # 任何未預期的錯都不能吃掉完成回報
        run.log("mission flow failed: %r" % (exc,))
        aborted = "exception: %r" % (exc,)
    if aborted == ABORT_STOP:
        return run.report(goal_reached, False, aborted)
    finished = robot.mission_finish()
    run.log("mission finished: %s" % finished)
    return run.report(goal_reached, finished, aborted)


def _fly(run: _Run) -> Tuple[bool, str]:
    """從取得 CheckPoint 到抵達 Goal。回傳 (goal_reached, aborted)。"""
    robot, config = run.robot, run.cfg
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
            config.budget._replace(speeds=run.speeds, settle_sec=run.stop_sec()),
        )
        if plan.dropped:
            run.log("dropping %s to protect the goal" % plan.dropped)
            run.dropped.extend(plan.dropped)
            pending = [cp for cp in pending if cp.id not in plan.dropped]
        run.log("route %s (~%.0fs)" % (plan.route.order, plan.estimated_sec))
        target = by_id[plan.route.order[0]]
        # 這一點之後還要的秒數 = 整條路線的估計，扣掉去這一點的腿與在這一點停留的時間；
        # 後面還有移動的話，再加上移動必須提早結束的收尾保留（見 move_timeout）。
        run.reserved_sec = max(
            0.0, plan.estimated_sec - plan.route.legs[0].seconds - run.stop_sec()
        )
        if target.id != cps.goal.id:
            run.reserved_sec += config.finish_reserve_sec + config.cancel_reserve_sec
        record = run.visit(target)
        if target.id == cps.goal.id:
            goal_reached = record.notified
            break
        pending = [cp for cp in pending if cp.id != target.id]
    return goal_reached, ""
