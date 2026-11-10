"""run_mission 在不順利時的行為：沒有導航、晃動、拒絕、逾時、中途停止。

每個情境用 FakeRobot 的子類別改掉一個行為，其餘照舊。
"""

from kibo.fake_robot import FakeRobot, FakeRobotConfig
from kibo.geometry import add, rotate
from kibo.judge import Pose
from kibo.mission import (
    DEFAULT_MISSION,
    MOVE_INVALID,
    MOVE_SUCCESS,
    MOVE_TIMEOUT,
    run_mission,
)

PERFECT = FakeRobotConfig(position_noise_m=0.0, attitude_noise_deg=0.0, nav_jitter_m=0.0)
CAMERA_ON = DEFAULT_MISSION._replace(camera_fix_max_m=0.3)
SIDEWAYS_15CM = (0.0, 0.15, 0.0)  # 機體 +Y，與視線垂直：位置 Lv2、對中約 17° 也是 Lv2
LOST_35CM = (0.0, 0.0, 0.35)  # 超出最寬的位置餘裕


class BlindRobot(FakeRobot):
    def pose(self):
        return None


class OffsetRobot(FakeRobot):
    """每次移動都停在目標旁邊固定的偏移處。"""

    offset = SIDEWAYS_15CM

    def move_to(self, target, timeout_sec):
        result = super().move_to(target, timeout_sec)
        if result == MOVE_SUCCESS:
            shift = rotate(target.orientation, self.offset)
            self.true_pose = Pose(add(target.position, shift), target.orientation)
        return result


class LostRobot(OffsetRobot):
    offset = LOST_35CM


class SecondTryRobot(OffsetRobot):
    """第一次到某點會偏，再移動一次就準。"""

    def move_to(self, target, timeout_sec):
        first_time = target.position not in getattr(self, "seen", set())
        self.seen = getattr(self, "seen", set()) | {target.position}
        if first_time:
            return super().move_to(target, timeout_sec)
        return FakeRobot.move_to(self, target, timeout_sec)


class RejectingRobot(FakeRobot):
    notify_calls = 0

    def notify_checkpoint(self, checkpoint_id):
        self.notify_calls += 1
        return False


class InvalidMoveRobot(FakeRobot):
    def move_to(self, target, timeout_sec):
        self.move_calls += 1
        return MOVE_INVALID


class TimeoutMoveRobot(FakeRobot):
    def move_to(self, target, timeout_sec):
        self.move_calls += 1
        self.t += timeout_sec
        return MOVE_TIMEOUT


class StopAfterFirstRobot(FakeRobot):
    def notify_checkpoint(self, checkpoint_id):
        accepted = super().notify_checkpoint(checkpoint_id)
        self.stop = True
        return accepted


def test_without_navigation_nothing_is_reported(three_point_message):
    robot = BlindRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished
    assert robot.judged_ids == []  # 一個通過通知都沒送
    assert all(v.judged_level == 0 and not v.notified for v in report.visits)
    # 但它確實盲飛到了 Goal，官方在完成回報時會用當下姿態判 Goal，所以 Goal 仍然算到。
    assert robot.passed_ids == [12]


def test_unstable_but_inside_margin_is_still_reported_as_unstable(three_point_message):
    robot = OffsetRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert [v.stable for v in report.visits] == [False, False, False]
    assert [v.notified for v in report.visits] == [True, True, True]
    assert len(robot.passed_levels) == 3 and all(lv < 3 for lv in robot.passed_levels)


def test_outside_every_margin_is_not_reported(three_point_message):
    robot = LostRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.passed_ids == []
    assert all(not v.notified for v in report.visits)


def test_when_hurrying_level_1_counts_as_stable(three_point_message):
    robot = OffsetRobot(three_point_message, PERFECT)
    hurried = DEFAULT_MISSION._replace(time_limit_sec=DEFAULT_MISSION.hurry_sec - 1.0)
    report = run_mission(robot, hurried)
    assert report.visits[0].stable  # 不趕時間時 Lv2 不算穩定（上一個測試），趕時間就算
    assert report.visits[0].judged_level == 2


def test_one_refinement_move_recovers_level_3(three_point_message):
    robot = SecondTryRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.passed_levels == [3, 3, 3]
    assert all(v.stable for v in report.visits)
    assert robot.move_calls == 6  # 每點：第一次偏掉，第二次修正


def test_rejected_notifications_are_retried_a_bounded_number_of_times(three_point_message):
    robot = RejectingRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.notify_calls == 3 * DEFAULT_MISSION.notify_attempts
    assert not report.goal_reached


def test_invalid_move_is_not_retried(three_point_message):
    robot = InvalidMoveRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    assert robot.move_calls == 3  # 三個點各一次


def test_timed_out_move_is_retried_up_to_the_limit(three_point_message):
    robot = TimeoutMoveRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.move_calls <= 3 * DEFAULT_MISSION.max_move_attempts
    assert report.finished


def test_stop_in_the_middle_aborts_without_finish(three_point_message):
    robot = StopAfterFirstRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.aborted == "stop requested"
    assert len(robot.passed_ids) == 1
    assert robot.finished_at is None


class DriftingCameraRobot(OffsetRobot):
    """每次絕對移動都偏 15 cm，但有相機；相對移動是準的。"""

    def __init__(self, message, config, seed=0):
        super().__init__(message, config._replace(camera=True), seed)


def test_camera_correction_recovers_level_3_without_a_second_absolute_move(three_point_message):
    robot = DriftingCameraRobot(three_point_message, PERFECT)
    report = run_mission(robot, CAMERA_ON)
    assert robot.passed_levels == [3, 3, 3]
    assert all(v.stable for v in report.visits)
    assert robot.move_calls == 3  # 絕對移動每點一次
    assert robot.relative_calls == 3  # 修正每點一次


class FarDriftCameraRobot(DriftingCameraRobot):
    offset = (0.0, 0.0, 0.29)  # 位置超出餘裕，但相機修正量在上限內


def test_large_but_allowed_drift_is_still_corrected_by_camera(three_point_message):
    robot = FarDriftCameraRobot(three_point_message, PERFECT)
    run_mission(robot, CAMERA_ON)
    assert robot.passed_levels == [3, 3, 3]
    assert robot.relative_calls == 3


class HugeDriftCameraRobot(DriftingCameraRobot):
    offset = (0.0, 0.0, 0.5)  # 超過 camera_fix_max_m，應該不信相機、改用絕對移動


def test_implausible_camera_correction_falls_back_to_absolute_move(three_point_message):
    robot = HugeDriftCameraRobot(three_point_message, PERFECT)
    run_mission(robot, CAMERA_ON)
    assert robot.relative_calls == 0
    assert robot.move_calls == 6


def test_camera_fix_is_off_by_default_even_when_the_robot_has_a_camera(three_point_message):
    robot = DriftingCameraRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    assert robot.relative_calls == 0
