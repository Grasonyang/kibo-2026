import pytest

from kibo.checkpoints import parse_checkpoints
from kibo.geometry import Pose, add, axis_angle_quat, quat_mul, scale
from kibo.judge import judge


@pytest.fixture
def cp1(three_point_message):
    return parse_checkpoints(three_point_message).by_id(1)


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
    rolled = quat_mul(cp1.attitude, axis_angle_quat((1.0, 0.0, 0.0), 15.0))
    result = judge(Pose(cp1.position, rolled), cp1)
    assert (result.roll_level, result.centering_level, result.level) == (2, 3, 2)


def test_yaw_of_12_degrees_drops_centering_to_level_2(cp1):
    # 對中從機體中心量，轉 12° 就是 12°。
    yawed = quat_mul(cp1.attitude, axis_angle_quat((0.0, 0.0, 1.0), 12.0))
    result = judge(Pose(cp1.position, yawed), cp1)
    assert (result.centering_level, result.roll_level, result.level) == (2, 3, 2)


def test_yaw_of_35_degrees_fails_centering(cp1):
    yawed = quat_mul(cp1.attitude, axis_angle_quat((0.0, 0.0, 1.0), 35.0))
    assert not judge(Pose(cp1.position, yawed), cp1).passed


def test_overall_level_is_the_lowest_of_the_three(cp1):
    rolled = quat_mul(cp1.attitude, axis_angle_quat((1.0, 0.0, 0.0), 15.0))  # roll Lv2
    pose = Pose(
        add(cp1.position, scale((0.0, -1.0, 0.0), 0.25)), rolled
    )  # 沿視線靠近：position Lv1
    result = judge(pose, cp1)
    assert (result.position_level, result.roll_level, result.level) == (1, 2, 1)


def test_roll_error_grows_when_the_line_of_sight_is_off(cp1):
    # 機體自己只滾了 25°（Lv1），但側偏 12 cm 讓視線歪 13.5°，官方量到的滾轉約 32°，整點 0 分。
    rolled = quat_mul(cp1.attitude, axis_angle_quat((1.0, 0.0, 0.0), 25.0))
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

    pointing_away = quat_mul(cp1.attitude, axis_angle_quat((0.0, 0.0, 1.0), 90.0))
    broken = cp1._replace(attitude=pointing_away)
    fixed = target_attitude(broken)
    assert fixed != pointing_away
    assert judge(Pose(broken.position, fixed), broken).centering_level == 3


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


def test_top_band_usage_is_the_tightest_of_the_three_margins(cp1):
    from kibo.judge import top_band_usage

    rolled = quat_mul(cp1.attitude, axis_angle_quat((1.0, 0.0, 0.0), 8.0))
    assert top_band_usage(judge(Pose(cp1.position, rolled), cp1), cp1) == pytest.approx(0.8)
    # 側偏 5 cm：位置用掉 0.05/0.1 = 5 成，對中 atan(0.05/0.5) = 5.7° 用掉 5.7 成
    sideways = judge(Pose(add(cp1.position, (0.05, 0.0, 0.0)), cp1.attitude), cp1)
    assert top_band_usage(sideways, cp1) == pytest.approx(0.571, abs=0.001)


def test_roll_reading_at_the_goal_marker_amplifies_small_pointing_errors():
    # 官方的滾轉是對「機體到 marker」軸做 twist 分解。Goal（marker 12）的視線幾乎正對世界 -X，
    # 姿態接近繞垂直軸轉 180°，分解在那附近是病態的：只有 1.5° 的指向誤差（機體完全沒滾），
    # 讀數就可能超過 5°。同樣的誤差在其他 marker 只讀到 2° 以內。
    from kibo.scenarios import random_checkpoints_message

    worst = {}
    for seed in range(10):
        for cp in parse_checkpoints(random_checkpoints_message(12, seed)).checkpoints:
            for axis in ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)):
                off = quat_mul(cp.attitude, axis_angle_quat(axis, 1.5))
                reading = judge(Pose(cp.position, off), cp).roll_deg
                worst[cp.id] = max(worst.get(cp.id, 0.0), reading)
    assert worst[12] > 5.0
    assert all(reading < 2.5 for cp_id, reading in worst.items() if cp_id != 12)
