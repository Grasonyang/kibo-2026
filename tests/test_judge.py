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


def test_fifteen_centimetres_sideways_also_costs_centering(cp1):
    # 側向偏 15 cm：機體中心離 marker 0.5 m，對中角 atan(0.15/0.5) 約 16.8°，位置與對中都是 Lv2。
    pose = Pose(add(cp1.position, (0.15, 0.0, 0.0)), cp1.attitude)
    result = judge(pose, cp1)
    assert (result.position_level, result.centering_level, result.level) == (2, 2, 2)


def test_outside_widest_band_fails(cp1):
    pose = Pose(add(cp1.position, (0.0, 0.0, 0.35)), cp1.attitude)
    assert not judge(pose, cp1).passed


def test_roll_of_15_degrees_about_line_of_sight_is_level_2(cp1):
    rolled = quat_mul(cp1.attitude, body_rotation((1.0, 0.0, 0.0), 15.0))
    result = judge(Pose(cp1.position, rolled), cp1)
    assert (result.roll_level, result.centering_level, result.level) == (2, 3, 2)


def test_yaw_of_12_degrees_drops_centering_to_level_2(cp1):
    # 對中從機體中心量，轉 12° 就是 12°。
    yawed = quat_mul(cp1.attitude, body_rotation((0.0, 0.0, 1.0), 12.0))
    result = judge(Pose(cp1.position, yawed), cp1)
    assert (result.centering_level, result.roll_level, result.level) == (2, 3, 2)


def test_yaw_of_35_degrees_fails_centering(cp1):
    yawed = quat_mul(cp1.attitude, body_rotation((0.0, 0.0, 1.0), 35.0))
    assert not judge(Pose(cp1.position, yawed), cp1).passed


def test_overall_level_is_the_lowest_of_the_three(cp1):
    rolled = quat_mul(cp1.attitude, body_rotation((1.0, 0.0, 0.0), 15.0))  # roll Lv2
    pose = Pose(
        add(cp1.position, scale((0.0, -1.0, 0.0), 0.25)), rolled
    )  # 沿視線靠近：position Lv1
    result = judge(pose, cp1)
    assert (result.position_level, result.roll_level, result.level) == (1, 2, 1)


def test_roll_error_grows_when_the_line_of_sight_is_off(cp1):
    # 機體自己只滾了 25°（Lv1），但側偏 12 cm 讓視線歪 13.5°，官方量到的滾轉約 32°，整點 0 分。
    rolled = quat_mul(cp1.attitude, body_rotation((1.0, 0.0, 0.0), 25.0))
    result = judge(Pose(add(cp1.position, (0.12, 0.0, 0.0)), rolled), cp1)
    assert result.roll_deg == pytest.approx(31.98, abs=0.01)
    assert not result.passed


def test_value_exactly_on_a_band_limit_gets_that_level():
    from kibo.checkpoints import Band
    from kibo.judge import level_for

    bands = [Band(0.1, 3), Band(0.2, 2), Band(0.3, 1)]
    assert level_for(0.1, bands) == 3
    assert level_for(0.1000001, bands) == 2
    assert level_for(0.3, bands) == 1
    assert level_for(0.3000001, bands) == 0


def test_target_attitude_keeps_server_attitude_when_it_points_at_marker(cp1):
    from kibo.judge import target_attitude

    assert target_attitude(cp1) == cp1.attitude


def test_target_attitude_falls_back_to_look_at_when_server_attitude_is_off(cp1):
    from kibo.judge import target_attitude

    pointing_away = quat_mul(cp1.attitude, body_rotation((0.0, 0.0, 1.0), 90.0))
    broken = cp1._replace(attitude=pointing_away)
    fixed = target_attitude(broken)
    assert fixed != pointing_away
    assert judge(Pose(broken.position, fixed), broken).centering_level == 3


def test_camera_offset_switch_changes_centering_only(cp1):
    # 預設照官方 judge.py 從機體中心量；camera_offset 留著只為了能回頭比較。
    sideways = Pose(add(cp1.position, (0.15, 0.0, 0.0)), cp1.attitude)
    from_body = judge(sideways, cp1)
    with_camera = judge(sideways, cp1, camera_offset=(0.14, 0.0, 0.0))
    assert with_camera.centering_deg > from_body.centering_deg
    assert with_camera.position_level == from_body.position_level == 2


# 黃金值：把官方模擬器 rootfs/krpc/judge_module/judge.py 的 _evaluate_centering_and_roll 與
# distance_3d 原封不動抽出來執行得到的（krpc7th-simulator.tar.gz，2026-10-05 版）。
# 每列：位置、姿態、官方算出的距離、對中角、滾轉角。目標是手冊 6.3.1 的 CheckPoint 1。
OFFICIAL_GOLDEN = [
    (
        "side15",
        (1.5921152111823451, -0.5013235815457989, 0.6649623093633403),
        (0.705928907230986, -0.689998801417597, 0.12254331978784033, -0.10270913665940805),
        0.15,
        16.78122141102894,
        0.0,
    ),
    (
        "yaw12",
        (1.4421152111823452, -0.5013235815457989, 0.6649623093633403),
        (0.62993724044591, -0.7600085796367342, 0.11113598644156807, -0.11495575016329307),
        0.0,
        12.0,
        0.33548226923119273,
    ),
    (
        "roll15",
        (1.4421152111823452, -0.5013235815457989, 0.6649623093633403),
        (0.6864833550550289, -0.6681006531056538, 0.21155786088478032, -0.1939726579960332),
        0.0,
        0.0,
        15.0,
    ),
    (
        "mixed",
        (1.4921152111823452, -0.4713235815457989, 0.6049623093633403),
        (0.6552924397741359, -0.6985782960051894, 0.21093390986788618, -0.19515908483386912),
        0.08366600265340762,
        7.918093716456801,
        14.406998444338228,
    ),
    (
        "roll170",
        (1.4421152111823452, -0.5013235815457989, 0.6649623093633403),
        (-0.04079253914892359, 0.061939647426663295, 0.6980535017167423, -0.7121943257057294),
        0.0,
        0.0,
        170.0,
    ),
    (
        # 視線沒對準時，官方的滾轉（繞「機體到 marker」軸的 twist 差）會比機體自己轉的 25° 大。
        "pitch8_roll-25",
        (1.4221152111823452, -0.4213235815457989, 0.6749623093633403),
        (0.6909296917204489, -0.7161136905596028, 0.016892982109455307, 0.09752933121702816),
        0.08306623862918078,
        9.841646985423123,
        30.940433409355137,
    ),
]


@pytest.mark.parametrize("name,position,orientation,dist,centering,roll", OFFICIAL_GOLDEN)
def test_judge_matches_the_official_judge_module(
    cp1, name, position, orientation, dist, centering, roll
):
    result = judge(Pose(position, orientation), cp1)
    assert result.distance_m == pytest.approx(dist, abs=1e-9)
    assert result.centering_deg == pytest.approx(centering, abs=1e-4)
    assert result.roll_deg == pytest.approx(roll, abs=1e-4)
