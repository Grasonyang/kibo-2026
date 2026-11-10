"""R1 不死保底：不管清單怎麼壞、程式怎麼炸，任務開始了就一定會完成回報。"""

import json

from conftest import CHECKPOINT_6, GOAL_12, MANUAL_CHECKPOINT_1, checkpoints_message
from kibo.fake_robot import FakeRobot, FakeRobotConfig
from kibo.field import MARKERS
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.planner import MAX_WAYPOINTS, plan_route
from kibo.scenarios import checkpoint_from_marker

PERFECT = FakeRobotConfig(position_noise_m=0.0, attitude_noise_deg=0.0, nav_jitter_m=0.0)


def test_manual_example_shape_count_8_goal_12_still_flies_and_finishes():
    # 手冊 6.3.1 的範例：count=8 但只列了一點、goalpoint_id=12 不在清單裡。
    message = json.dumps(
        {"checkpoint_count": 8, "checkpoints": [MANUAL_CHECKPOINT_1], "goalpoint_id": 12}
    )
    robot = FakeRobot(message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished and robot.finished_at is not None
    assert robot.passed_ids == [1]
    assert any("goalpoint_id=12" in line for line in robot.logs)


class ExplodingRobot(FakeRobot):
    def move_to(self, target, timeout_sec):
        raise RuntimeError("actionlib went away")


def test_exception_in_the_middle_still_calls_mission_finish(three_point_message):
    robot = ExplodingRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.finished_at is not None
    assert report.aborted.startswith("exception")


def test_twelve_waypoints_do_not_raise():
    import random

    rng = random.Random(1)
    extra = [checkpoint_from_marker(m, rng) for m in MARKERS.values() if m.id != 12]
    thirteenth = json.loads(json.dumps(extra[0]))
    thirteenth["checkpoint_id"] = 13
    message = json.dumps(
        {"checkpoint_count": 13, "checkpoints": extra + [thirteenth, GOAL_12], "goalpoint_id": 12}
    )
    robot = FakeRobot(message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished and report.goal_reached


def test_nearest_neighbour_fallback_visits_everything_once():
    from kibo.checkpoints import Checkpoint
    from kibo.geometry import IDENTITY_QUAT

    def cp(i):
        return Checkpoint(
            i, (float(i), 0.0, 0.0), (float(i), 0.0, 0.0), IDENTITY_QUAT, IDENTITY_QUAT, [], [], []
        )

    waypoints = [cp(i) for i in range(1, MAX_WAYPOINTS + 3)]
    route = plan_route((0.0, 0.0, 0.0), IDENTITY_QUAT, waypoints, cp(99))
    assert sorted(route.order[:-1]) == [w.id for w in waypoints]
    assert route.order == [w.id for w in waypoints] + [99]  # 直線上最近鄰就是順序


def test_matrix_planner_matches_previous_known_answer():
    from kibo.checkpoints import Checkpoint
    from kibo.geometry import IDENTITY_QUAT

    def cp(i, p):
        return Checkpoint(i, p, p, IDENTITY_QUAT, IDENTITY_QUAT, [], [], [])

    waypoints = [cp(3, (3.0, 0.0, 0.0)), cp(1, (1.0, 0.0, 0.0)), cp(2, (2.0, 0.0, 0.0))]
    assert plan_route((0.0, 0.0, 0.0), IDENTITY_QUAT, waypoints, cp(9, (0.0, 1.0, 0.0))).order == [
        1,
        2,
        3,
        9,
    ]


def test_skipped_checkpoint_is_logged_at_mission_start():
    broken = json.loads(json.dumps(CHECKPOINT_6))
    del broken["marker_pose"]
    message = checkpoints_message([MANUAL_CHECKPOINT_1, broken, GOAL_12])
    robot = FakeRobot(message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    assert any("skipped" in line for line in robot.logs)
    assert sorted(robot.passed_ids) == [1, 12]


def test_fake_judge_ignores_notifications_outside_the_mission_and_unknown_ids(
    three_point_message,
):
    # 官方 judge.py：開始前、完成後的通知只記警告；不存在的 id 記成判過、沒過；通知一律被接受。
    robot = FakeRobot(three_point_message, PERFECT)
    assert robot.notify_checkpoint(1) is True  # 還沒開始
    assert robot.judged_ids == []
    robot.mission_start()
    assert robot.notify_checkpoint(99) is True
    assert robot.judged_ids == [99] and robot.passed_ids == []
    robot.mission_finish()
    assert robot.notify_checkpoint(1) is True  # 已經結束
    assert 1 not in robot.judged_ids
