"""場地固定資料：AR marker 與 Int-Ball2 起點。

來源：Rulebook v1.1 表 2.2.2-2、2.2.2-3。座標原點是 Dock Station，
姿態是四元數，順序 (x, y, z, w)。
"""

from typing import Dict, NamedTuple, Tuple

Quaternion = Tuple[float, float, float, float]


class Pose(NamedTuple):
    position: Tuple[float, float, float]
    orientation: Quaternion


class Marker(NamedTuple):
    id: int
    target: str
    pose: Pose


def _marker(id_, target, x, y, z, qx, qy, qz, qw):
    return Marker(id_, target, Pose((x, y, z), (qx, qy, qz, qw)))


MARKERS: Dict[int, Marker] = {
    m.id: m
    for m in (
        _marker(1, "SAIBO", 1.451, -1.001, 0.681, -0.707, 0.000, 0.000, 0.707),
        _marker(2, "RYUTAI", 2.973, -1.001, 0.718, -0.707, 0.000, 0.000, 0.707),
        _marker(3, "MSPR_1", 3.313, -1.001, 0.523, -0.707, 0.000, 0.000, 0.707),
        _marker(4, "MSPR_2", 4.181, -1.001, 0.523, -0.707, 0.000, 0.000, 0.707),
        _marker(5, "RMS_Console", 5.754, -1.001, 0.838, -0.707, 0.000, 0.000, 0.707),
        _marker(6, "EPS1", 1.895, -0.282, -0.208, 0.000, 0.000, 0.707, -0.707),
        _marker(7, "MELFI1", 1.451, -1.001, 0.372, -0.707, 0.000, 0.000, 0.707),
        _marker(8, "EPS2_2", 4.779, 0.112, 1.884, -0.707, 0.707, 0.000, 0.000),
        _marker(9, "EPS2_1", 2.066, 1.046, -0.014, 0.000, 0.707, -0.707, 0.000),
        _marker(10, "ECLSS_TCS2", 5.851, 0.010, 1.884, -0.707, 0.707, 0.000, 0.000),
        _marker(11, "Airlock", 7.195, 0.363, 1.230, 0.500, 0.500, -0.500, -0.500),
        _marker(12, "Bay0_Closeout_Panel", 0.000, -0.059, -0.102, -0.500, 0.500, -0.500, 0.500),
    )
}

START_POSE = Pose((0.200, 0.000, 0.000), (0.000, 0.000, 0.000, 1.000))

# 規則書 2.2.2：任務時限 5 分鐘，從 Undock 完成起算。
TIME_LIMIT_SEC = 300
