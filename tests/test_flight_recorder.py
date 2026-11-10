"""R4：校準與飛行記錄——穩定判定只計新資料、探針旗標、沒成功移動不回報、log 可算速度。"""

from conftest import PERFECT
from kibo.fake_robot import FakeRobot
from kibo.field import TIME_LIMIT_SEC
from kibo.geometry import Pose
from kibo.mission import DEFAULT_MISSION, MOVE_INVALID, run_mission


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
    assert robot.finished_at is not None and robot.finished_at > TIME_LIMIT_SEC


def test_log_has_distance_turn_and_seconds_for_every_leg(three_point_message):
    import re

    robot = FakeRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    legs = [re.search(r"leg: ([\d.]+)m (\d+)deg in ([\d.]+)s", line) for line in robot.logs]
    legs = [m for m in legs if m]
    assert len(legs) == 3
    for m in legs:
        metres, seconds = float(m.group(1)), float(m.group(3))
        # 上限速度 0.2 m/s，短腿加減速加轉向後平均慢很多
        assert 0.01 < metres / seconds <= 0.2
    assert any("nav_age=" in line for line in robot.logs)


def test_log_lets_you_measure_settle_seconds(three_point_message):
    import re

    robot = FakeRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    left = {}
    for line in robot.logs:
        m = re.match(r"\[t=[\d.]+ +([\d.]+)s left\] (.*)", line)
        if m and ("move to #1 attempt 1: success" in m.group(2) or m.group(2).startswith("at #1:")):
            left[m.group(2)[:10]] = float(m.group(1))
    settle_sec = left["move to #1"] - left["at #1: dis"]
    assert 1.0 <= settle_sec <= DEFAULT_MISSION.settle_timeout_sec + 1.0


def test_probe_flags_are_off_by_default():
    assert not DEFAULT_MISSION.probes_on
    assert DEFAULT_MISSION.notify_even_if_level0 is False
    assert DEFAULT_MISSION.skip_one_waypoint is False
    assert DEFAULT_MISSION.deliberate_late_after == 0
    assert DEFAULT_MISSION._replace(skip_one_waypoint=True).probes_on


def test_deliberate_late_counts_notified_checkpoints_and_honours_stop(three_point_message):
    class StopDuringWait(FakeRobot):
        def sleep(self, sec):
            super().sleep(sec)
            if self.t > 200.0:
                self.stop = True

    robot = StopDuringWait(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION._replace(deliberate_late_after=1))
    assert report.aborted == "stop requested"
    assert robot.t < 300.0  # 等到一半就被停下來，沒有硬睡到逾時


def test_log_compares_what_the_camera_sees_with_what_navigation_expects(three_point_message):
    import re

    robot = FakeRobot(three_point_message, PERFECT._replace(camera=True, vision_noise_m=0.0))
    run_mission(robot, DEFAULT_MISSION)
    lines = [line for line in robot.logs if "marker #1 seen" in line]
    assert len(lines) == 1
    match = re.search(r"apart ([\d.]+)m", lines[0])
    assert match is not None
    apart = float(match.group(1))
    assert apart < 0.01  # 假相機沒有誤差，導航也準：兩者應該重合
    assert robot.relative_calls == 0  # 只記錄，沒有因此多動一下


def test_a_robot_without_a_camera_just_says_the_marker_was_not_seen(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert any("marker #1 not seen" in line for line in robot.logs)
    assert report.goal_reached


def test_sim_report_can_still_find_the_legs_in_the_log(three_point_message):
    # scripts/sim_report.py 靠這兩種 log 行切出每段腿；log 的字改了，它會悄悄什麼都找不到。
    import importlib.util
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "sim_report.py")
    spec = importlib.util.spec_from_file_location("sim_report", path)
    assert spec is not None and spec.loader is not None
    sim_report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sim_report)

    robot = FakeRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    starts = [line for line in robot.logs if sim_report.LEG_START.search(line)]
    ends = [sim_report.LEG_END.search(line) for line in robot.logs]
    ends = [m for m in ends if m]
    assert len(starts) == 3 and len(ends) == 3
    assert [int(m.group(2)) for m in ends] == [v.checkpoint_id for v in report.visits]
    assert all(m.group(3) == "success" for m in ends)
