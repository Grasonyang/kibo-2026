"""R3：規則書沒講清楚的兩件事做成開關，分數在四個世界各算一次。"""

from kibo.scoring import WORLDS, Scoring

LEVELS = [3, 3, 2]  # 10 + 10 + 6 = 26 分


def test_goal_only_world_pays_goal_even_if_a_checkpoint_was_missed():
    s = WORLDS["B/T0"]
    assert s.total(LEVELS, True, 0.0, all_passed=False) == 46.0


def test_goal_requires_all_world_withholds_goal_points_when_a_checkpoint_was_missed():
    s = WORLDS["A/T0"]
    assert s.total(LEVELS, True, 0.0, all_passed=False) == 26.0
    assert s.total(LEVELS, True, 0.0, all_passed=True) == 46.0


def test_timeout_zeroes_everything_in_t0_but_keeps_checkpoints_in_t1():
    assert WORLDS["B/T0"].total(LEVELS, False, 0.0, late=True) == 0.0
    assert WORLDS["B/T1"].total(LEVELS, False, 0.0, late=True) == 26.0  # 倍率 1，沒有 Goal


def test_fake_robot_can_be_scored_in_any_world(three_point_message):
    from conftest import PERFECT
    from kibo.fake_robot import FakeRobot
    from kibo.mission import DEFAULT_MISSION, run_mission

    class SkipsOne(FakeRobot):
        def notify_checkpoint(self, checkpoint_id):
            if checkpoint_id == 6:
                return False
            return super().notify_checkpoint(checkpoint_id)

    robot = SkipsOne(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    assert robot.score(WORLDS["B/T0"]) > robot.score(WORLDS["A/T0"]) > 0.0


def test_default_scoring_is_the_goal_only_timeout_zero_world():
    assert isinstance(WORLDS["B/T0"], Scoring)
    assert (
        WORLDS["B/T0"].goal_requires_all is False and WORLDS["B/T0"].timeout_keeps_points is False
    )
