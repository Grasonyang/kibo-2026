"""到點判定：IB2 現在這個姿態，在某個 CheckPoint 會拿到幾級？

這是我們自己對規則書 2.3.1 三個條件的實作，用來決定「現在可以送通過通知了嗎」。
真正給分的是伺服器；這裡的目的是不要送早，也不要在明明到了的時候還在等。

假設（拿到模擬器後要核對）：
- 「對中」用相機位置算。相機在機頭前方 0.14 m（手冊 5.13.2）。若模擬器顯示伺服器是用
  機體中心算，把 `camera_offset` 傳 `(0, 0, 0)` 即可（`MissionConfig.camera_offset_m`）。
"""

from typing import List, NamedTuple

from kibo.checkpoints import Band, Checkpoint
from kibo.geometry import (
    Quat,
    Vec3,
    add,
    angle_between,
    distance,
    forward,
    look_at,
    roll_error,
    rotate,
    sub,
)

CAMERA_OFFSET = (0.14, 0.0, 0.0)  # 機體座標系，公尺


class Pose(NamedTuple):
    position: Vec3
    orientation: Quat


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


def target_attitude(checkpoint: Checkpoint) -> Quat:
    """要用哪個姿態去 CheckPoint。

    正常用伺服器給的 attitude。保險：若那個姿態從 CheckPoint 位置看 marker 的對中角
    超過最嚴的餘裕（手冊範例是 0.0°，不該發生），就自己算一個「相機正對 marker、
    滾轉盡量貼近伺服器姿態」的姿態。
    """
    probe = Pose(checkpoint.position, checkpoint.attitude)
    to_marker = sub(checkpoint.marker_position, camera_position(probe))
    centering = angle_between(forward(checkpoint.attitude), to_marker)
    strictest = checkpoint.centering_bands[0].limit if checkpoint.centering_bands else 180.0
    if centering <= strictest:
        return checkpoint.attitude
    # 從機體位置算：視線對準 marker 後，相機（在視線上前方 0.14 m）看 marker 也剛好對中。
    return look_at(checkpoint.position, checkpoint.marker_position, reference=checkpoint.attitude)


def judge(pose: Pose, checkpoint: Checkpoint, camera_offset: Vec3 = CAMERA_OFFSET) -> Judgement:
    dist = distance(pose.position, checkpoint.position)
    to_marker = sub(checkpoint.marker_position, camera_position(pose, camera_offset))
    centering = angle_between(forward(pose.orientation), to_marker)
    roll = roll_error(pose.orientation, checkpoint.attitude)

    p = level_for(dist, checkpoint.position_bands)
    c = level_for(centering, checkpoint.centering_bands)
    r = level_for(roll, checkpoint.roll_bands)
    return Judgement(min(p, c, r), p, c, r, dist, centering, roll)
