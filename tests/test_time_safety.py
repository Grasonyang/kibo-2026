"""時間安全：不管機器人偏慢、到點不穩，或兩者一起，完成回報都要在 300 秒內送出。

這些情境來自 sim-bringup-review council 的查證（notes/council/sim-bringup-review/synthesis.md）：
規劃端不知道機器人偏慢，每點實際停留的時間也比預算估的長。逾時的代價可能是整場 0 分，
所以寧可少去幾個點。
"""

import pytest

from kibo.fake_robot import FakeRobot, fake_config
from kibo.geometry import Pose, add
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo.motion import Speeds
from kibo.scenarios import random_checkpoints_message

LIMIT = DEFAULT_MISSION.time_limit_sec
COUNTS = (8, 10, 12)
SEEDS = range(20)  # 正常情況的比較用全部 20 個；其他情境用前 10 個就夠
BASE = fake_config(0.01, 0.0, 1.0)  # 到點誤差 1 cm、不失敗、與模型同速
BEFORE = {10: 8.9, 12: 9.1}  # 收緊之前，正常機器人在這 20 個場景平均通過幾點


class NeverSteady(FakeRobot):
    """到點後導航讀數一筆正常、一筆偏 0.5 m，永遠湊不滿連續 5 筆；也沒有尾段紀錄。"""

    reads = 0

    def pose(self):
        pose = super().pose()
        self.reads += 1
        if pose is not None and self.reads % 2:
            return Pose(add(pose.position, (0.0, 0.0, 0.5)), pose.orientation, pose.stamp)
        return pose

    def recent_poses(self, seconds):
        return []


def fleet(robot_class, slowdown, seeds=range(10)):
    """回傳 (最晚的完成時刻, 到達 Goal 的場數, 各點數的平均通過點數)。"""
    config = BASE._replace(speeds=Speeds(slowdown=slowdown))
    latest, goals, mean_points = 0.0, 0, {}
    for count in COUNTS:
        passed = 0
        for seed in seeds:
            robot = robot_class(random_checkpoints_message(count, seed), config, seed)
            run_mission(robot, DEFAULT_MISSION)
            assert robot.finished_at is not None
            latest = max(latest, robot.finished_at)
            goals += robot.goal_reached
            passed += len(robot.passed_ids)
        mean_points[count] = passed / float(len(seeds))
    return latest, goals, mean_points


@pytest.mark.parametrize("slowdown", [1.11, 1.24, 1.5])
def test_a_robot_slower_than_the_model_still_finishes_in_time(slowdown):
    # 慢 20% 到 24% 曾經落在校正的死區裡（慢 25% 才校正），完成時間貼到 298 秒，偶爾超過。
    # 1.11 是現在死區的邊緣（慢 11% 以內不校正），1.5 是校正會啟動的情況。
    latest, goals, _ = fleet(FakeRobot, slowdown)
    assert latest <= LIMIT - 5.0
    assert goals == len(COUNTS) * 10


def test_a_robot_that_never_settles_still_finishes_in_time():
    latest, _, _ = fleet(NeverSteady, 1.0)
    assert latest <= LIMIT - 2.0


def test_slow_and_never_settling_together_still_finish_in_time():
    # 兩者疊加時曾經有三成的場次超時：每點實際停留十幾秒，預算卻只估 1 秒。
    latest, _, _ = fleet(NeverSteady, 1.2)
    assert latest <= LIMIT - 2.0


def test_a_well_behaved_robot_visits_as_many_points_as_before():
    # 收緊時間安全不能讓正常情況少去點。BEFORE 是收緊之前、同樣 20 個場景的平均。
    _, goals, mean_points = fleet(FakeRobot, 1.0, SEEDS)
    assert goals == len(COUNTS) * len(SEEDS)
    assert mean_points[8] == 8.0
    assert mean_points[10] >= BEFORE[10] and mean_points[12] >= BEFORE[12]
