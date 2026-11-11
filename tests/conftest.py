"""共用的測試資料。

CheckPoint 1 直接取自 Programming Manual 6.3.1 的回應範例。CheckPoint 6 與 Goal（12）
是依同樣規則手工造的：位置在 marker 法線方向 0.5 到 0.6 公尺處，姿態正對 marker。
"""

import json

import pytest

from kibo.checkpoints import Checkpoint
from kibo.geometry import IDENTITY_QUAT
from kibo_lab.fake_robot import FakeRobotConfig

# 沒有任何誤差的假機器人：到點分毫不差、導航不抖。測流程時用，免得亂數干擾。
PERFECT = FakeRobotConfig(position_noise_m=0.0, attitude_noise_deg=0.0, nav_jitter_m=0.0)


def checkpoint_at(cp_id, position, attitude=IDENTITY_QUAT):
    """只有位置與姿態的 CheckPoint（marker 就放在同一點、沒有餘裕表），測路線與預算用。"""
    return Checkpoint(cp_id, position, position, IDENTITY_QUAT, attitude, [], [], [])


MANUAL_CHECKPOINT_1 = {
    "checkpoint_id": 1,
    "position": [1.4421152111823452, -0.5013235815457989, 0.6649623093633403],
    "marker_pose": {
        "position": [1.451, -1.001, 0.6806],
        "quaternion": [-0.707106781187, 0.0, 0.0, 0.707106781187],
    },
    "score_bands": [
        {"radius": 0.1, "level": 3},
        {"radius": 0.2, "level": 2},
        {"radius": 0.3, "level": 1},
    ],
    "attitude": {
        "quaternion": [
            0.705928907230986,
            -0.689998801417597,
            0.12254331978784033,
            -0.10270913665940805,
        ],
        "centering_bands": [
            {"angle": 10.0, "level": 3},
            {"angle": 20.0, "level": 2},
            {"angle": 30.0, "level": 1},
        ],
        "roll_bands": [
            {"angle": 10.0, "level": 3},
            {"angle": 20.0, "level": 2},
            {"angle": 30.0, "level": 1},
        ],
    },
}

CHECKPOINT_6 = {
    "checkpoint_id": 6,
    "position": [1.895, -0.282, 0.3918188],
    "marker_pose": {"position": [1.895, -0.282, -0.208], "quaternion": [0.0, 0.0, 0.707, -0.707]},
    "score_bands": MANUAL_CHECKPOINT_1["score_bands"],
    "attitude": {
        "quaternion": [-0.5, 0.5, 0.5, 0.5],
        "centering_bands": MANUAL_CHECKPOINT_1["attitude"]["centering_bands"],
        "roll_bands": MANUAL_CHECKPOINT_1["attitude"]["roll_bands"],
    },
}

GOAL_12 = {
    "checkpoint_id": 12,
    "position": [0.5, -0.059, -0.102],
    "marker_pose": {"position": [0.0, -0.059, -0.102], "quaternion": [-0.5, 0.5, -0.5, 0.5]},
    "score_bands": MANUAL_CHECKPOINT_1["score_bands"],
    "attitude": {
        "quaternion": [0.0, 0.0, 1.0, 0.0],
        "centering_bands": MANUAL_CHECKPOINT_1["attitude"]["centering_bands"],
        "roll_bands": MANUAL_CHECKPOINT_1["attitude"]["roll_bands"],
    },
}


def checkpoints_message(checkpoints, goal_id=12):
    return json.dumps(
        {"checkpoint_count": len(checkpoints), "checkpoints": checkpoints, "goalpoint_id": goal_id}
    )


@pytest.fixture
def three_point_message():
    return checkpoints_message([MANUAL_CHECKPOINT_1, CHECKPOINT_6, GOAL_12])
