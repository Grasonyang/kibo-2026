"""假機器人自己的行為：測試靠它的設定造情境，所以設定說的事要是真的。

整場任務的行為在 test_mission*.py；這裡直接呼叫 `Robot` 介面的方法，用 `truth()` 看它真正在哪。
"""

import pytest

from conftest import PERFECT
from kibo.checkpoints import parse_checkpoints, target_attitude
from kibo.ctl_result import MOVE_ABORTED, MOVE_INVALID, MOVE_SUCCESS, MOVE_TIMEOUT
from kibo.geometry import Pose, add, distance, quat_angle, rotate
from kibo.judge import judge
from kibo_lab.fake_robot import FakeRobot
from kibo_lab.scenarios import random_checkpoints_message

SIDEWAYS_15CM = (0.0, 0.15, 0.0)
ROLL_15 = PERFECT._replace(residual_roll_deg=15.0, residual_roll_sec=2.0)


@pytest.fixture
def cps(three_point_message):
    return parse_checkpoints(three_point_message)


def target_of(cp):
    return Pose(cp.position, target_attitude(cp))


def test_a_perfect_robot_stops_exactly_on_the_target(three_point_message, cps):
    robot = FakeRobot(three_point_message, PERFECT)
    target = target_of(cps.by_id(1))
    assert robot.move_to(target, 100.0) == MOVE_SUCCESS
    assert robot.truth().position == target.position
    assert quat_angle(robot.truth().orientation, target.orientation) == pytest.approx(0.0, abs=1e-6)


def test_the_arrival_offset_is_in_the_frame_of_the_target_attitude(three_point_message, cps):
    robot = FakeRobot(three_point_message, PERFECT._replace(arrival_offsets_m=(SIDEWAYS_15CM,)))
    target = target_of(cps.by_id(1))
    robot.move_to(target, 100.0)
    expected = add(target.position, rotate(target.orientation, SIDEWAYS_15CM))
    assert distance(robot.truth().position, expected) == pytest.approx(0.0, abs=1e-9)
    robot.move_to(target, 100.0)  # 只給一個偏移：之後每次都用它
    assert distance(robot.truth().position, expected) == pytest.approx(0.0, abs=1e-9)


def test_later_arrivals_at_the_same_target_use_the_later_offsets(three_point_message, cps):
    second_try = PERFECT._replace(arrival_offsets_m=(SIDEWAYS_15CM, (0.0, 0.0, 0.0)))
    robot = FakeRobot(three_point_message, second_try)
    first, other = target_of(cps.by_id(1)), target_of(cps.by_id(6))
    robot.move_to(first, 100.0)
    assert distance(robot.truth().position, first.position) == pytest.approx(0.15)
    robot.move_to(other, 100.0)  # 別的目標有自己的次數
    assert distance(robot.truth().position, other.position) == pytest.approx(0.15)
    robot.move_to(first, 100.0)
    assert distance(robot.truth().position, first.position) == pytest.approx(0.0, abs=1e-9)


def test_a_robot_still_turning_is_seen_rolled_until_the_time_is_up(three_point_message, cps):
    robot = FakeRobot(three_point_message, ROLL_15)
    cp = cps.by_id(1)
    robot.move_to(target_of(cp), 100.0)
    seen = robot.pose()
    assert seen is not None
    assert judge(seen, cp).roll_deg == pytest.approx(15.0, abs=0.01)
    assert judge(robot.truth(), cp).level == 2
    robot.sleep(2.0)
    assert judge(robot.truth(), cp).level == 3
    assert judge(robot.truth(), cp).roll_deg == pytest.approx(0.0, abs=0.01)


def test_the_judge_sees_the_roll_of_a_notification_sent_while_turning(three_point_message, cps):
    # 官方每點只判第一次：還在轉就通知，這一點就定在 Lv2，轉完也不會變。
    robot = FakeRobot(three_point_message, ROLL_15)
    robot.mission_start()
    robot.move_to(target_of(cps.by_id(1)), 100.0)
    assert robot.notify_checkpoint(1) is True
    assert robot.judge.passed_ids == [1] and robot.judge.passed_levels == [2]


def test_the_judge_uses_the_pose_at_the_moment_the_notification_was_sent(three_point_message, cps):
    # 通知來回 0.3 秒；送出時還在轉（剩 0.1 秒），回來時已經轉完：算送出當下的。
    robot = FakeRobot(three_point_message, ROLL_15)
    robot.mission_start()
    robot.move_to(target_of(cps.by_id(1)), 100.0)
    robot.sleep(1.9)
    robot.notify_checkpoint(1)
    assert robot.judge.passed_levels == [2]


def test_a_notification_sent_after_the_turn_is_done_gets_level_3(three_point_message, cps):
    robot = FakeRobot(three_point_message, ROLL_15)
    robot.mission_start()
    robot.move_to(target_of(cps.by_id(1)), 100.0)
    robot.sleep(2.0)
    robot.notify_checkpoint(1)
    assert robot.judge.passed_levels == [3]


def test_the_finish_report_is_judged_with_the_roll_too():
    # 滾轉 35° 超出最寬的餘裕：還在轉就送完成回報，Goal 不算到；等轉完再送就到。
    # 共用的三點場景裡 Goal 的滾轉量測退化成 0（simulator-internals 的 J5），所以用產生器的場景。
    message = random_checkpoints_message(3, seed=5)
    goal = parse_checkpoints(message).goal
    too_early = FakeRobot(message, ROLL_15._replace(residual_roll_deg=35.0))
    too_early.mission_start()
    too_early.move_to(target_of(goal), 200.0)
    too_early.mission_finish()
    assert not too_early.judge.goal_reached

    patient = FakeRobot(message, ROLL_15._replace(residual_roll_deg=35.0))
    patient.mission_start()
    patient.move_to(target_of(goal), 200.0)
    patient.sleep(2.0)
    patient.mission_finish()
    assert patient.judge.goal_reached


@pytest.mark.parametrize("result", [MOVE_INVALID, MOVE_ABORTED])
def test_a_forced_failure_does_not_move_the_robot_or_the_clock(three_point_message, cps, result):
    robot = FakeRobot(three_point_message, PERFECT._replace(move_always=result))
    before = robot.truth()
    assert robot.move_to(target_of(cps.by_id(1)), 40.0) == result
    assert robot.truth() == before and robot.now() == 0.0
    assert robot.move_calls == 1


def test_a_forced_timeout_spends_the_whole_timeout(three_point_message, cps):
    robot = FakeRobot(three_point_message, PERFECT._replace(move_always=MOVE_TIMEOUT))
    before = robot.truth()
    assert robot.move_to(target_of(cps.by_id(1)), 40.0) == MOVE_TIMEOUT
    assert robot.truth() == before and robot.now() == 40.0


def test_reconfiguring_changes_the_robot_from_then_on(three_point_message, cps):
    robot = FakeRobot(three_point_message, PERFECT)
    robot.mission_start()
    robot.reconfigure(notify_sec=5.0)
    assert robot.notify_checkpoint(1, 2.0) is False  # 通知變慢了：2 秒內回不來
    assert robot.now() == 2.0
