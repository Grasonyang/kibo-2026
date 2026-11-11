"""假裁判：官方評分模組的三條規則（docs/kibo/simulator-internals.md 的 J7、J9、J10）與假設的分數。

直接對假裁判測，不透過假機器人：姿態由測試給。
"""

import pytest

from kibo.checkpoints import parse_checkpoints
from kibo.geometry import Pose, add
from kibo_lab.fake_judge import FakeJudge
from kibo_lab.scoring import DEFAULT_SCORING, WORLDS


@pytest.fixture
def cps(three_point_message):
    return parse_checkpoints(three_point_message)


def at(cp, offset=(0.0, 0.0, 0.0)):
    """停在 cp 上、姿態正確，位置偏 offset。"""
    return Pose(add(cp.position, offset), cp.attitude)


FAR = (0.0, 0.0, 0.5)  # 超出最寬的位置餘裕


def started(cps):
    judge = FakeJudge(cps)
    judge.mission_start()
    return judge


def test_a_checkpoint_reached_on_target_passes_at_level_3(cps):
    judge = started(cps)
    judge.checkpoint_passed(1, at(cps.by_id(1)))
    assert judge.judged_ids == [1] and judge.passed_ids == [1] and judge.passed_levels == [3]


def test_each_checkpoint_is_judged_on_the_first_notification_only(cps):
    # J7：第一次沒過就是沒過，之後站得再準也不重判。
    judge = started(cps)
    judge.checkpoint_passed(1, at(cps.by_id(1), FAR))
    judge.checkpoint_passed(1, at(cps.by_id(1)))
    assert judge.judged_ids == [1] and judge.passed_ids == []


def test_a_pass_is_not_upgraded_by_a_later_notification(cps):
    judge = started(cps)
    judge.checkpoint_passed(1, at(cps.by_id(1), (0.0, 0.0, 0.15)))  # 位置 Lv2
    judge.checkpoint_passed(1, at(cps.by_id(1)))
    assert judge.passed_levels == [2]


def test_notifications_before_the_start_and_after_the_finish_are_ignored(cps):
    # J10
    judge = FakeJudge(cps)
    judge.checkpoint_passed(1, at(cps.by_id(1)))
    assert judge.judged_ids == []
    judge.mission_start()
    judge.mission_finish(at(cps.goal), 100.0)
    judge.checkpoint_passed(1, at(cps.by_id(1)))
    assert judge.judged_ids == []


def test_an_unknown_id_is_recorded_as_judged_and_failed(cps):
    judge = started(cps)
    judge.checkpoint_passed(99, at(cps.by_id(1)))
    assert judge.judged_ids == [99] and judge.passed_ids == []


def test_a_goal_passed_earlier_counts_at_the_finish_wherever_the_robot_is(cps):
    # J9 前半：Goal 點先前通過就算到達。
    judge = started(cps)
    judge.checkpoint_passed(12, at(cps.goal))
    judge.mission_finish(at(cps.by_id(1)), 100.0)
    assert judge.goal_reached and judge.passed_ids == [12]


def test_the_goal_is_judged_again_at_the_finish_if_it_has_not_passed(cps):
    # J9 後半：先前那次通知沒過，完成回報時用當下姿態再判，通過就補記。
    judge = started(cps)
    judge.checkpoint_passed(12, at(cps.goal, FAR))
    judge.mission_finish(at(cps.goal), 100.0)
    assert judge.goal_reached
    assert judge.passed_ids == [12] and judge.passed_levels == [3]


def test_finishing_away_from_the_goal_does_not_reach_it(cps):
    judge = started(cps)
    judge.mission_finish(at(cps.by_id(1)), 100.0)
    assert not judge.goal_reached and judge.passed_ids == []


def test_the_score_is_the_points_times_the_time_multiplier(cps):
    judge = started(cps)
    for cp in cps.checkpoints:
        judge.checkpoint_passed(cp.id, at(cp))
    judge.mission_finish(at(cps.goal), 150.0)  # 剩一半時間：倍率 1.5
    assert judge.remaining_at_finish() == 150.0
    assert judge.score() == pytest.approx((3 * 10.0 + 20.0) * 1.5)


def test_without_a_finish_report_the_run_counts_as_late(cps):
    judge = started(cps)
    judge.checkpoint_passed(1, at(cps.by_id(1)))
    assert judge.finished_at is None and judge.remaining_at_finish() == 0.0
    assert judge.score() == 0.0  # 預設世界：逾時整場 0
    assert judge.score(WORLDS["B/T1"]) == 10.0  # 逾時保留已得分的世界


def test_a_finish_after_the_limit_is_late(cps):
    judge = started(cps)
    judge.checkpoint_passed(12, at(cps.goal))
    judge.mission_finish(at(cps.goal), DEFAULT_SCORING.time_limit_sec + 0.1)
    assert judge.score() == 0.0


def test_the_goal_points_can_depend_on_passing_every_checkpoint(cps):
    judge = started(cps)
    judge.checkpoint_passed(1, at(cps.by_id(1)))
    judge.checkpoint_passed(12, at(cps.goal))
    judge.mission_finish(at(cps.goal), 300.0)  # 沒有剩餘時間：倍率 1
    assert judge.score(WORLDS["B/T0"]) == 40.0
    assert judge.score(WORLDS["A/T0"]) == 20.0  # 漏了 #6：Goal 分不給
