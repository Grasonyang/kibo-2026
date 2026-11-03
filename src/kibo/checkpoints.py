"""把 `/mission/get_checkpoints` 回傳的 JSON 變成程式好用的結構。

伺服器回的是一段 JSON 字串（Programming Manual 6.3.1）。這個模組只做「讀懂它」，
不做任何決策。每個 CheckPoint 有三組餘裕（band）：

- position_bands：IB2 離 CheckPoint 中心多近（公尺），對應 Lv3/Lv2/Lv1。
- centering_bands：相機視線與「指向 marker」方向的夾角上限（度）。
- roll_bands：繞視線軸的滾轉誤差上限（度）。

bands 一律由嚴到寬排序（Lv3 在前），方便判定時從最高等級往下找。
"""

import json
from typing import Dict, List, NamedTuple, Optional

from kibo.geometry import Quat, Vec3


class Band(NamedTuple):
    limit: float  # 半徑（公尺）或角度（度）
    level: int  # 3 最嚴、1 最寬


class Checkpoint(NamedTuple):
    id: int
    position: Vec3
    marker_position: Vec3
    marker_orientation: Quat
    attitude: Quat  # 伺服器指定的目標姿態
    position_bands: List[Band]
    centering_bands: List[Band]
    roll_bands: List[Band]


class CheckpointSet(NamedTuple):
    checkpoints: List[Checkpoint]
    goal_id: int

    def by_id(self, checkpoint_id: int) -> Checkpoint:
        for cp in self.checkpoints:
            if cp.id == checkpoint_id:
                return cp
        raise KeyError(checkpoint_id)

    @property
    def goal(self) -> Checkpoint:
        return self.by_id(self.goal_id)

    @property
    def waypoints(self) -> List[Checkpoint]:
        """Goal 以外的 CheckPoint。"""
        return [cp for cp in self.checkpoints if cp.id != self.goal_id]


def _bands(raw: Optional[List[Dict]], key: str) -> List[Band]:
    if not raw:
        return []
    bands = [Band(float(b[key]), int(b["level"])) for b in raw]
    return sorted(bands, key=lambda b: -b.level)


def _vec3(raw) -> Vec3:
    return (float(raw[0]), float(raw[1]), float(raw[2]))


def _quat(raw) -> Quat:
    return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))


def parse_checkpoint(raw: Dict) -> Checkpoint:
    attitude = raw.get("attitude") or {}
    marker = raw["marker_pose"]
    return Checkpoint(
        id=int(raw["checkpoint_id"]),
        position=_vec3(raw["position"]),
        marker_position=_vec3(marker["position"]),
        marker_orientation=_quat(marker["quaternion"]),
        attitude=_quat(attitude["quaternion"]),
        position_bands=_bands(raw.get("score_bands"), "radius"),
        centering_bands=_bands(attitude.get("centering_bands"), "angle"),
        roll_bands=_bands(attitude.get("roll_bands"), "angle"),
    )


def parse_checkpoints(message: str) -> CheckpointSet:
    """`message` 是 CheckPoints.srv 回應裡的 JSON 字串。"""
    data = json.loads(message)
    checkpoints = [parse_checkpoint(raw) for raw in data["checkpoints"]]
    declared = int(data.get("checkpoint_count", len(checkpoints)))
    if declared != len(checkpoints):
        raise ValueError(
            "checkpoint_count=%d but %d checkpoints listed" % (declared, len(checkpoints))
        )
    goal_id = int(data["goalpoint_id"])
    if all(cp.id != goal_id for cp in checkpoints):
        raise ValueError("goalpoint_id=%d is not one of the checkpoints" % goal_id)
    return CheckpointSet(checkpoints=checkpoints, goal_id=goal_id)
