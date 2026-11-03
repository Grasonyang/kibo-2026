"""路線規劃：決定拜訪 CheckPoint 的順序。

問題是「從起點出發，經過所有中途點各一次，最後停在 Goal，總成本最小」，
這是有固定終點的旅行推銷員問題。點數最多 12（規則書 2.2.2），用 Held-Karp
動態規劃（狀態 = 已拜訪集合 × 目前所在點，2^11 × 11）在幾毫秒內就能算出最佳解，
不需要啟發式。

成本不只是距離：IB2 到每一點都要轉到指定姿態，轉得越多越花時間。所以一段路的
成本 = 距離 / 線速度 + 轉角 / 角速度，單位是秒。速度參數是估計值，拿到模擬器後校正。
"""

from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from kibo.checkpoints import Checkpoint
from kibo.geometry import Quat, Vec3, distance, quat_angle


class Speeds(NamedTuple):
    linear_mps: float = 0.1  # 公尺／秒，保守估計
    angular_dps: float = 15.0  # 度／秒


DEFAULT_SPEEDS = Speeds()


class Leg(NamedTuple):
    to_id: int
    seconds: float


class Route(NamedTuple):
    order: List[int]  # CheckPoint id 的拜訪順序，最後一個是 Goal
    legs: List[Leg]

    @property
    def seconds(self) -> float:
        return sum(leg.seconds for leg in self.legs)


def leg_seconds(
    from_pos: Vec3, from_att: Quat, to_pos: Vec3, to_att: Quat, speeds: Speeds = DEFAULT_SPEEDS
) -> float:
    travel = distance(from_pos, to_pos) / speeds.linear_mps
    turn = quat_angle(from_att, to_att) / speeds.angular_dps
    return travel + turn


CostFn = Callable[[Vec3, Quat, Vec3, Quat], float]

# 規則書最多 12 個 CheckPoint，其中一個是 Goal；再多 Held-Karp 的狀態數會爆。
MAX_WAYPOINTS = 11


def plan_route(
    start_pos: Vec3,
    start_att: Quat,
    waypoints: List[Checkpoint],
    goal: Checkpoint,
    cost: Optional[CostFn] = None,
) -> Route:
    """回傳成本最小的順序。waypoints 可以是空的（只去 Goal）。"""
    cost_fn = cost or leg_seconds
    n = len(waypoints)
    if n > MAX_WAYPOINTS:
        raise ValueError("too many waypoints for exact search: %d" % n)

    # best[mask][i] = 從起點出發、拜訪 mask 裡的點、最後停在 waypoints[i] 的最小成本
    best: Dict[Tuple[int, int], float] = {}
    parent: Dict[Tuple[int, int], Optional[int]] = {}
    for i, wp in enumerate(waypoints):
        best[(1 << i, i)] = cost_fn(start_pos, start_att, wp.position, wp.attitude)
        parent[(1 << i, i)] = None

    for mask in range(1, 1 << n):
        for i in range(n):
            if (mask, i) not in best or not mask & (1 << i):
                continue
            here = waypoints[i]
            for j in range(n):
                if mask & (1 << j):
                    continue
                there = waypoints[j]
                candidate = best[(mask, i)] + cost_fn(
                    here.position, here.attitude, there.position, there.attitude
                )
                key = (mask | (1 << j), j)
                if candidate < best.get(key, float("inf")):
                    best[key] = candidate
                    parent[key] = i

    full = (1 << n) - 1
    if n == 0:
        order: List[int] = []
    else:
        last = min(
            range(n),
            key=lambda i: (
                best[(full, i)]
                + cost_fn(
                    waypoints[i].position, waypoints[i].attitude, goal.position, goal.attitude
                )
            ),
        )
        order_idx: List[int] = []
        mask = full
        i: Optional[int] = last
        for _ in range(n):  # parent 鏈最長 n 步
            if i is None:
                break
            order_idx.append(i)
            prev = parent[(mask, i)]
            mask &= ~(1 << i)
            i = prev
        order = [waypoints[k].id for k in reversed(order_idx)]

    legs = []
    pos, att = start_pos, start_att
    by_id = {wp.id: wp for wp in waypoints}
    for cp_id in order + [goal.id]:
        cp = goal if cp_id == goal.id else by_id[cp_id]
        legs.append(Leg(cp_id, cost_fn(pos, att, cp.position, cp.attitude)))
        pos, att = cp.position, cp.attitude
    return Route(order + [goal.id], legs)
