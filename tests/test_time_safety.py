"""時間安全：不管機器人偏慢、到點不穩、移動失敗，或幾種一起，完成回報都要在 300 秒內送出。

這些情境來自 sim-bringup-review council 的查證（notes/council/sim-bringup-review/synthesis.md）
與 issue #16 的審查：規劃端不知道機器人偏慢，每點實際停留的時間也比預算估的長。逾時的代價
可能是整場 0 分，所以寧可少去幾個點，最壞時連 Goal 都放棄。

兩層：硬上限（移動的逾時與到點後的等待都不越過時限前的收尾保留）保證準時；
速度校正與停留時間的回饋讓規劃早一點刪點，才到得了 Goal。
"""

import pytest

from kibo.fake_robot import FakeRobot, fake_config
from kibo.geometry import Pose, add
from kibo.checkpoints import parse_checkpoints
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
    ],
)
def test_the_finish_report_is_on_time_even_when_the_plan_is_wrong(
    robot_class, slowdown, move_fail_prob
):
    # 這些情境曾經在 305 秒才送出完成回報：移動的逾時最少給 5 秒，重試也不看剩餘時間。
    # 現在到不了 Goal 就放棄 Goal，已通過的點不會因為逾時而賠掉。
    latest, _, _ = fleet(robot_class, slowdown, move_fail_prob=move_fail_prob)
    assert latest <= LIMIT - 2.0


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
    robot, run, goal = _run_with_seconds_left(NeverSteady, 100.0)
    before = robot.t
    run.settle(goal, wait=False)
    assert robot.t == before


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
