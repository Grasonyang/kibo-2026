import math

import pytest

from kibo.geometry import (
    IDENTITY_QUAT,
    angle_between,
    distance,
    forward,
    look_at,
    quat_angle,
    roll_error,
    rotate,
    sub,
)

S = math.sqrt(0.5)  # sin(45°) = cos(45°)，90° 旋轉的四元數分量
YAW_90 = (0.0, 0.0, S, S)  # 繞 Z 軸轉 90°
ROLL_30 = (math.sin(math.radians(15)), 0.0, 0.0, math.cos(math.radians(15)))  # 繞 X 軸轉 30°

# Programming Manual 6.3.1 的回應範例：伺服器給的 CheckPoint、marker 與目標姿態。
MANUAL_CP = (1.4421152111823452, -0.5013235815457989, 0.6649623093633403)
MANUAL_MARKER = (1.451, -1.001, 0.6806)
MANUAL_ATTITUDE = (0.705928907230986, -0.689998801417597, 0.12254331978784033, -0.10270913665940805)


def close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_distance_is_euclidean():
    assert distance((0.0, 0.0, 0.0), (3.0, 4.0, 0.0)) == pytest.approx(5.0)


def test_angle_between_perpendicular_vectors_is_90():
    assert angle_between((1.0, 0.0, 0.0), (0.0, 2.0, 0.0)) == pytest.approx(90.0)


def test_yaw_90_turns_forward_to_left():
    # 機體 +X 繞世界 Z 轉 90° 後指向世界 +Y。
    assert close(rotate(YAW_90, (1.0, 0.0, 0.0)), (0.0, 1.0, 0.0))


def test_identity_forward_is_plus_x():
    assert close(forward(IDENTITY_QUAT), (1.0, 0.0, 0.0))


def test_manual_attitude_points_exactly_at_marker():
    # 手冊範例：伺服器給的姿態應該讓相機正對 marker，否則我們的慣例有錯。
    to_marker = sub(MANUAL_MARKER, MANUAL_CP)
    assert angle_between(forward(MANUAL_ATTITUDE), to_marker) == pytest.approx(0.0, abs=0.01)


def test_look_at_points_forward_axis_at_target():
    q = look_at((0.0, 0.0, 0.0), (0.0, 2.0, 0.0))
    assert close(forward(q), (0.0, 1.0, 0.0))


def test_look_at_keeps_reference_up_when_possible():
    q = look_at((0.0, 0.0, 0.0), (0.0, 2.0, 0.0))
    assert close(rotate(q, (0.0, 0.0, 1.0)), (0.0, 0.0, 1.0))


def test_look_at_reproduces_manual_attitude_up_to_roll():
    q = look_at(MANUAL_CP, MANUAL_MARKER, reference=MANUAL_ATTITUDE)
    assert quat_angle(q, MANUAL_ATTITUDE) == pytest.approx(0.0, abs=0.05)


def test_roll_error_measures_rotation_about_line_of_sight():
    assert roll_error(ROLL_30, IDENTITY_QUAT) == pytest.approx(30.0)


def test_roll_error_is_zero_for_same_attitude():
    assert roll_error(MANUAL_ATTITUDE, MANUAL_ATTITUDE) == pytest.approx(0.0)


def test_quat_angle_between_identity_and_yaw_90():
    assert quat_angle(IDENTITY_QUAT, YAW_90) == pytest.approx(90.0)
