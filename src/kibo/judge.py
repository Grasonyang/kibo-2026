"""到點判定：IB2 現在這個姿態，在某個 CheckPoint 會拿到幾級？

照官方模擬器的評分模組（`rootfs/krpc/judge_module/judge.py` 的
`evaluate_checkpoint_navigation`）一步一步移植，用來決定「現在可以送通過通知了嗎」。
真正給分的是伺服器；這裡的目的是不要送早，也不要在明明到了的時候還在等。

官方的三個量（測試裡有從官方程式碼算出的黃金值）：
- 距離：機體中心到 CheckPoint 位置。
- 對中：機體 +X 軸與「機體中心指向 marker」的夾角。原點是**機體中心**，不是相機。
- 滾轉：把實際姿態與目標姿態各自對「機體中心指向 marker」這條軸做 twist 分解，取兩個
  twist 角的差。視線沒對準時，這個量會比「機體自己繞 X 軸轉了幾度」大。
等級取三者最低；任一項是 0 就整體 0。
"""

import math
from typing import List, NamedTuple, Optional

from kibo.checkpoints import Band, Checkpoint
from kibo.geometry import (
    Quat,
    Vec3,
    add,
    angle_between,
    distance,
    forward,
    look_at,
    norm,
    quat_normalize,
    rotate,
    scale,
    sub,
)

CAMERA_OFFSET = (0.14, 0.0, 0.0)  # 相機在機體座標系的位置（公尺）；影像換算用，判定不用
JUDGE_ORIGIN = (0.0, 0.0, 0.0)  # 官方判定的原點是機體中心


class Pose(NamedTuple):
    position: Vec3
    orientation: Quat
    stamp: Optional[float] = None  # 導航資料的時間戳（秒）；用來分辨是不是同一筆資料


class Judgement(NamedTuple):
    level: int  # 0 代表沒通過
    position_level: int
    centering_level: int
    roll_level: int
    distance_m: float
    centering_deg: float
    roll_deg: float

    @property
    def passed(self) -> bool:
        return self.level > 0


def level_for(value: float, bands: List[Band]) -> int:
    """value 落在哪一級。bands 由嚴到寬；沒有 bands 代表這項不評，視為最高級。"""
    if not bands:
        return 3
    for band in bands:
        if value <= band.limit:
            return band.level
    return 0


def camera_position(pose: Pose, camera_offset: Vec3 = CAMERA_OFFSET) -> Vec3:
    return add(pose.position, rotate(pose.orientation, camera_offset))


def twist_angle(q: Quat, axis: Vec3) -> float:
    """姿態 q 繞單位軸 axis 的 twist 角（度，有正負）。與官方 `_twist_angle_deg` 相同。"""
    x, y, z, w = quat_normalize(q)
    if w < 0.0:
        x, y, z, w = -x, -y, -z, -w
    return math.degrees(2.0 * math.atan2(x * axis[0] + y * axis[1] + z * axis[2], w))


def official_roll_error(actual: Quat, target: Quat, view: Vec3) -> float:
    """繞視線軸 view 的滾轉差（度，0 到 180）。view 長度為零時方向無定義，回 180 當最差。"""
    length = norm(view)
    if length <= 1e-9:
        return 180.0
    axis = scale(view, 1.0 / length)
    diff = twist_angle(actual, axis) - twist_angle(target, axis)
    return abs((diff + 180.0) % 360.0 - 180.0)


def target_attitude(checkpoint: Checkpoint) -> Quat:
    """要用哪個姿態去 CheckPoint。

    正常用伺服器給的 attitude（官方產生器保證它從 CheckPoint 位置正對 marker）。保險：
    若那個姿態的對中角超過最嚴的餘裕，就自己算一個「正對 marker、滾轉盡量貼近伺服器姿態」的。
    """
    to_marker = sub(checkpoint.marker_position, checkpoint.position)
    centering = angle_between(forward(checkpoint.attitude), to_marker)
    strictest = checkpoint.centering_bands[0].limit if checkpoint.centering_bands else 180.0
    if centering <= strictest:
        return checkpoint.attitude
    return look_at(checkpoint.position, checkpoint.marker_position, reference=checkpoint.attitude)


def judge(pose: Pose, checkpoint: Checkpoint, camera_offset: Vec3 = JUDGE_ORIGIN) -> Judgement:
    """`camera_offset` 預設是機體中心（官方做法）；只有要比較「若改用相機位置」時才傳別的。"""
    dist = distance(pose.position, checkpoint.position)
    origin = add(pose.position, rotate(pose.orientation, camera_offset))
    view = sub(checkpoint.marker_position, origin)
    centering = angle_between(forward(pose.orientation), view)
    roll = official_roll_error(pose.orientation, checkpoint.attitude, view)

    p = level_for(dist, checkpoint.position_bands)
    c = level_for(centering, checkpoint.centering_bands)
    r = level_for(roll, checkpoint.roll_bands)
    return Judgement(min(p, c, r), p, c, r, dist, centering, roll)
