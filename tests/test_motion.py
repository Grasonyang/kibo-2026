"""移動時間模型：照 Int-Ball2 控制器（上游 ctl_only）的剖面公式與推力配置表。

期望值都是手算的：有效推力 = eta x 單顆風扇上限 / 該方向上最吃力那顆風扇的係數。
"""

import math

import pytest

from kibo.geometry import IDENTITY_QUAT
from kibo.motion import (
    DEFAULT_MOTION,
    bang_bang_seconds,
    max_accel,
    max_angular_accel,
    move_seconds,
)

S = math.sqrt(0.5)  # sin(45°) = cos(45°)，90° 旋轉的四元數分量


def test_acceleration_along_each_body_axis():
    # 0.4 x 0.06 N / (3.216 kg x 係數)；係數 X 0.3315、Y 0.6027、Z 0.4911
    assert max_accel((1.0, 0.0, 0.0)) == pytest.approx(0.022511, abs=1e-6)
    assert max_accel((0.0, 1.0, 0.0)) == pytest.approx(0.012382, abs=1e-6)
    assert max_accel((0.0, 0.0, 1.0)) == pytest.approx(0.015196, abs=1e-6)
    assert max_accel((-1.0, 0.0, 0.0)) == pytest.approx(0.022511, abs=1e-6)


def test_diagonal_directions_are_slower_than_any_axis():
    # (1,1,0)/√2：最吃力的風扇係數 (0.3315 + 0.6027)/√2 = 0.6606
    assert max_accel((S, S, 0.0)) == pytest.approx(0.011297, abs=1e-6)
    third = 1.0 / math.sqrt(3.0)
    assert max_accel((third, third, third)) < max_accel((0.0, 1.0, 0.0))


def test_angular_acceleration_about_each_body_axis():
    # 0.024 N / 係數 / 0.0136 kg·m²；係數 X 19.8198、Y 13.1935、Z 7.3257
    assert max_angular_accel((1.0, 0.0, 0.0)) == pytest.approx(0.089037, abs=1e-6)
    assert max_angular_accel((0.0, 1.0, 0.0)) == pytest.approx(0.133755, abs=1e-6)
    assert max_angular_accel((0.0, 0.0, 1.0)) == pytest.approx(0.240892, abs=1e-6)


def test_short_moves_never_reach_cruise_speed():
    # 1 m、a = 0.0225：v²/a = 1.78 m > 1 m，所以是三角形剖面 2√(r/a)
    assert bang_bang_seconds(1.0, 0.2, 0.0225) == pytest.approx(13.333, abs=1e-3)


def test_long_moves_cruise_at_top_speed():
    # 4 m：加速 8.889 s，再走 r/v = 20 s
    assert bang_bang_seconds(4.0, 0.2, 0.0225) == pytest.approx(28.889, abs=1e-3)


def test_zero_amount_takes_no_time():
    assert bang_bang_seconds(0.0, 0.2, 0.0225) == 0.0


def test_moving_sideways_takes_longer_than_moving_forward():
    forward = move_seconds((0.0, 0.0, 0.0), IDENTITY_QUAT, (1.0, 0.0, 0.0), IDENTITY_QUAT)
    sideways = move_seconds((0.0, 0.0, 0.0), IDENTITY_QUAT, (0.0, 1.0, 0.0), IDENTITY_QUAT)
    overhead = DEFAULT_MOTION.overhead_sec
    assert forward - overhead == pytest.approx(2.0 * math.sqrt(1.0 / 0.022511), abs=1e-2)
    assert sideways - overhead == pytest.approx(2.0 * math.sqrt(1.0 / 0.012382), abs=1e-2)


def test_the_same_displacement_costs_differently_depending_on_start_attitude():
    # 起點姿態繞 Z 轉 90°：世界 +X 的位移在機體座標是 -Y（側向），比較慢。
    yawed = (0.0, 0.0, S, S)
    assert move_seconds((0.0, 0.0, 0.0), yawed, (1.0, 0.0, 0.0), yawed) > move_seconds(
        (0.0, 0.0, 0.0), IDENTITY_QUAT, (1.0, 0.0, 0.0), IDENTITY_QUAT
    )


def test_translation_and_rotation_add_up_because_they_run_one_after_the_other():
    yaw_90 = (0.0, 0.0, S, S)
    both = move_seconds((0.0, 0.0, 0.0), IDENTITY_QUAT, (1.0, 0.0, 0.0), yaw_90)
    only_move = move_seconds((0.0, 0.0, 0.0), IDENTITY_QUAT, (1.0, 0.0, 0.0), IDENTITY_QUAT)
    # 繞 Z 轉 90°：w²/α = 0.79 rad < 1.57 rad，會巡航：θ/w + w/α
    turn = (math.pi / 2.0) / 0.436332313 + 0.436332313 / 0.240891
    assert both - only_move == pytest.approx(turn, abs=1e-2)


def test_q_and_minus_q_are_the_same_target():
    yaw_90 = (0.0, 0.0, S, S)
    negated = (0.0, 0.0, -S, -S)
    a = move_seconds((0.0, 0.0, 0.0), IDENTITY_QUAT, (0.0, 0.0, 0.0), yaw_90)
    b = move_seconds((0.0, 0.0, 0.0), IDENTITY_QUAT, (0.0, 0.0, 0.0), negated)
    assert a == pytest.approx(b)
