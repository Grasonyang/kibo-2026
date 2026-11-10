"""場地固定資料：AR marker、安全區與 Int-Ball2 起點。

來源：官方模擬器的 `rootfs/krpc/random_env_generator/files/input/area_config.json`
（krpc7th-simulator.tar.gz，2026-10-05 版）。座標原點是 Dock Station，姿態是四元數
(x, y, z, w)。marker 的局部 +Z 是它的法線（朝艙內），CheckPoint 就產生在法線附近。
規則書表 2.2.2-2 的四元數寫法不同（只到三位小數），但法線方向一致。
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


_WALL = (-0.5, 0.5, 0.5, 0.5)  # 法線朝 +Y 的那面牆（marker 1 到 5、7）
_CEILING = (0.0, 1.0, 0.0, 0.0)  # 法線朝 -Z（marker 8、10）

MARKERS: Dict[int, Marker] = {
    m.id: m
    for m in (
        _marker(1, "SAIBO", 1.451, -1.001, 0.6806, *_WALL),
        _marker(2, "RYUTAI", 2.973, -1.001, 0.7176, *_WALL),
        _marker(3, "MSPR_1", 3.313, -1.001, 0.5226, *_WALL),
        _marker(4, "MSPR_2", 4.181, -1.001, 0.5226, *_WALL),
        _marker(5, "RMS_Console", 5.754, -1.001, 0.8376, *_WALL),
        _marker(6, "EPS1", 1.895, -0.282, -0.2084, 0.0, 0.0, 0.7071068, 0.7071068),
        _marker(7, "MELFI1", 1.451, -1.001, 0.3716, *_WALL),
        _marker(8, "EPS2_2", 4.779, 0.112, 1.8836, *_CEILING),
        _marker(9, "EPS2_1", 2.066, 1.046, -0.0144, -0.5, 0.5, -0.5, -0.5),
        _marker(10, "ECLSS_TCS2", 5.851, 0.010, 1.8836, *_CEILING),
        _marker(11, "Airlock", 7.195, 0.363, 1.2296, -0.5, 0.5, 0.5, -0.5),
        _marker(12, "Bay0_Closeout_Panel", 0.000, -0.059, -0.1024, -0.5, 0.5, -0.5, 0.5),
    )
}

# CheckPoint 只會產生在這個盒子裡（area_config.json 的 SafeArea）。
SAFE_AREA_MIN = (0.2, -0.8, 0.0)
SAFE_AREA_MAX = (7.0, 0.85, 1.68)

START_POSE = Pose((0.200, 0.000, 0.000), (0.000, 0.000, 0.000, 1.000))

# 規則書 2.2.2：任務時限 5 分鐘，從 Undock 完成起算。
TIME_LIMIT_SEC = 300
