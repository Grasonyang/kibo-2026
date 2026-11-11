"""節奏：只用數字測速度校正的規則（整場任務的回歸在 test_speed_calibration.py）。"""

import pytest

from kibo.pace import DEFAULT_PACE, Pace

LONG_M = 2.0  # 夠長、算得上證據的腿


def pace_after(legs, rule=DEFAULT_PACE):
    pace = Pace(rule)
    for metres, predicted_sec, actual_sec in legs:
        pace.add_leg(metres, predicted_sec, actual_sec)
    return pace


def test_with_no_legs_the_model_is_trusted():
    assert Pace(DEFAULT_PACE).slowdown() == 1.0


def test_a_robot_half_again_slower_than_the_model_is_measured_as_such():
    assert pace_after([(LONG_M, 20.0, 30.0)]).slowdown() == pytest.approx(1.5)


def test_one_or_two_legs_are_not_enough_to_conclude():
    # 模型秒數累積不到 20 秒：就算每段都慢一倍也先不下結論。
    assert pace_after([(LONG_M, 9.0, 18.0), (LONG_M, 10.0, 20.0)]).slowdown() == 1.0
    assert pace_after([(LONG_M, 9.0, 18.0), (LONG_M, 11.0, 22.0)]).slowdown() == pytest.approx(2.0)


def test_slower_by_less_than_the_deadband_is_left_alone():
    # 死區是 1/0.9 = 1.11 倍：慢 10% 不動，慢 12% 才校正。
    assert pace_after([(LONG_M, 100.0, 110.0)]).slowdown() == 1.0
    assert pace_after([(LONG_M, 100.0, 112.0)]).slowdown() == pytest.approx(1.12)


def test_the_measurement_is_capped_at_twice_the_model():
    assert pace_after([(LONG_M, 30.0, 90.0)]).slowdown() == pytest.approx(2.0)


def test_a_robot_faster_than_the_model_is_never_sped_up():
    assert pace_after([(LONG_M, 40.0, 20.0)]).slowdown() == 1.0


def test_short_legs_are_not_evidence():
    # 0.5 公尺以下的腿，一兩秒的誤差佔比太大：不算進去，也不算進「累積夠了沒」。
    pace = pace_after([(0.3, 30.0, 60.0)])
    assert pace.slowdown() == 1.0 and pace.predicted_sec == 0.0
    assert pace_after([(0.5, 30.0, 60.0)]).slowdown() == pytest.approx(2.0)


def test_the_ratio_is_over_all_legs_together_not_the_latest_one():
    # 40 秒的腿慢 50%、10 秒的腿準時：合起來是 70/50 = 1.4 倍。
    assert pace_after([(LONG_M, 40.0, 60.0), (LONG_M, 10.0, 10.0)]).slowdown() == pytest.approx(1.4)


def test_later_legs_can_bring_it_back_to_the_model():
    # 不留棘輪：後來的腿把整體拉回死區內，就回到照模型。
    pace = pace_after([(LONG_M, 20.0, 30.0)])
    assert pace.slowdown() == pytest.approx(1.5)
    pace.add_leg(LONG_M, 100.0, 100.0)
    assert pace.slowdown() == 1.0


def test_switched_off_it_always_trusts_the_model():
    off = DEFAULT_PACE._replace(enabled=False)
    pace = pace_after([(LONG_M, 30.0, 60.0)], off)
    assert pace.slowdown() == 1.0 and pace.predicted_sec == 0.0
