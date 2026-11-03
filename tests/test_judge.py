import math

import pytest

from kibo.checkpoints import parse_checkpoints
from kibo.geometry import add, quat_mul, scale
from kibo.judge import Pose, judge


@pytest.fixture
def cp1(three_point_message):
    return parse_checkpoints(three_point_message).by_id(1)


def body_rotation(axis, degrees):
    """繞機體某軸轉 degrees 的四元數（右乘到目前姿態上）。"""
    half = math.radians(degrees) / 2.0
    s = math.sin(half)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half))


def test_exact_server_pose_is_level_3(cp1):
    result = judge(Pose(cp1.position, cp1.attitude), cp1)
    assert result.level == 3
    assert result.passed


def test_fifteen_centimetres_closer_along_line_of_sight_is_level_2(cp1):
    # 沿視線往 marker 靠近 15 cm：對中與滾轉不變，只有位置掉到 Lv2。
    pose = Pose(add(cp1.position, (0.0, -0.15, 0.0)), cp1.attitude)
    result = judge(pose, cp1)
    assert (result.position_level, result.centering_level, result.level) == (2, 3, 2)


def test_fifteen_centimetres_sideways_also_breaks_centering(cp1):
    # 側向偏 15 cm：相機離 marker 只有 0.36 m，對中角約 22°，所以整體只剩 Lv1。
    pose = Pose(add(cp1.position, (0.15, 0.0, 0.0)), cp1.attitude)
    result = judge(pose, cp1)
    assert (result.position_level, result.centering_level, result.level) == (2, 1, 1)


def test_outside_widest_band_fails(cp1):
    pose = Pose(add(cp1.position, (0.0, 0.0, 0.35)), cp1.attitude)
    assert not judge(pose, cp1).passed


def test_roll_of_15_degrees_about_line_of_sight_is_level_2(cp1):
    rolled = quat_mul(cp1.attitude, body_rotation((1.0, 0.0, 0.0), 15.0))
    result = judge(Pose(cp1.position, rolled), cp1)
    assert (result.roll_level, result.centering_level, result.level) == (2, 3, 2)


def test_yaw_of_12_degrees_drops_centering_to_level_2(cp1):
    # 轉 12° 加上相機位移帶來的視差，對中角約 16°。
    yawed = quat_mul(cp1.attitude, body_rotation((0.0, 0.0, 1.0), 12.0))
    result = judge(Pose(cp1.position, yawed), cp1)
    assert (result.centering_level, result.roll_level, result.level) == (2, 3, 2)


def test_yaw_of_25_degrees_fails_centering(cp1):
    yawed = quat_mul(cp1.attitude, body_rotation((0.0, 0.0, 1.0), 25.0))
    assert not judge(Pose(cp1.position, yawed), cp1).passed


def test_overall_level_is_the_lowest_of_the_three(cp1):
    rolled = quat_mul(cp1.attitude, body_rotation((1.0, 0.0, 0.0), 25.0))  # roll Lv1
    pose = Pose(add(cp1.position, scale((1.0, 0.0, 0.0), 0.12)), rolled)  # position Lv2
    assert judge(pose, cp1).level == 1
