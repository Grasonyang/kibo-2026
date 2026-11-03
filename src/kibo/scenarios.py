"""隨機場景：照規則書的描述產生一組 CheckPoint，讓本機可以像資格賽一樣跑很多次取平均。

規則（2.2.2）：CheckPoint 以 AR marker 為原點、用「指定的角度與距離」隨機產生；
手冊 6.3.1 的範例在 marker 法線方向 0.5 m 處，滾轉隨機。這裡的範圍是猜的：
距離 0.4 到 0.7 m，偏離法線最多 20°。Goal 固定用 marker 12（Dock 旁的面板），
與手冊範例的 goalpoint_id 一致。
"""

import json
import math
import random
from typing import Dict, List

from kibo.field import MARKERS, Marker
from kibo.geometry import UP, Quat, add, cross, look_at, normalize, quat_mul, rotate, scale

BANDS_POSITION = [
    {"radius": 0.1, "level": 3},
    {"radius": 0.2, "level": 2},
    {"radius": 0.3, "level": 1},
]
BANDS_ANGLE = [
    {"angle": 10.0, "level": 3},
    {"angle": 20.0, "level": 2},
    {"angle": 30.0, "level": 1},
]
GOAL_MARKER_ID = 12


def _roll_quat(degrees: float) -> Quat:
    half = math.radians(degrees) / 2.0
    return (math.sin(half), 0.0, 0.0, math.cos(half))


def checkpoint_from_marker(
    marker: Marker,
    rng: random.Random,
    min_dist: float = 0.4,
    max_dist: float = 0.7,
    max_tilt_deg: float = 20.0,
) -> Dict:
    normal = rotate(marker.pose.orientation, UP)
    # 隨機挑一個與法線垂直的方向，把法線往那邊傾斜一點。
    side = normalize(cross(normal, (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (0.0, 1.0, 0.0)))
    spin = rng.uniform(0, 2 * math.pi)
    side = add(scale(side, math.cos(spin)), scale(cross(normal, side), math.sin(spin)))
    tilt = math.radians(rng.uniform(0, max_tilt_deg))
    direction = normalize(add(scale(normal, math.cos(tilt)), scale(side, math.sin(tilt))))
    position = add(marker.pose.position, scale(direction, rng.uniform(min_dist, max_dist)))
    attitude = look_at(position, marker.pose.position)
    attitude = quat_mul(attitude, _roll_quat(rng.uniform(-180.0, 180.0)))
    return {
        "checkpoint_id": marker.id,
        "position": list(position),
        "marker_pose": {
            "position": list(marker.pose.position),
            "quaternion": list(marker.pose.orientation),
        },
        "score_bands": BANDS_POSITION,
        "attitude": {
            "quaternion": list(attitude),
            "centering_bands": BANDS_ANGLE,
            "roll_bands": BANDS_ANGLE,
        },
    }


def random_checkpoints_message(count: int, seed: int = 0) -> str:
    """count 包含 Goal；規則是 6 到 12 個。"""
    if not 2 <= count <= len(MARKERS):
        raise ValueError("count must be between 2 and %d" % len(MARKERS))
    rng = random.Random(seed)
    others = [m for m in MARKERS.values() if m.id != GOAL_MARKER_ID]
    chosen: List[Marker] = rng.sample(others, count - 1) + [MARKERS[GOAL_MARKER_ID]]
    checkpoints = [checkpoint_from_marker(m, rng) for m in chosen]
    return json.dumps(
        {"checkpoint_count": count, "checkpoints": checkpoints, "goalpoint_id": GOAL_MARKER_ID}
    )
