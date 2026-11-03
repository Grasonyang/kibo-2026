from kibo.fake_robot import FakeRobot, FakeRobotConfig
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.planner import Speeds
from kibo.scenarios import random_checkpoints_message

PERFECT = FakeRobotConfig(position_noise_m=0.0, attitude_noise_deg=0.0, nav_jitter_m=0.0)


def test_perfect_robot_passes_every_checkpoint_at_level_3(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished and report.goal_reached
    assert sorted(robot.passed_ids) == [1, 6, 12]
    assert robot.passed_levels == [3, 3, 3]
    assert report.dropped == []
    assert report.elapsed_sec < 300.0


def test_score_rewards_remaining_time(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    # 三個 Lv3（30 分）加 Goal（20 分），再乘上 1 到 2 之間的倍率。
    assert 50.0 < robot.score() <= 100.0


def test_moves_that_always_fail_still_end_within_bounds(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT._replace(move_fail_prob=1.0))
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished
    assert not report.goal_reached
    # 每個點最多 max_move_attempts 次，三個點
    assert robot.move_calls <= 3 * DEFAULT_MISSION.max_move_attempts


def test_flaky_checkpoint_service_is_retried(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT._replace(checkpoints_fail_times=2))
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.goal_reached
    assert robot.checkpoints_calls == 3


def test_slow_robot_drops_checkpoints_but_still_reaches_goal_in_time():
    message = random_checkpoints_message(12, seed=7)
    slow = PERFECT._replace(speeds=Speeds(linear_mps=0.03, angular_dps=5.0))
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
    assert robot.finished_at is None


def test_random_scenarios_are_valid_and_reproducible():
    a = random_checkpoints_message(8, seed=3)
    b = random_checkpoints_message(8, seed=3)
    assert a == b
    robot = FakeRobot(a, PERFECT, seed=3)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.goal_reached
    assert len(robot.passed_ids) == 8
