"""R2：規劃用的速度猜錯時，用實測往慢修；猜對時什麼都不動。"""

from kibo.fake_robot import FakeRobot, FakeRobotConfig
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.planner import Speeds
from kibo.scenarios import random_checkpoints_message

NOISY = FakeRobotConfig(position_noise_m=0.05, move_fail_prob=0.1)


def fleet(true_speed, mission, n=12, runs=6):
    goals = 0
    scores = []
    calibrated_runs = 0
    for i in range(runs):
        robot = FakeRobot(
            random_checkpoints_message(n, 100 + i),
            NOISY._replace(speeds=Speeds(true_speed, 20.0)),
            100 + i,
        )
        report = run_mission(robot, mission)
        goals += report.goal_reached
        scores.append(robot.score())
        calibrated_runs += any("speed calibrated" in line for line in robot.logs)
    return goals, sum(scores) / runs, calibrated_runs


def test_half_speed_robot_reaches_goal_far_more_often_with_calibration():
    without = DEFAULT_MISSION._replace(calibrate_speed=False)
    goals_off, score_off, _ = fleet(0.05, without)
    goals_on, score_on, calibrated = fleet(0.05, DEFAULT_MISSION)
    assert goals_on >= goals_off and goals_on >= 5
    assert score_on > score_off * 1.2  # 20 場的矩陣是 1.57 倍；6 場留餘裕
    assert calibrated == 6  # 每場都偵測到變慢


def test_correct_speed_guess_is_left_alone():
    without = DEFAULT_MISSION._replace(calibrate_speed=False)
    _, score_off, _ = fleet(0.1, without)
    _, score_on, calibrated = fleet(0.1, DEFAULT_MISSION)
    assert calibrated == 0
    assert score_on == score_off


def test_long_leg_gets_a_longer_timeout(three_point_message):
    # 假機器人慢到 0.02 m/s：1.5 m 的腿要 78 s，固定 60 s 的逾時會失敗；估計腿長放大後才成功。
    slow = FakeRobotConfig(position_noise_m=0.0, speeds=Speeds(0.02, 20.0))
    mission = DEFAULT_MISSION._replace(
        budget=DEFAULT_MISSION.budget._replace(speeds=Speeds(0.02, 20.0))
    )
    robot = FakeRobot(three_point_message, slow)
    run_mission(robot, mission)
    assert any("timeout" not in line for line in robot.logs if "move to #1" in line)
    assert 1 in robot.passed_ids
