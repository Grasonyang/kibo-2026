"""R2：規劃用的速度猜錯時，用實測往慢修；猜對時什麼都不動；極慢也不低於預設一半。"""

from kibo.fake_robot import FakeRobot, FakeRobotConfig
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.planner import Speeds
from kibo.scenarios import random_checkpoints_message

NOISY = FakeRobotConfig(position_noise_m=0.05, move_fail_prob=0.1)
WITHOUT = DEFAULT_MISSION._replace(calibrate_speed=False)


def fleet(true_speed, mission, n=8, runs=6):
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
    goals_off, score_off, _ = fleet(0.05, WITHOUT)
    goals_on, score_on, calibrated = fleet(0.05, DEFAULT_MISSION)
    assert goals_on - goals_off >= 3  # 8 點：不校正約 1/6，校正約 6/6
    assert score_on > score_off * 2.0
    assert calibrated == 6


def test_correct_speed_guess_is_left_alone():
    _, score_off, _ = fleet(0.1, WITHOUT)
    _, score_on, calibrated = fleet(0.1, DEFAULT_MISSION)
    assert calibrated == 0
    assert score_on == score_off


def test_faster_than_expected_robot_is_never_sped_up():
    _, score_off, _ = fleet(0.2, WITHOUT)
    _, score_on, calibrated = fleet(0.2, DEFAULT_MISSION)
    assert calibrated == 0
    assert score_on == score_off


def test_calibration_never_goes_below_half_of_the_default():
    robot = FakeRobot(
        random_checkpoints_message(8, 3), NOISY._replace(speeds=Speeds(0.04, 20.0)), 3
    )
    run_mission(robot, DEFAULT_MISSION)
    lines = [line for line in robot.logs if "speed calibrated" in line]
    assert lines
    assert all("x2.00 vs model" in line for line in lines)  # 上限 2 倍 = 速度不低於 0.05


def test_a_single_short_leg_with_overhead_does_not_trigger_calibration(three_point_message):
    # 三點場景的腿都短（< 1.2 m）：含 3 秒起停的實測比模型慢，但累積不到 20 秒模型時間，不該校正。
    robot = FakeRobot(three_point_message, NOISY._replace(speeds=Speeds(0.1, 15.0)))
    run_mission(robot, DEFAULT_MISSION)
    assert not any("speed calibrated" in line for line in robot.logs)


def test_long_leg_gets_a_longer_timeout(three_point_message):
    # 假機器人慢到 0.02 m/s：1.5 m 的腿要 78 s，固定 60 s 的逾時會失敗；估計腿長放大後才成功。
    slow = FakeRobotConfig(position_noise_m=0.0, speeds=Speeds(0.02, 20.0))
    mission = DEFAULT_MISSION._replace(
        budget=DEFAULT_MISSION.budget._replace(speeds=Speeds(0.02, 20.0))
    )
    robot = FakeRobot(three_point_message, slow)
    run_mission(robot, mission)
    assert any("move to #1 attempt 1: success" in line for line in robot.logs)
    assert 1 in robot.passed_ids


def test_a_timed_out_leg_counts_as_evidence_of_slowness():
    # 真速 0.03 m/s：1.5 m 以上的腿在 60 s 內到不了，第一次就逾時；逾時本身要讓速度估計變慢。
    robot = FakeRobot(
        random_checkpoints_message(8, 3), NOISY._replace(speeds=Speeds(0.03, 20.0)), 3
    )
    run_mission(robot, DEFAULT_MISSION)
    logs = robot.logs
    first_timeout = next(i for i, line in enumerate(logs) if "TIMED OUT, lower bound" in line)
    assert any("speed calibrated" in line for line in logs[first_timeout:])
