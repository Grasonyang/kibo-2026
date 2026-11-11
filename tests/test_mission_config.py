"""任務設定的分組（issue #4）：每一組管一件事，沒有一欄多用；探針自己一組，節點只碰那一組。"""

import ast
import os

from conftest import PERFECT
from kibo.mission import DEFAULT_MISSION, NO_PROBES, MissionConfig, Probes, _Run
from kibo.pace import DEFAULT_PACE
from kibo.settle import SettleConfig
from kibo_lab.fake_robot import FakeRobot

ROOT = os.path.join(os.path.dirname(__file__), "..")
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


def _node_tree():
    # ros/user_node.py 不能在這裡匯入（要 rospy），所以解析原始碼。
    with open(os.path.join(ROOT, "ros", "user_node.py"), encoding="utf-8") as source:
        return ast.parse(source.read())


def _calls(tree, method):
    """tree 裡所有 `<什麼>.method(...)` 的呼叫。"""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
    ]


def test_the_node_changes_no_setting_other_than_the_probe_group():
    tree = _node_tree()
    # 整個節點只有一處改任務設定，而且只給 probes；不准用 **kwargs，也不准自己建一份 MissionConfig。
    changed = [(kw.arg for kw in call.keywords) for call in _calls(tree, "_replace")]
    assert [list(names) for names in changed] == [["probes"]]
    names_used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names_used & {"MissionConfig", "TimeConfig", "MoveConfig", "RetryConfig"}
    assert not names_used & {"CameraConfig", "SettleConfig", "PaceRule", "BudgetConfig"}


def test_the_node_reads_probe_parameters_in_one_place_only():
    tree = _node_tree()
    config = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_config"
    )

    def params(scope):
        found = []
        for call in _calls(scope, "get_param"):
            first = call.args[0]
            assert isinstance(first, ast.Constant), "參數名要寫成字串常數，才看得出讀了什麼"
            found.append(first.value)
        return found

    assert sorted(params(config)) == [
        "~probe_deliberate_late_after",
        "~probe_notify_even_if_level0",
        "~probe_skip_one_waypoint",
    ]
    # _config 以外讀的參數都與任務設定無關
    assert sorted(set(params(tree)) - set(params(config))) == ["/use_sim_time", "~survey_only"]


def test_the_launch_file_we_submit_turns_no_probe_on():
    # 節點啟動時不會自己擋探針（資格賽模擬器上要用），所以守提交包：launch 檔不得帶探針參數。
    with open(os.path.join(ROOT, "krpc_user", "launch", "krpc_user.launch")) as source:
        assert "probe" not in source.read()


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
