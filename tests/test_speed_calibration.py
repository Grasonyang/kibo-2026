"""R2：機器人實際比移動模型慢時，用實測把規劃往慢修；模型準時什麼都不動；最多修到 2 倍。"""

from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.motion import Speeds
from kibo_lab.fake_robot import FakeRobot, FakeRobotConfig
from kibo_lab.scenarios import random_checkpoints_message

NOISY = FakeRobotConfig(position_noise_m=0.05, move_fail_prob=0.1)
WITHOUT = DEFAULT_MISSION._replace(calibrate_speed=False)


def fleet(true_slowdown, mission, n=10, runs=6):
    goals = 0
    scores = []
    calibrated_runs = 0
    for i in range(runs):
        robot = FakeRobot(
            random_checkpoints_message(n, 100 + i),
            NOISY._replace(speeds=Speeds(slowdown=true_slowdown)),
            100 + i,
        )
        report = run_mission(robot, mission)
        goals += report.goal_reached
        scores.append(robot.judge.score())
        calibrated_runs += any("speed calibrated" in line for line in robot.logs)
    return goals, sum(scores) / runs, calibrated_runs


def test_half_speed_robot_reaches_goal_far_more_often_with_calibration():
    goals_off, score_off, _ = fleet(2.0, WITHOUT)
    goals_on, score_on, calibrated = fleet(2.0, DEFAULT_MISSION)
    assert goals_on - goals_off >= 3
    # 沒校正的那一邊到不了 Goal，但移動的逾時不越過時限，仍然準時送出完成回報、保住已通過的點；
    # 所以差距不是「有分對 0 分」，而是多了 Goal 與更多的點。
    assert score_on > score_off * 1.5
    assert calibrated == 6


def test_correct_speed_guess_is_left_alone():
    _, score_off, _ = fleet(1.0, WITHOUT)
    _, score_on, calibrated = fleet(1.0, DEFAULT_MISSION)
    assert calibrated == 0
    assert score_on == score_off


def test_faster_than_expected_robot_is_never_sped_up():
    _, score_off, _ = fleet(0.5, WITHOUT)
    _, score_on, calibrated = fleet(0.5, DEFAULT_MISSION)
    assert calibrated == 0
    assert score_on == score_off


def test_calibration_is_capped_at_twice_the_model():
    robot = FakeRobot(
        random_checkpoints_message(8, 3), NOISY._replace(speeds=Speeds(slowdown=2.5)), 3
    )
    run_mission(robot, DEFAULT_MISSION)
    lines = [line for line in robot.logs if "speed calibrated" in line]
    assert lines
    assert all("x2.00 vs model" in line for line in lines)


def test_a_second_of_overhead_per_move_stays_inside_the_deadband(three_point_message):
    # 每次移動多花 1 秒（模型沒算到的）：一段腿二十幾秒，慢 5% 左右，在 11% 的死區內，不該校正。
    robot = FakeRobot(three_point_message, NOISY._replace(move_overhead_sec=1.0))
    run_mission(robot, DEFAULT_MISSION)
    assert not any("speed calibrated" in line for line in robot.logs)


def test_fifteen_percent_slower_is_outside_the_deadband():
    # 慢 15% 以前落在死區裡（慢 25% 才校正），現在要校正：這是新門檻（慢 11%）的依據。
    quiet = FakeRobotConfig(position_noise_m=0.01, speeds=Speeds(slowdown=1.15))
    robot = FakeRobot(random_checkpoints_message(8, 3), quiet, 3)
    run_mission(robot, DEFAULT_MISSION)
    assert any("speed calibrated" in line and "x1.15" in line for line in robot.logs)


def test_long_leg_gets_a_longer_timeout(three_point_message):
    # 假機器人比模型慢 4 倍（規劃也知道）：一段腿要 120 幾秒，固定 60 s 的逾時會失敗；
    # 逾時跟著估計放大才成功。時間只夠兩段，所以 #1 會被放棄，看 #6。
    slow = FakeRobotConfig(position_noise_m=0.0, speeds=Speeds(slowdown=4.0))
    mission = DEFAULT_MISSION._replace(
        budget=DEFAULT_MISSION.budget._replace(speeds=Speeds(slowdown=4.0))
    )
    robot = FakeRobot(three_point_message, slow)
    run_mission(robot, mission)
    assert any("move to #6 attempt 1: success" in line for line in robot.logs)
    assert 6 in robot.judge.passed_ids


def test_a_timed_out_leg_counts_as_evidence_of_slowness():
    # 比模型慢 4 倍：長一點的腿在 60 s 內到不了，第一次就逾時；逾時本身要讓規劃變慢。
    robot = FakeRobot(
        random_checkpoints_message(8, 3), NOISY._replace(speeds=Speeds(slowdown=4.0)), 3
    )
    run_mission(robot, DEFAULT_MISSION)
    logs = robot.logs
    first_timeout = next(i for i, line in enumerate(logs) if "TIMED OUT, lower bound" in line)
    assert any("speed calibrated" in line for line in logs[first_timeout:])
