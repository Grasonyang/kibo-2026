"""移動時間模型：一次 MOVE_TO_ABSOLUTE_TARGET 要花幾秒？

不是量出來的經驗公式，是照 Int-Ball2 控制器的原始碼算的（上游 jaxa/int-ball2_simulator
的 `ctl_only`：`pos_att_profiler.cpp`、`thrust_allocator.cpp`、`ctl.yaml`），再用本機模擬器的
實測核對過（docs/kibo/motion-model.md）。三件事決定時間：

1. **先平移、平移完才轉向**（`SEQUENCE::POS_ATT`），所以兩段時間相加，不是取大的。
2. 兩段都是 bang-bang 剖面：全力加速、（夠遠才）等速巡航、全力減速。
   短程是 2√(量／加速度)，所以 0.3 m 也要 8 秒，「距離 ÷ 速度」的模型會低估短腿。
3. **加速度看方向**。八顆風扇斜著裝，推力上限是「最吃力那顆風扇不超過 eta x 上限」。
   沿機體 X 軸最快（0.0225 m/s²），沿 Y 軸只有一半，斜向更慢。平移時機體還是上一個點的
   姿態，所以同一段位移，從不同的點出發，時間可以差到 1.5 倍。

數字是模擬器的參數；實機的參數可能不同，但公式的形狀相同。
"""

import math
from typing import List, NamedTuple, Sequence, Tuple

from kibo.geometry import Quat, Vec3, norm, quat_conj, quat_mul, rotate, sub

# 推力配置表（ctl.yaml 的 fan/Wp、fan/Wm）：每列一顆風扇，六欄是 Fx Fy Fz Tx Ty Tz。
# Wp 用在該分量為正時，Wm 用在為負時。
_WP: Tuple[Tuple[float, ...], ...] = (
    (0.0, 0.0, 0.0, 0.0, 0.0, 7.3257),
    (0.0, 0.6027, 0.0, 19.8198, 0.0, 0.0),
    (0.0, 0.6027, 0.4911, 0.0, 13.1935, 0.0),
    (0.0, 0.0, 0.4911, 19.8198, 13.1935, 7.3257),
    (0.3315, 0.0, 0.4911, 19.8198, 0.0, 0.0),
    (0.3315, 0.0, 0.0, 0.0, 13.1935, 0.0),
    (0.3315, 0.6027, 0.0, 19.8198, 13.1935, 7.3257),
    (0.3315, 0.6027, 0.4911, 0.0, 0.0, 7.3257),
)
_WM: Tuple[Tuple[float, ...], ...] = (
    (0.3315, 0.6027, 0.4911, 19.8198, 13.1935, 0.0),
    (0.3315, 0.0, 0.4911, 0.0, 13.1935, 7.3257),
    (0.3315, 0.0, 0.0, 19.8198, 0.0, 7.3257),
    (0.3315, 0.6027, 0.0, 0.0, 0.0, 0.0),
    (0.0, 0.6027, 0.0, 0.0, 13.1935, 7.3257),
    (0.0, 0.6027, 0.4911, 19.8198, 0.0, 7.3257),
    (0.0, 0.0, 0.4911, 0.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 19.8198, 13.1935, 0.0),
)


class MotionModel(NamedTuple):
    mass_kg: float = 3.216  # ctl_body/mass
    inertia_kgm2: float = 0.0136  # ctl_body/Is，三軸相同
    fan_max_n: float = 0.06  # fan/Fmax
    eta: float = 0.4  # pos_profile/eta：剖面只用到風扇上限的這個比例
    v_max_mps: float = 0.20  # pos_profile/v_max
    w_max_radps: float = 0.436332313  # att_profile/w_max（25°/s）
    # 剖面結束到「可以回報」之間多等的時間。控制器要在容差（10 cm、0.5 rad）內連續待滿 3 秒
    # 才回報成功（ctl/duration_goal），但進容差比剖面結束早 3 秒左右，兩者大致抵銷：
    # 實測 action 回來的時刻與剖面結束只差 -0.95 ± 2.05 秒（docs/kibo/motion-model.md），取 0。
    overhead_sec: float = 0.0


DEFAULT_MOTION = MotionModel()


def _worst_fan(wrench: Sequence[float]) -> float:
    """單位力或力矩 `wrench`（Fx Fy Fz Tx Ty Tz）下，最吃力的風扇要出多少（已扣掉共同的底）。"""
    loads: List[float] = []
    for plus, minus in zip(_WP, _WM):
        load = 0.0
        for k in range(6):
            load += (plus[k] if wrench[k] > 0.0 else minus[k]) * abs(wrench[k])
        loads.append(load)
    return max(loads) - min(loads)


def max_accel(direction_body: Vec3, model: MotionModel = DEFAULT_MOTION) -> float:
    """沿機體座標系某方向平移的最大加速度（m/s²）。"""
    length = norm(direction_body)
    if length <= 1e-9:
        direction_body, length = (1.0, 0.0, 0.0), 1.0
    unit = (direction_body[0] / length, direction_body[1] / length, direction_body[2] / length)
    worst = _worst_fan((unit[0], unit[1], unit[2], 0.0, 0.0, 0.0))
    return model.eta * model.fan_max_n / (worst * model.mass_kg)


def max_angular_accel(axis_body: Vec3, model: MotionModel = DEFAULT_MOTION) -> float:
    """繞機體座標系某軸轉動的最大角加速度（rad/s²）。"""
    length = norm(axis_body)
    if length <= 1e-9:
        axis_body, length = (1.0, 0.0, 0.0), 1.0
    unit = (axis_body[0] / length, axis_body[1] / length, axis_body[2] / length)
    worst = _worst_fan((0.0, 0.0, 0.0, unit[0], unit[1], unit[2]))
    return model.eta * model.fan_max_n / (worst * model.inertia_kgm2)


def bang_bang_seconds(amount: float, top_speed: float, accel: float) -> float:
    """全力加速、巡航、全力減速，走完 `amount` 要幾秒（`maneuverTiming`）。"""
    if amount <= 0.0:
        return 0.0
    if amount > top_speed * top_speed / accel:
        return amount / top_speed + top_speed / accel
    return 2.0 * math.sqrt(amount / accel)


def translation_seconds(
    from_pos: Vec3, from_att: Quat, to_pos: Vec3, model: MotionModel = DEFAULT_MOTION
) -> float:
    displacement_body = rotate(quat_conj(from_att), sub(to_pos, from_pos))
    return bang_bang_seconds(
        norm(displacement_body), model.v_max_mps, max_accel(displacement_body, model)
    )


def rotation_seconds(from_att: Quat, to_att: Quat, model: MotionModel = DEFAULT_MOTION) -> float:
    dq = quat_mul(quat_conj(from_att), to_att)
    if dq[3] < 0.0:  # q 與 -q 是同一個姿態；控制器也是這樣取最短的那一邊
        dq = (-dq[0], -dq[1], -dq[2], -dq[3])
    angle = 2.0 * math.acos(max(-1.0, min(1.0, dq[3])))
    axis = (dq[0], dq[1], dq[2])
    return bang_bang_seconds(angle, model.w_max_radps, max_angular_accel(axis, model))


def move_seconds(
    from_pos: Vec3,
    from_att: Quat,
    to_pos: Vec3,
    to_att: Quat,
    model: MotionModel = DEFAULT_MOTION,
) -> float:
    """從 (from_pos, from_att) 出發、到 (to_pos, to_att) 並等到 action 回報成功，預估幾秒。"""
    return (
        translation_seconds(from_pos, from_att, to_pos, model)
        + rotation_seconds(from_att, to_att, model)
        + model.overhead_sec
    )
