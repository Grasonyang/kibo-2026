"""時間安全：不管機器人偏慢、到點不穩、移動失敗，或幾種一起，完成回報都要在 300 秒內送出。

這些情境來自 sim-bringup-review council 的查證（notes/council/sim-bringup-review/synthesis.md）
與 issue #16 的審查：規劃端不知道機器人偏慢，每點實際停留的時間也比預算估的長。逾時的代價
可能是整場 0 分，所以寧可少去幾個點，最壞時連 Goal 都放棄。

兩層：硬上限（移動的逾時與到點後的等待都不越過時限前的收尾保留）保證準時；
速度校正與停留時間的回饋讓規劃早一點刪點，才到得了 Goal。
"""

import os
import re

import pytest

from kibo import mission as mission_module
from kibo.checkpoints import parse_checkpoints, target_attitude
from kibo.ctl_result import MOVE_ABORTED, MOVE_SUCCESS, MOVE_TIMEOUT
from kibo.fake_robot import FakeRobot, fake_config
from kibo.geometry import Pose, add
from kibo.mission import DEFAULT_MISSION, _Run, run_mission
from kibo.motion import Speeds
from kibo.scenarios import random_checkpoints_message

LIMIT = DEFAULT_MISSION.time_limit_sec
COUNTS = (8, 10, 12)
SEEDS = range(20)  # 正常情況的比較用全部 20 個；其他情境用前 10 個就夠
BASE = fake_config(0.01, 0.0, 1.0)  # 到點誤差 1 cm、不失敗、與模型同速
# 收緊之前（origin/main ff08a73），正常機器人在這 20 個場景平均通過幾點。
# 這是假機器人的快照：改了 fake_robot 或 scenarios 就要重算。
BEFORE = {10: 8.9, 12: 9.1}


class NeverSteady(FakeRobot):
    """到點後導航讀數一筆正常、一筆偏 0.5 m，永遠湊不滿連續 5 筆；也沒有尾段紀錄。"""

    reads = 0

    def pose(self):
        pose = super().pose()
        self.reads += 1
        if pose is not None and self.reads % 2:
            return Pose(add(pose.position, (0.0, 0.0, 0.5)), pose.orientation, pose.stamp)
        return pose

    def recent_poses(self, seconds):
        return []


def slow_after(start_sec, slowdown, base=FakeRobot):
    """任務進行到 start_sec 之後才變慢的機器人：前面量到的速度不再可信。"""

    class SuddenlySlow(base):
        def move_to(self, target, timeout_sec):
            if self.t >= start_sec:
                self.cfg = self.cfg._replace(speeds=Speeds(slowdown=slowdown))
            return super().move_to(target, timeout_sec)

    return SuddenlySlow


def slow_to_cancel(base=FakeRobot, cancel_sec=5.2):
    """移動逾時之後，取消還要再花 cancel_sec 才回來（節點最多等 CANCEL_WAIT_SEC 加一次輪詢）。"""

    class SlowToCancel(base):
        def move_to(self, target, timeout_sec):
            result = super().move_to(target, timeout_sec)
            if result == MOVE_TIMEOUT:
                self.t += cancel_sec
            return result

    return SlowToCancel


def unsteady_from(first_bad_point, base=FakeRobot):
    """前幾個點正常，從第 first_bad_point 個點（0 起算）開始到點後永遠不穩。"""

    class UnsteadyLater(base):
        reads = 0

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.targets = []  # 去過的目標位置，用來數現在是第幾個點

        def _bad(self):
            return len(self.targets) > first_bad_point

        def move_to(self, target, timeout_sec):
            key = tuple(round(x, 3) for x in target.position)
            if key not in self.targets:
                self.targets.append(key)
            return super().move_to(target, timeout_sec)

        def pose(self):
            pose = super().pose()
            self.reads += 1
            if pose is not None and self._bad() and self.reads % 2:
                return Pose(add(pose.position, (0.0, 0.0, 0.5)), pose.orientation, pose.stamp)
            return pose

        def recent_poses(self, seconds):
            return [] if self._bad() else super().recent_poses(seconds)

    return UnsteadyLater


class NoNavigation(FakeRobot):
    """導航完全沒有資料。"""

    def pose(self):
        return None

    def recent_poses(self, seconds):
        return []


def fleet(robot_class, slowdown, seeds=range(10), move_fail_prob=0.0):
    """回傳 (最晚的完成時刻, 到達 Goal 的場數, 各點數的平均通過點數)。"""
    config = BASE._replace(speeds=Speeds(slowdown=slowdown), move_fail_prob=move_fail_prob)
    latest, goals, mean_points = 0.0, 0, {}
    for count in COUNTS:
        passed = 0
        for seed in seeds:
            robot = robot_class(random_checkpoints_message(count, seed), config, seed)
            run_mission(robot, DEFAULT_MISSION)
            assert robot.finished_at is not None
            latest = max(latest, robot.finished_at)
            goals += robot.goal_reached
            passed += len(robot.passed_ids)
        mean_points[count] = passed / float(len(seeds))
    return latest, goals, mean_points


@pytest.mark.parametrize("slowdown", [1.11, 1.24, 1.5])
def test_a_robot_slower_than_the_model_still_finishes_in_time(slowdown):
    # 慢 20% 到 24% 曾經落在校正的死區裡（慢 25% 才校正），完成時間貼到 298 秒，偶爾超過。
    # 1.11 是現在死區的邊緣（慢 11% 以內不校正），1.5 是校正會啟動的情況。
    latest, goals, _ = fleet(FakeRobot, slowdown)
    assert latest <= LIMIT - 5.0
    assert goals == len(COUNTS) * 10


def test_a_robot_that_never_settles_still_finishes_in_time():
    latest, _, _ = fleet(NeverSteady, 1.0)
    assert latest <= LIMIT - 2.0


def test_slow_and_never_settling_together_still_finish_in_time():
    # 兩者疊加時曾經有三成的場次超時：每點實際停留十幾秒，預算卻只估 1 秒。
    latest, _, _ = fleet(NeverSteady, 1.2)
    assert latest <= LIMIT - 2.0


def test_a_well_behaved_robot_visits_as_many_points_as_before():
    # 收緊時間安全不能讓正常情況少去點。BEFORE 是收緊之前、同樣 20 個場景的平均。
    _, goals, mean_points = fleet(FakeRobot, 1.0, SEEDS)
    assert goals == len(COUNTS) * len(SEEDS)
    assert mean_points[8] == 8.0
    assert mean_points[10] >= BEFORE[10] and mean_points[12] >= BEFORE[12]


# ---- 硬上限：規劃再怎麼錯，完成回報也準時 ----


@pytest.mark.parametrize(
    "robot_class, slowdown, move_fail_prob",
    [
        (FakeRobot, 2.5, 0.0),  # 比校正認得的上限（2 倍）還慢
        (slow_after(100.0, 1.5), 1.0, 0.0),  # 中途才變慢，校正來不及反應
        (slow_after(120.0, 2.0), 1.0, 0.0),
        (slow_after(150.0, 1.5, NeverSteady), 1.0, 0.0),
        (FakeRobot, 1.0, 0.3),  # 移動常常失敗，重試會吃時間
        (NeverSteady, 1.11, 0.2),
        # 逾時之後取消還要 5 秒多：收尾保留裡的 cancel_reserve_sec 就是留給它的
        (slow_to_cancel(), 2.5, 0.0),
        (slow_to_cancel(slow_after(120.0, 2.0)), 1.0, 0.0),
        (slow_to_cancel(slow_after(200.0, 1.5, NeverSteady)), 1.0, 0.3),
        (NoNavigation, 1.3, 0.0),  # 讀不到導航時的重試也不能越過時限
        (slow_to_cancel(NoNavigation), 1.0, 0.3),
    ],
)
def test_the_finish_report_is_on_time_even_when_the_plan_is_wrong(
    robot_class, slowdown, move_fail_prob
):
    # 這些情境曾經在 305 秒才送出完成回報：移動的逾時最少給 5 秒，重試也不看剩餘時間。
    # 現在到不了 Goal 就放棄 Goal，已通過的點不會因為逾時而賠掉。
    latest, _, _ = fleet(robot_class, slowdown, move_fail_prob=move_fail_prob)
    assert latest <= LIMIT - 1.0


def _run_with_seconds_left(robot_class, seconds_left):
    message = random_checkpoints_message(3, 1)
    robot = robot_class(message, BASE, 1)
    run = _Run(robot, DEFAULT_MISSION)
    robot.t = LIMIT - seconds_left
    return robot, run, parse_checkpoints(message).goal


def test_no_move_is_sent_when_it_could_not_be_cancelled_before_the_limit():
    reserve = DEFAULT_MISSION.finish_reserve_sec + DEFAULT_MISSION.cancel_reserve_sec
    robot, run, goal = _run_with_seconds_left(FakeRobot, reserve + 0.5)
    assert run.move(goal, DEFAULT_MISSION.max_move_attempts) is False
    assert robot.move_calls == 0
    assert robot.t == LIMIT - (reserve + 0.5)  # 沒有花時間


def test_a_move_timeout_leaves_room_to_cancel_and_report():
    reserve = DEFAULT_MISSION.finish_reserve_sec + DEFAULT_MISSION.cancel_reserve_sec
    robot, run, goal = _run_with_seconds_left(FakeRobot, 100.0)
    assert run.move_timeout() == pytest.approx(DEFAULT_MISSION.move_timeout_sec)
    robot.t = LIMIT - 20.0
    assert run.move_timeout() == pytest.approx(20.0 - reserve)


def test_waiting_at_the_goal_stops_before_the_limit():
    # 到 Goal 時餘裕就是剩餘時間；讀數一直不穩時曾經等到只剩 0.9 秒才送完成回報。
    robot, run, goal = _run_with_seconds_left(NeverSteady, 5.0)
    settled = run.settle(goal)
    assert not settled.stable
    assert LIMIT - robot.t >= DEFAULT_MISSION.finish_reserve_sec


def test_a_point_the_move_did_not_reach_is_not_waited_on():
    # 沒移動成功的點不回報（手冊 6.5），等它穩定是白花時間：只讀一筆。
    class MovesAlwaysFail(NeverSteady):
        def move_to(self, target, timeout_sec):
            self.move_calls += 1
            return MOVE_ABORTED

    robot, run, goal = _run_with_seconds_left(MovesAlwaysFail, 100.0)
    before = robot.t
    record = run.visit(goal)
    assert not record.moved and not record.notified
    assert robot.move_calls == DEFAULT_MISSION.max_move_attempts
    assert robot.t == before


def test_waiting_at_a_waypoint_leaves_the_goal_leg_its_reserve():
    # 中途點的等待若把餘裕花到見底，Goal 那一段就得在「時限前 8 秒」之前剛好飛完，
    # 模型差一兩秒就到不了。餘裕要先扣掉後面移動需要的收尾保留。
    _, goals, _ = fleet(unsteady_from(4), 1.2, seeds=range(30))
    assert goals == len(COUNTS) * 30


def test_the_camera_correction_is_limited_by_slack_too():
    class SeesMarkerSlightlyOff(FakeRobot):
        relative_timeouts = ()
        seen = (0.0, 0.0, 0.0)

        def marker_in_body(self, marker_id):
            return self.seen

        def move_relative(self, delta, timeout_sec):
            self.relative_timeouts += (timeout_sec,)
            return MOVE_SUCCESS

    robot, run, goal = _run_with_seconds_left(SeesMarkerSlightlyOff, 100.0)
    run.cfg = DEFAULT_MISSION._replace(camera_fix_max_m=0.1)
    expected = mission_module.expected_marker_in_body(
        goal.position, target_attitude(goal), goal.marker_position
    )
    robot.seen = add(expected, (0.0, 0.02, 0.0))
    run.reserved_sec = 80.0  # 餘裕 20 秒
    assert run.camera_fix(goal)
    assert robot.relative_timeouts == (pytest.approx(20.0 - DEFAULT_MISSION.hurry_sec),)


def test_reading_the_pose_does_not_retry_inside_the_finish_reserve():
    robot, run, _ = _run_with_seconds_left(NoNavigation, DEFAULT_MISSION.finish_reserve_sec - 0.5)
    before = robot.t
    assert run.current_pose() is None
    assert robot.t == before


def test_the_cancel_reserve_covers_how_long_the_node_waits_for_a_cancel():
    # ros/user_node.py 不能在這裡匯入（要 rospy），所以讀原始碼比對那個常數。
    node = os.path.join(os.path.dirname(__file__), "..", "ros", "user_node.py")
    with open(node) as source:
        found = re.search(r"^CANCEL_WAIT_SEC = ([0-9.]+)", source.read(), re.MULTILINE)
    assert found
    assert DEFAULT_MISSION.cancel_reserve_sec >= float(found.group(1))


def test_the_short_move_that_refines_a_point_is_not_calibration_evidence():
    # 修正用的再移動，起點是一筆沒穩定的讀數，算出來的預測秒數不可信：曾經因為一段
    # 「預測 14 秒、實際 4.5 秒」的再移動，把已經校正到 1.17 的速度拉回 1.00，Goal 那一段就估短了。
    slow = BASE._replace(speeds=Speeds(slowdown=1.2))
    for seed in range(6):
        robot = NeverSteady(random_checkpoints_message(8, seed), slow, seed)
        run_mission(robot, DEFAULT_MISSION)
        calibrated = [line for line in robot.logs if "speed calibrated" in line]
        assert calibrated
        assert not any("-> 1.00" in line for line in calibrated)


# ---- 停留時間的回饋 ----


def _stop_sec_after(stops):
    robot, run, _ = _run_with_seconds_left(FakeRobot, 100.0)
    run.stops = list(stops)
    return run.stop_sec()


def test_one_long_stop_does_not_change_the_budget():
    # 2026-11-11 本機 veryhard：第一點等了 3.5 秒，用平均的話之後每點都留 3.5 秒，
    # 多刪一個點，結果提早 60 秒結束。
    planned = DEFAULT_MISSION.budget.settle_sec
    assert _stop_sec_after([]) == planned
    assert _stop_sec_after([15.0]) == planned
    assert _stop_sec_after([0.3, 15.0, 0.3]) == planned


def test_two_long_stops_in_the_last_three_raise_the_budget():
    assert _stop_sec_after([15.0, 12.0]) == 12.0
    assert _stop_sec_after([0.3, 15.0, 12.0]) == 12.0
    assert _stop_sec_after([15.0, 0.3, 12.0]) == 12.0


def test_the_budget_never_goes_below_the_planned_stop():
    assert _stop_sec_after([0.1, 0.1, 0.1]) == DEFAULT_MISSION.budget.settle_sec


def test_one_unsteady_point_costs_about_one_point_not_three():
    class FirstPointUnsteady(NeverSteady):
        def _bad(self):
            return not self.passed_ids and not self.judged_ids and self.move_calls <= 2

        def pose(self):
            return super().pose() if self._bad() else FakeRobot.pose(self)

        def recent_poses(self, seconds):
            return [] if self._bad() else FakeRobot.recent_poses(self, seconds)

    _, goals, usual = fleet(FakeRobot, 1.0)
    _, goals_unsteady, unsteady = fleet(FirstPointUnsteady, 1.0)
    assert goals_unsteady == goals
    for count in COUNTS:
        assert unsteady[count] >= usual[count] - 1.5


# ---- 通知本身卡住（issue #17）----


def notify_slows_down(after_sec, notify_sec, base=FakeRobot):
    """任務進行到 after_sec 之後，每一次通過通知都要 notify_sec 才回來（伺服器或網路出問題）。"""

    class SlowNotify(base):
        def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
            if self.t > after_sec:
                self.cfg = self.cfg._replace(notify_sec=notify_sec)
            return super().notify_checkpoint(checkpoint_id, timeout_sec)

    return SlowNotify


@pytest.mark.parametrize(
    "robot_class, slowdown",
    [
        (notify_slows_down(150.0, 15.3), 1.0),  # 曾經 90 場裡 3 場在 302.9 秒才完成
        (notify_slows_down(0.0, 4.0, NeverSteady), 1.2),  # 3 秒以上就會超時的門檻之上
        (notify_slows_down(200.0, 60.0), 1.0),  # 比任務層給的上限還久：每次都逾時
        (slow_to_cancel(notify_slows_down(100.0, 8.0)), 1.5),
    ],
)
def test_a_stuck_notification_cannot_delay_the_finish_report(robot_class, slowdown):
    latest, _, _ = fleet(robot_class, slowdown)
    assert latest <= LIMIT - 0.5


def test_a_notification_gets_no_more_time_than_is_left_before_the_finish_call():
    class RecordsTimeout(FakeRobot):
        timeouts = ()

        def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
            self.timeouts += (timeout_sec,)
            return super().notify_checkpoint(checkpoint_id, timeout_sec)

    robot, run, goal = _run_with_seconds_left(RecordsTimeout, 100.0)
    assert run.notify(goal)
    robot.t = LIMIT - 4.0
    assert run.notify(goal)
    assert robot.timeouts == (
        pytest.approx(DEFAULT_MISSION.notify_timeout_sec),
        pytest.approx(4.0 - DEFAULT_MISSION.finish_call_sec),
    )


def test_no_notification_is_sent_when_there_is_no_time_for_it():
    class CountsNotifies(FakeRobot):
        notifies = 0

        def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
            self.notifies += 1
            return super().notify_checkpoint(checkpoint_id, timeout_sec)

    robot, run, goal = _run_with_seconds_left(CountsNotifies, DEFAULT_MISSION.finish_call_sec)
    before = robot.t
    assert run.notify(goal) is False
    assert robot.notifies == 0
    assert robot.t == before


def test_a_notification_that_times_out_is_retried_only_while_time_remains():
    class NeverAnswers(FakeRobot):
        notifies = 0

        def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
            self.notifies += 1
            return super().notify_checkpoint(checkpoint_id, timeout_sec)

    slow = BASE._replace(notify_sec=1000.0)
    robot = NeverAnswers(random_checkpoints_message(3, 1), slow, 1)
    run = _Run(robot, DEFAULT_MISSION)
    goal = parse_checkpoints(random_checkpoints_message(3, 1)).goal
    robot.t = LIMIT - 6.0
    assert run.notify(goal) is False
    assert robot.notifies == 1  # 第一次就把時間用到只剩完成回報要的，不再試第二次
    assert LIMIT - robot.t >= DEFAULT_MISSION.finish_call_sec


def test_the_pause_before_a_retry_counts_against_the_time_left():
    class NeverAnswers(FakeRobot):
        notifies = 0

        def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
            self.notifies += 1
            return super().notify_checkpoint(checkpoint_id, timeout_sec)

    message = random_checkpoints_message(3, 1)
    robot = NeverAnswers(message, BASE._replace(notify_sec=1000.0), 1)
    quick = DEFAULT_MISSION._replace(notify_timeout_sec=2.0)
    run = _Run(robot, quick)
    # 第一次逾時後剩 1.3 秒：扣掉完成回報的 1 秒還有 0.3 秒，看似夠再試一次，
    # 但重試前要先停 0.25 秒，停完就不夠了。
    robot.t = LIMIT - 3.3
    assert run.notify(parse_checkpoints(message).goal) is False
    assert robot.notifies == 1
    assert LIMIT - robot.t >= quick.finish_call_sec


def test_the_fake_judge_never_sees_a_notification_that_timed_out(three_point_message):
    robot = FakeRobot(three_point_message, BASE._replace(notify_sec=5.0))
    robot.mission_start()
    assert robot.notify_checkpoint(1, 2.0) is False
    assert robot.t == 2.0 and robot.judged_ids == []
    assert robot.notify_checkpoint(1, 6.0) is True
    assert robot.judged_ids == [1]


def test_the_marker_log_is_skipped_inside_the_finish_reserve():
    class CountsLooks(FakeRobot):
        looks = 0

        def marker_in_body(self, marker_id):
            self.looks += 1
            return None

    robot, run, goal = _run_with_seconds_left(CountsLooks, DEFAULT_MISSION.finish_reserve_sec - 0.5)
    run.last_pose = Pose(goal.position, target_attitude(goal))
    run.log_marker(goal)
    assert robot.looks == 0
    robot.t = LIMIT - 50.0
    run.log_marker(goal)
    assert robot.looks == 1
