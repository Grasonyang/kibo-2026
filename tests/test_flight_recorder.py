"""R4：校準與飛行記錄——穩定判定只計新資料、探針旗標、沒成功移動不回報、log 可算速度。"""

from kibo.fake_robot import FakeRobot, FakeRobotConfig
from kibo.judge import Pose
from kibo.mission import DEFAULT_MISSION, MOVE_INVALID, run_mission

PERFECT = FakeRobotConfig(position_noise_m=0.0, attitude_noise_deg=0.0, nav_jitter_m=0.0)


class StaleNavRobot(FakeRobot):
    """導航永遠回同一筆資料（stamp 不變）。"""

    def pose(self):
        p = super().pose()
        assert p is not None
        return Pose(p.position, p.orientation, stamp=0.0)


def test_repeated_navigation_sample_never_counts_as_stable(three_point_message):
    robot = StaleNavRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert all(not v.stable for v in report.visits)


class ParkedAtFirstCheckpoint(FakeRobot):
    """已經停在 CheckPoint 1 的位置上，但每次移動都回 INVALID。"""

    def __init__(self, message, config, seed=0):
        super().__init__(message, config, seed)
        cp = self.checkpoints.by_id(1)
        self.true_pose = Pose(cp.position, cp.attitude)

    def move_to(self, target, timeout_sec):
        self.move_calls += 1
        return MOVE_INVALID


def test_no_notification_without_a_successful_move_even_if_judge_passes(three_point_message):
    robot = ParkedAtFirstCheckpoint(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    first = next(v for v in report.visits if v.checkpoint_id == 1)
    assert first.judged_level == 3 and not first.moved and not first.notified


def test_probe_flag_notifies_even_when_move_failed_or_level_is_zero(three_point_message):
    robot = ParkedAtFirstCheckpoint(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION._replace(notify_even_if_level0=True))
    assert any(v.notified for v in report.visits)
    assert any("PROBE FLAGS ON" in line for line in robot.logs)


def test_skip_one_waypoint_probe_leaves_exactly_one_out(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION._replace(skip_one_waypoint=True))
    assert report.goal_reached
    assert len(robot.passed_ids) == 2


def test_deliberate_late_probe_finishes_after_the_limit(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION._replace(deliberate_late_after=1))
    assert robot.finished_at is not None and robot.finished_at > 300.0


def test_log_has_per_leg_seconds_and_nav_age(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    legs = [line for line in robot.logs if "leg:" in line and "m in" in line]
    assert len(legs) == 3
    assert any("nav_age=" in line for line in robot.logs)
