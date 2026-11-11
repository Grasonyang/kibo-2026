"""隨機場景要跟官方產生器（rootfs/krpc/random_env_generator/generate_objects.py）同一套規則。"""

import json
import math

import pytest

from kibo.checkpoints import parse_checkpoints
from kibo.field import MARKERS, SAFE_AREA_MAX, SAFE_AREA_MIN
from kibo.geometry import Pose, angle_between, distance, forward, rotate, sub
from kibo.judge import judge
from kibo_lab.scenarios import LEVEL_COUNTS, random_checkpoints_message

SEEDS = range(40)


def _all_checkpoints():
    for seed in SEEDS:
        for cp in parse_checkpoints(random_checkpoints_message(12, seed)).checkpoints:
            yield cp


def test_levels_match_the_official_difficulty_presets():
    assert LEVEL_COUNTS == {"easy": 6, "normal": 8, "hard": 10, "veryhard": 12}


def test_every_checkpoint_is_half_a_metre_from_its_marker():
    for cp in _all_checkpoints():
        assert distance(cp.position, cp.marker_position) == pytest.approx(0.5, abs=1e-6)


def test_every_checkpoint_is_inside_the_safe_area():
    for cp in _all_checkpoints():
        for axis in range(3):
            assert SAFE_AREA_MIN[axis] <= cp.position[axis] <= SAFE_AREA_MAX[axis]


def test_checkpoints_stay_within_yaw_20_and_pitch_15_of_the_marker_normal():
    # 偏航 ±20°、俯仰 ±15° 合起來，離法線最多 acos(cos20·cos15) 約 24.8°。
    limit = math.degrees(math.acos(math.cos(math.radians(20)) * math.cos(math.radians(15))))
    for cp in _all_checkpoints():
        normal = rotate(MARKERS[cp.id].pose.orientation, (0.0, 0.0, 1.0))
        assert angle_between(sub(cp.position, cp.marker_position), normal) <= limit + 1e-6


def test_server_attitude_at_the_checkpoint_scores_level_3():
    for cp in _all_checkpoints():
        assert angle_between(forward(cp.attitude), sub(cp.marker_position, cp.position)) < 1e-4
        assert judge(Pose(cp.position, cp.attitude), cp).level == 3


def test_roll_is_spread_over_the_full_circle():
    # 官方的滾轉是 ±180° 均勻；機體的「上」應該朝各個方向都出現過。
    ups = [rotate(cp.attitude, (0.0, 0.0, 1.0)) for cp in _all_checkpoints() if cp.id == 1]
    assert min(u[2] for u in ups) < -0.5 and max(u[2] for u in ups) > 0.5
    assert min(u[0] for u in ups) < -0.5 and max(u[0] for u in ups) > 0.5


def test_goal_is_marker_12_and_always_included():
    for seed in SEEDS:
        data = json.loads(random_checkpoints_message(6, seed))
        assert data["goalpoint_id"] == 12
        assert 12 in [cp["checkpoint_id"] for cp in data["checkpoints"]]
        assert data["checkpoint_count"] == len(data["checkpoints"]) == 6


def test_goal_checkpoint_is_pushed_up_into_the_safe_area():
    # marker 12 在 z=-0.10，安全區 z>=0，所以 Goal 點只可能落在 z 0 到 0.03 這一小條。
    for seed in SEEDS:
        goal = parse_checkpoints(random_checkpoints_message(6, seed)).goal
        assert 0.0 <= goal.position[2] <= 0.03
