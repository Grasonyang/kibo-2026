"""到點穩定：一筆一筆餵姿態，問「已經在容差內連續待滿 1 秒了嗎」。

用手冊 6.3.1 的 CheckPoint 1。姿態直接造：exact 是分毫不差（Lv3），rolled(9) 是滾 9°
（還是 Lv3，但貼著 10° 的上限），rolled(15) 是 Lv2。
"""

import pytest

from kibo.checkpoints import parse_checkpoints
from kibo.geometry import FORWARD, Pose, axis_angle_quat, quat_mul
from kibo.settle import SettleRule, Steadiness

RULE = SettleRule(samples=5, window_sec=1.0, max_age_sec=0.25, notify_margin=0.8)


@pytest.fixture
def cp1(three_point_message):
    return parse_checkpoints(three_point_message).by_id(1)


def rolled(cp, degrees, stamp):
    attitude = quat_mul(cp.attitude, axis_angle_quat(FORWARD, degrees))
    return Pose(cp.position, attitude, stamp=stamp)


def feed(watch, cp, readings, required=3, strict=False):
    """readings 是 [(stamp, 滾轉度數), …]；回傳每筆餵完之後是否穩定。"""
    out = []
    for stamp, degrees in readings:
        watch.feed(rolled(cp, degrees, stamp), required, strict)
        out.append(watch.stable)
    return out


def test_five_good_samples_a_second_apart_end_to_end_are_stable(cp1):
    watch = Steadiness(cp1, RULE)
    result = feed(watch, cp1, [(10.0 + 0.25 * i, 0.0) for i in range(5)])
    assert result == [False, False, False, False, True]
    assert watch.last is not None and watch.last.level == 3


def test_a_bad_sample_starts_the_count_over(cp1):
    watch = Steadiness(cp1, RULE)
    readings = [(0.0, 0.0), (0.25, 0.0), (0.5, 15.0)] + [(0.75 + 0.25 * i, 0.0) for i in range(5)]
    assert feed(watch, cp1, readings) == [False] * 7 + [True]


def test_the_same_navigation_sample_read_twice_counts_once(cp1):
    # 導航沒更新時讀到同一筆：不能把同一筆讀五次當成「穩定 1 秒」。
    watch = Steadiness(cp1, RULE)
    assert feed(watch, cp1, [(3.0, 0.0)] * 8) == [False] * 8
    assert watch.feed(rolled(cp1, 0.0, 3.0), 3, False) is None  # 重複的那筆沒有被判定


def test_many_good_samples_packed_into_less_than_a_second_are_not_enough(cp1):
    # 20 Hz 的紀錄：筆數早就夠了，但頭尾還不到 1 秒。
    watch = Steadiness(cp1, RULE)
    result = feed(watch, cp1, [(0.05 * i, 0.0) for i in range(21)])
    assert result[:20] == [False] * 20 and result[20] is True


def test_strict_asks_for_a_fifth_of_the_level_3_margin_to_spare(cp1):
    # 9° 是 Lv3，但用掉九成的餘裕；嚴格時不算，放寬後才算。
    readings = [(0.25 * i, 9.0) for i in range(5)]
    assert feed(Steadiness(cp1, RULE), cp1, readings, strict=True) == [False] * 5
    assert feed(Steadiness(cp1, RULE), cp1, readings, strict=False)[-1] is True


def test_strict_does_not_apply_when_less_than_level_3_is_required(cp1):
    readings = [(0.25 * i, 15.0) for i in range(5)]  # Lv2
    assert feed(Steadiness(cp1, RULE), cp1, readings, required=2, strict=True)[-1] is True
    assert feed(Steadiness(cp1, RULE), cp1, readings, required=3, strict=True)[-1] is False


def test_poses_without_a_stamp_fall_back_to_counting(cp1):
    watch = Steadiness(cp1, RULE)
    result = [
        (watch.feed(Pose(cp1.position, cp1.attitude), 3, False), watch.stable)[1] for _ in range(5)
    ]
    assert result == [False, False, False, False, True]


def test_a_tail_that_was_good_for_a_full_second_is_stable_right_away(cp1):
    watch = Steadiness(cp1, RULE)
    tail = [rolled(cp1, 0.0, 9.0 + 0.05 * i) for i in range(21)]  # 9.00 到 10.00
    assert watch.feed_tail(tail, now=10.1, required_level=3) is True
    assert watch.stable


@pytest.mark.parametrize(
    "tail_stamps_and_rolls,now,why",
    [
        ([(9.0 + 0.05 * i, 0.0) for i in range(21)], 10.5, "newest sample is too old"),
        ([(9.5 + 0.05 * i, 0.0) for i in range(11)], 10.1, "covers only half a second"),
        ([(9.0, 15.0)] + [(9.05 + 0.05 * i, 0.0) for i in range(20)], 10.1, "one bad sample"),
        ([(9.0 + 0.05 * i, 9.0) for i in range(21)], 10.1, "too close to the Lv3 limit"),
        ([(9.0, 0.0), (10.0, 0.0)], 10.1, "too few samples"),
    ],
)
def test_a_tail_that_falls_short_counts_for_nothing(cp1, tail_stamps_and_rolls, now, why):
    watch = Steadiness(cp1, RULE)
    tail = [rolled(cp1, degrees, stamp) for stamp, degrees in tail_stamps_and_rolls]
    assert watch.feed_tail(tail, now=now, required_level=3) is False, why
    assert not watch.stable
    assert "samples over" in watch.tail_report
    # 之後要從頭數滿 1 秒，尾段那些好樣本不能拿來湊。
    later = [(now + 0.25 * i, 0.0) for i in range(5)]
    assert feed(watch, cp1, later) == [False, False, False, False, True], why


def test_an_empty_tail_is_simply_not_stable(cp1):
    watch = Steadiness(cp1, RULE)
    assert watch.feed_tail([], now=1.0, required_level=3) is False
    assert watch.tail_report == ""
