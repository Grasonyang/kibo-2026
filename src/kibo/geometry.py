"""幾何工具：向量與四元數。

為什麼自己寫：執行環境是 Python 3.6 的 ROS 映像，不能保證有 scipy；
ROS 的 tf 又要在節點裡才能用。這裡只需要幾個很小的運算，自己寫最穩。

慣例（與規則書、ROS 一致）：
- 位置是 (x, y, z) 公尺。
- 姿態是四元數 (x, y, z, w)，代表「把機體座標系轉到世界座標系」的旋轉。
- 機體座標系：+X 是機頭（相機視線），+Y 是左，+Z 是上。
"""

import math
from typing import Tuple

Vec3 = Tuple[float, float, float]
Quat = Tuple[float, float, float, float]

IDENTITY_QUAT: Quat = (0.0, 0.0, 0.0, 1.0)
FORWARD: Vec3 = (1.0, 0.0, 0.0)
UP: Vec3 = (0.0, 0.0, 1.0)


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(v: Vec3, k: float) -> Vec3:
    return (v[0] * k, v[1] * k, v[2] * k)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(v: Vec3) -> float:
    return math.sqrt(dot(v, v))


def distance(a: Vec3, b: Vec3) -> float:
    return norm(sub(a, b))


def normalize(v: Vec3) -> Vec3:
    n = norm(v)
    if n == 0.0:
        raise ValueError("cannot normalize a zero vector")
    return scale(v, 1.0 / n)


def angle_between(a: Vec3, b: Vec3) -> float:
    """兩向量的夾角，單位是度。任一向量為零時方向無定義，回 180 當作最差。"""
    denominator = norm(a) * norm(b)
    if denominator == 0.0:
        return 180.0
    c = dot(a, b) / denominator
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def quat_mul(a: Quat, b: Quat) -> Quat:
    """Hamilton 乘積 a*b：先做 b 的旋轉，再做 a 的旋轉。"""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_conj(q: Quat) -> Quat:
    """單位四元數的共軛就是反向旋轉。"""
    return (-q[0], -q[1], -q[2], q[3])


def quat_normalize(q: Quat) -> Quat:
    n = math.sqrt(sum(c * c for c in q))
    if n == 0.0:
        raise ValueError("cannot normalize a zero quaternion")
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def rotate(q: Quat, v: Vec3) -> Vec3:
    """把機體座標系的向量 v 轉到世界座標系。"""
    x, y, z, _ = quat_mul(quat_mul(q, (v[0], v[1], v[2], 0.0)), quat_conj(q))
    return (x, y, z)


def forward(q: Quat) -> Vec3:
    """姿態 q 之下，相機視線在世界座標系的方向。"""
    return rotate(q, FORWARD)


def quat_angle(a: Quat, b: Quat) -> float:
    """兩個姿態之間要轉多少度才能重合（最短路徑）。"""
    d = abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3])
    return math.degrees(2.0 * math.acos(min(1.0, d)))


def quat_from_axes(x_axis: Vec3, y_axis: Vec3, z_axis: Vec3) -> Quat:
    """由三個正交單位軸（旋轉矩陣的三個欄）組出四元數。"""
    m00, m10, m20 = x_axis
    m01, m11, m21 = y_axis
    m02, m12, m22 = z_axis
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        return quat_normalize(((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s))
    if m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        return quat_normalize((0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s))
    if m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        return quat_normalize(((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s))
    s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
    return quat_normalize(((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s))


def look_at(eye: Vec3, target: Vec3, reference: Quat = IDENTITY_QUAT) -> Quat:
    """算出一個姿態：視線（+X）從 eye 指向 target，滾轉盡量貼近 reference。

    做法：把 reference 的「上」向量投影到與視線垂直的平面，當作新的上。
    若 reference 的上剛好與視線平行（極罕見），改用世界的 Z 軸或 Y 軸。
    """
    x_axis = normalize(sub(target, eye))
    for candidate in (rotate(reference, UP), UP, (0.0, 1.0, 0.0)):
        z_axis = sub(candidate, scale(x_axis, dot(candidate, x_axis)))
        if norm(z_axis) > 1e-6:
            z_axis = normalize(z_axis)
            break
    y_axis = cross(z_axis, x_axis)
    return quat_from_axes(x_axis, y_axis, z_axis)
