"""隨機場景：用官方產生器的同一套規則產生一組 CheckPoint，讓本機可以跑很多場取平均。

規則照抄官方模擬器的 `rootfs/krpc/random_env_generator/generate_objects.py`
（krpc7th-simulator.tar.gz，2026-10-05 版）：

- CheckPoint 離 marker 固定 0.5 m；方向是 marker 法線偏航 ±20°、俯仰 ±15°（均勻）。
- 落在安全區外就重抽，最多 50 次；還不行就用正前方，再不行就夾進安全區。
- 目標姿態：機頭正對 marker，再繞視線軸滾 ±180°（均勻）。
- 位置餘裕 0.1／0.2／0.3 m，對中與滾轉餘裕 10／20／30°，對應 Lv3／Lv2／Lv1。
- Goal 固定是 marker 12；難度決定總點數（含 Goal）：easy 6、normal 8、hard 10、veryhard 12。

亂數序列與官方不同（官方不固定種子），所以只是同分布，不是同一場。
"""

import json
import math
import random
from typing import Dict, List

from kibo.field import MARKERS, SAFE_AREA_MAX, SAFE_AREA_MIN, Marker
from kibo.geometry import FORWARD, Vec3, add, axis_angle_quat, look_at, quat_mul, rotate, scale

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
LEVEL_COUNTS = {"easy": 6, "normal": 8, "hard": 10, "veryhard": 12}  # 含 Goal

CHECKPOINT_DISTANCE_M = 0.5
YAW_RANGE_DEG = 20.0
PITCH_RANGE_DEG = 15.0
SAFE_AREA_MAX_RETRY = 50


def _inside_safe_area(position: Vec3) -> bool:
    return all(SAFE_AREA_MIN[i] <= position[i] <= SAFE_AREA_MAX[i] for i in range(3))


def _offset_position(marker: Marker, yaw_deg: float, pitch_deg: float) -> Vec3:
    """marker 局部座標：+Z 是法線，偏航往 +X 偏、俯仰往 +Y 偏。"""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    local = (math.cos(pitch) * math.sin(yaw), math.sin(pitch), math.cos(pitch) * math.cos(yaw))
    direction = rotate(marker.pose.orientation, local)
    return add(marker.pose.position, scale(direction, CHECKPOINT_DISTANCE_M))


def checkpoint_position(marker: Marker, rng: random.Random) -> Vec3:
    for _ in range(SAFE_AREA_MAX_RETRY):
        position = _offset_position(
            marker,
            rng.uniform(-YAW_RANGE_DEG, YAW_RANGE_DEG),
            rng.uniform(-PITCH_RANGE_DEG, PITCH_RANGE_DEG),
        )
        if _inside_safe_area(position):
            return position
    straight = _offset_position(marker, 0.0, 0.0)
    if _inside_safe_area(straight):
        return straight
    return (
        min(max(straight[0], SAFE_AREA_MIN[0]), SAFE_AREA_MAX[0]),
        min(max(straight[1], SAFE_AREA_MIN[1]), SAFE_AREA_MAX[1]),
        min(max(straight[2], SAFE_AREA_MIN[2]), SAFE_AREA_MAX[2]),
    )


def checkpoint_from_marker(marker: Marker, rng: random.Random) -> Dict:
    position = checkpoint_position(marker, rng)
    attitude = look_at(position, marker.pose.position)
    attitude = quat_mul(attitude, axis_angle_quat(FORWARD, rng.uniform(-180.0, 180.0)))
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
    """count 包含 Goal；官方四個難度是 6、8、10、12（`LEVEL_COUNTS`）。回傳的清單照 id 排序。"""
    if not 2 <= count <= len(MARKERS):
        raise ValueError("count must be between 2 and %d" % len(MARKERS))
    rng = random.Random(seed)
    others = [m for m in MARKERS.values() if m.id != GOAL_MARKER_ID]
    chosen: List[Marker] = rng.sample(others, count - 1) + [MARKERS[GOAL_MARKER_ID]]
    checkpoints = sorted(
        (checkpoint_from_marker(m, rng) for m in chosen), key=lambda cp: cp["checkpoint_id"]
    )
    return json.dumps(
        {"checkpoint_count": count, "checkpoints": checkpoints, "goalpoint_id": GOAL_MARKER_ID}
    )
