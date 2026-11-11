"""R1 不死保底：不管清單怎麼壞、程式怎麼炸，任務開始了就一定會完成回報。"""

import json

from conftest import (
    CHECKPOINT_6,
    GOAL_12,
    MANUAL_CHECKPOINT_1,
    PERFECT,
    checkpoint_at,
    checkpoints_message,
)
from kibo.field import MARKERS
from kibo.geometry import IDENTITY_QUAT
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.planner import MAX_WAYPOINTS, plan_route
from kibo_lab.fake_robot import FakeRobot
from kibo_lab.scenarios import checkpoint_from_marker


def test_manual_example_shape_count_8_goal_12_still_flies_and_finishes():
    # 手冊 6.3.1 的範例：count=8 但只列了一點、goalpoint_id=12 不在清單裡。
    message = json.dumps(
        {"checkpoint_count": 8, "checkpoints": [MANUAL_CHECKPOINT_1], "goalpoint_id": 12}
    )
    robot = FakeRobot(message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished and robot.judge.finished_at is not None
    assert robot.judge.passed_ids == [1]
    assert any("goalpoint_id=12" in line for line in robot.logs)


class ExplodingRobot(FakeRobot):
    def move_to(self, target, timeout_sec):
        raise RuntimeError("actionlib went away")


def test_exception_in_the_middle_still_calls_mission_finish(three_point_message):
    robot = ExplodingRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.judge.finished_at is not None
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
    # 中途點超過 Held-Karp 的上限（規則外）：改用最近鄰，照樣每點去一次。
    waypoints = [checkpoint_at(i, (float(i), 0.0, 0.0)) for i in range(1, MAX_WAYPOINTS + 3)]
    goal = checkpoint_at(99, (99.0, 0.0, 0.0))
    route = plan_route((0.0, 0.0, 0.0), IDENTITY_QUAT, waypoints, goal)
    assert route.order == [w.id for w in waypoints] + [99]  # 直線上最近鄰就是順序


def test_skipped_checkpoint_is_logged_at_mission_start():
    broken = json.loads(json.dumps(CHECKPOINT_6))
    del broken["marker_pose"]
    message = checkpoints_message([MANUAL_CHECKPOINT_1, broken, GOAL_12])
    robot = FakeRobot(message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    assert any("skipped" in line for line in robot.logs)
    assert sorted(robot.judge.passed_ids) == [1, 12]


def test_fake_judge_ignores_notifications_outside_the_mission_and_unknown_ids(
    three_point_message,
):
    # 官方 judge.py：開始前、完成後的通知只記警告；不存在的 id 記成判過、沒過；通知一律被接受。
    robot = FakeRobot(three_point_message, PERFECT)
    assert robot.notify_checkpoint(1) is True  # 還沒開始
    assert robot.judge.judged_ids == []
    robot.mission_start()
    assert robot.notify_checkpoint(99) is True
    assert robot.judge.judged_ids == [99] and robot.judge.passed_ids == []
    robot.mission_finish()
    assert robot.notify_checkpoint(1) is True  # 已經結束
    assert 1 not in robot.judge.judged_ids
