"""任務設定的分組（issue #4）：每一組管一件事，沒有一欄多用；探針自己一組，節點只碰那一組。"""

import os
import re

from conftest import PERFECT
from kibo.mission import DEFAULT_MISSION, NO_PROBES, MissionConfig, Probes, _Run
from kibo.pace import DEFAULT_PACE
from kibo.settle import SettleConfig
from kibo_lab.fake_robot import FakeRobot

GROUPS = ("time", "budget", "move", "settle", "retry", "camera", "pace", "probes")


class Sleeps(FakeRobot):
    """記下每一次等待的秒數。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sleeps = []

    def sleep(self, sec):
        self.sleeps.append(sec)
        super().sleep(sec)


class SleepsBlind(Sleeps):
    def pose(self):
        return None


class SleepsRejected(Sleeps):
    def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
        return False


def test_the_settings_are_grouped_by_concept_and_nothing_is_left_loose():
    assert MissionConfig._fields == GROUPS
    assert DEFAULT_MISSION.pace == DEFAULT_PACE
    assert DEFAULT_MISSION.settle == SettleConfig()


def test_the_final_build_can_assert_in_one_line_that_no_probe_is_on():
    assert DEFAULT_MISSION.probes == NO_PROBES
    assert not NO_PROBES.on


def test_any_single_probe_turns_the_group_on():
    assert Probes(notify_even_if_level0=True).on
    assert Probes(skip_one_waypoint=True).on
    assert Probes(deliberate_late_after=2).on


def test_the_node_reads_ros_parameters_into_the_probe_group_only():
    # ros/user_node.py 不能在這裡匯入（要 rospy），所以讀原始碼：_config 只能動 probes 這一組。
    node = os.path.join(os.path.dirname(__file__), "..", "ros", "user_node.py")
    with open(node, encoding="utf-8") as source:
        text = source.read()
    body = text[text.index("def _config():") :]
    body = body[: body.index("\n    def ", 1)] if "\n    def " in body[1:] else body
    assert re.findall(r"_replace\(\s*(\w+)=", body) == ["probes"]
    assert set(re.findall(r'get_param\("~(\w+)"', body)) == {
        "probe_notify_even_if_level0",
        "probe_skip_one_waypoint",
        "probe_deliberate_late_after",
    }


# ---- 沒有一欄多用：三種「等一下」各有自己的秒數 ----


def test_reading_the_pose_again_waits_its_own_pause(three_point_message):
    retry = DEFAULT_MISSION.retry._replace(pose_attempts=3, pose_pause_sec=0.7)
    robot = SleepsBlind(three_point_message, PERFECT)
    run = _Run(robot, DEFAULT_MISSION._replace(retry=retry))
    assert run.current_pose() is None
    assert robot.sleeps == [0.7, 0.7, 0.7]


def test_notifying_again_waits_its_own_pause(three_point_message):
    retry = DEFAULT_MISSION.retry._replace(notify_attempts=3, notify_pause_sec=0.6)
    robot = SleepsRejected(three_point_message, PERFECT)
    run = _Run(robot, DEFAULT_MISSION._replace(retry=retry))
    assert run.notify(robot.checkpoints.goal) is False
    assert robot.sleeps == [0.0, 0.6, 0.6]


def test_sampling_while_settling_waits_its_own_interval(three_point_message):
    settle = DEFAULT_MISSION.settle._replace(samples=3, interval_sec=0.4)
    robot = Sleeps(three_point_message, PERFECT)
    run = _Run(robot, DEFAULT_MISSION._replace(settle=settle))
    goal = robot.checkpoints.goal
    assert run.move(goal, 1)
    robot.sleeps = []
    assert run.settle(goal).stable
    assert robot.sleeps == [0.4, 0.4]  # 三筆樣本之間等兩次
    assert settle.rule().window_sec == 0.8 and settle.rule().max_age_sec == 0.4
