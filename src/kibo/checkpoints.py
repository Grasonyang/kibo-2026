"""把 `/mission/get_checkpoints` 回傳的 JSON 變成程式好用的結構。

伺服器回的是一段 JSON 字串（Programming Manual 6.3.1）。這個模組只做「讀懂它」，
不做任何決策。每個 CheckPoint 有三組餘裕（band）：

- position_bands：IB2 離 CheckPoint 中心多近（公尺），對應 Lv3/Lv2/Lv1。
- centering_bands：相機視線與「指向 marker」方向的夾角上限（度）。
- roll_bands：繞視線軸的滾轉誤差上限（度）。

bands 一律由嚴到寬排序（Lv3 在前），方便判定時從最高等級往下找。
"""

import json
from typing import Dict, List, NamedTuple, Optional, Tuple

from kibo.geometry import Quat, Vec3, look_at


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
    warnings: Tuple[str, ...] = ()  # 解析時降級處理的事，任務開始時要 log

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


_STRUCTURE_ERRORS = (KeyError, TypeError, IndexError, AttributeError, ValueError)


def parse_checkpoint(raw: Dict) -> Checkpoint:
    """單一 CheckPoint。缺 attitude 時自己算一個正對 marker 的姿態（手冊 4.3.1 的 N/A 點
    可能長這樣）；其他欄位缺就讓呼叫端跳過這一點。"""
    marker = raw["marker_pose"]
    position = _vec3(raw["position"])
    marker_position = _vec3(marker["position"])
    attitude_raw = raw.get("attitude") or {}
    if attitude_raw.get("quaternion"):
        attitude = _quat(attitude_raw["quaternion"])
    else:
        attitude = look_at(position, marker_position)
    return Checkpoint(
        id=int(raw["checkpoint_id"]),
        position=position,
        marker_position=marker_position,
        marker_orientation=_quat(marker["quaternion"]),
        attitude=attitude,
        position_bands=_bands(raw.get("score_bands"), "radius"),
        centering_bands=_bands(attitude_raw.get("centering_bands"), "angle"),
        roll_bands=_bands(attitude_raw.get("roll_bands"), "angle"),
    )


def parse_checkpoints(message: str) -> CheckpointSet:
    """`message` 是 CheckPoints.srv 回應裡的 JSON 字串。

    原則：能救就救，不整批作廢。單一點壞掉就跳過它；count 對不上以實際清單為準；
    goalpoint_id 不在清單就拿最後一點當終點。每個降級都記在 warnings。
    只有整段 JSON 壞掉或一個點都沒有才丟 ValueError，因為那時真的無事可做。
    """
    warnings: List[str] = []
    try:
        data = json.loads(message)
        raw_list = list(data["checkpoints"])
    except _STRUCTURE_ERRORS as exc:
        raise ValueError("unexpected checkpoints structure: %r" % (exc,)) from exc

    checkpoints: List[Checkpoint] = []
    for index, raw in enumerate(raw_list):
        try:
            checkpoints.append(parse_checkpoint(raw))
        except _STRUCTURE_ERRORS as exc:
            warnings.append("checkpoint #%d skipped: %r" % (index, exc))
    if not checkpoints:
        raise ValueError("no usable checkpoints")

    declared = data.get("checkpoint_count")
    if declared is not None and int(declared) != len(raw_list):
        warnings.append("checkpoint_count=%s but %d listed" % (declared, len(raw_list)))

    ids = [cp.id for cp in checkpoints]
    try:
        goal_id = int(data["goalpoint_id"])
    except _STRUCTURE_ERRORS:
        goal_id = ids[-1]
        warnings.append("goalpoint_id missing, using last checkpoint #%d" % goal_id)
    if goal_id not in ids:
        warnings.append(
            "goalpoint_id=%d not in list, using last checkpoint #%d" % (goal_id, ids[-1])
        )
        goal_id = ids[-1]
    return CheckpointSet(checkpoints=checkpoints, goal_id=goal_id, warnings=tuple(warnings))
