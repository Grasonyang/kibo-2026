import pytest

from conftest import PERFECT
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.motion import Speeds
from kibo_lab.fake_robot import FakeRobot
from kibo_lab.scenarios import random_checkpoints_message


def test_perfect_robot_passes_every_checkpoint_at_level_3(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished and report.goal_reached
    assert sorted(robot.judge.passed_ids) == [1, 6, 12]
    assert robot.judge.passed_levels == [3, 3, 3]
    assert report.dropped == []
    assert report.elapsed_sec < 300.0


def test_score_rewards_remaining_time(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    # 三個 Lv3（30 分）加 Goal（20 分），再乘上「1 + 剩餘比例」的倍率。
    expected = 50.0 * (1.0 + robot.judge.remaining_at_finish() / 300.0)
    assert robot.judge.score() == pytest.approx(expected)
    assert 50.0 < robot.judge.score() <= 100.0


def test_moves_that_always_fail_still_end_within_bounds(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT._replace(move_fail_prob=1.0))
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished
    assert not report.goal_reached
    # 每個點最多 move.max_attempts 次，三個點
    assert robot.move_calls <= 3 * DEFAULT_MISSION.move.max_attempts


def test_flaky_checkpoint_service_is_retried(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT._replace(checkpoints_fail_times=2))
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.goal_reached
    assert robot.checkpoints_calls == 3


def test_slow_robot_drops_checkpoints_but_still_reaches_goal_in_time():
    message = random_checkpoints_message(12, seed=7)
    slow = PERFECT._replace(speeds=Speeds(slowdown=3.0))
    # 規劃也知道自己慢，才會提前放棄
    cfg = DEFAULT_MISSION._replace(budget=DEFAULT_MISSION.budget._replace(speeds=slow.speeds))
    robot = FakeRobot(message, slow, seed=7)
    report = run_mission(robot, cfg)
    assert report.finished and report.goal_reached
    assert report.dropped  # 來不及，所以放棄了一些
    assert report.elapsed_sec <= 300.0


def test_stop_request_ends_the_mission_without_finishing(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    robot.stop = True
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.aborted == "stop requested"
    assert robot.judge.finished_at is None


def test_random_scenarios_are_valid_and_reproducible():
    a = random_checkpoints_message(8, seed=3)
    b = random_checkpoints_message(8, seed=3)
    assert a == b
    robot = FakeRobot(a, PERFECT, seed=3)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.goal_reached
    assert len(robot.judge.passed_ids) == 8
