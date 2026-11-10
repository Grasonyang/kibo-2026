"""路線規劃：決定拜訪 CheckPoint 的順序。

問題是「從起點出發，經過所有中途點各一次，最後停在 Goal，總成本最小」，
這是有固定終點的旅行推銷員問題。點數最多 12（規則書 2.2.2），用 Held-Karp
動態規劃（狀態 = 已拜訪集合 × 目前所在點，2^11 × 11）在零點幾秒內就能算出最佳解。
中途點超過 11 個是規則外的情況，為了不炸掉改用最近鄰當退路。

成本是秒數，由 `kibo.motion` 的移動時間模型算：先平移再轉向、短程看加速度、
加速度看機體方向。同一段位移從不同的點出發成本不同，所以成本矩陣不對稱，
Held-Karp 照樣能解。
"""

from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from kibo.checkpoints import Checkpoint
from kibo.geometry import Quat, Vec3
from kibo.motion import leg_seconds


class Leg(NamedTuple):
    to_id: int
    seconds: float


class Route(NamedTuple):
    order: List[int]  # CheckPoint id 的拜訪順序，最後一個是 Goal
    legs: List[Leg]

    @property
    def seconds(self) -> float:
        return sum(leg.seconds for leg in self.legs)


CostFn = Callable[[Vec3, Quat, Vec3, Quat], float]

# 規則書最多 12 個 CheckPoint，其中一個是 Goal；再多 Held-Karp 的狀態數會爆。
MAX_WAYPOINTS = 11


def _nearest_neighbour(
    start_pos: Vec3, start_att: Quat, waypoints: List[Checkpoint], cost_fn: CostFn
) -> List[int]:
    """點太多無法精確解時的退路：每次去最近的一點。"""
    remaining = list(waypoints)
    order: List[int] = []
    pos, att = start_pos, start_att
    for _ in range(len(waypoints)):
        nearest = min(remaining, key=lambda cp: cost_fn(pos, att, cp.position, cp.attitude))
        order.append(nearest.id)
        remaining.remove(nearest)
        pos, att = nearest.position, nearest.attitude
    return order


class _Table(NamedTuple):
    """Held-Karp 的整張表：每個「拜訪了哪些點、最後停在哪」的最小成本。"""

    best: Dict[Tuple[int, int], float]
    parent: Dict[Tuple[int, int], Optional[int]]
    to_goal: List[float]
    direct: float  # 起點直接到 Goal


def _table(
    start_pos: Vec3, start_att: Quat, waypoints: List[Checkpoint], goal: Checkpoint, cost_fn: CostFn
) -> _Table:
    """成本先算成矩陣，DP 裡只查表，n=11 時少掉約 5 萬次幾何運算。"""
    n = len(waypoints)
    from_start = [cost_fn(start_pos, start_att, wp.position, wp.attitude) for wp in waypoints]
    to_goal = [cost_fn(wp.position, wp.attitude, goal.position, goal.attitude) for wp in waypoints]
    between = [
        [
            0.0 if i == j else cost_fn(a.position, a.attitude, b.position, b.attitude)
            for j, b in enumerate(waypoints)
        ]
        for i, a in enumerate(waypoints)
    ]

    # best[(mask, i)] = 從起點出發、拜訪 mask 裡的點、最後停在 waypoints[i] 的最小成本
    best: Dict[Tuple[int, int], float] = {}
    parent: Dict[Tuple[int, int], Optional[int]] = {}
    for i in range(n):
        best[(1 << i, i)] = from_start[i]
        parent[(1 << i, i)] = None
    for mask in range(1, 1 << n):
        for i in range(n):
            if (mask, i) not in best:
                continue
            base = best[(mask, i)]
            row = between[i]
            for j in range(n):
                if mask & (1 << j):
                    continue
                key = (mask | (1 << j), j)
                candidate = base + row[j]
                if candidate < best.get(key, float("inf")):
                    best[key] = candidate
                    parent[key] = i
    direct = cost_fn(start_pos, start_att, goal.position, goal.attitude)
    return _Table(best, parent, to_goal, direct)


def _unwind(table: _Table, waypoints: List[Checkpoint], mask: int, last: int) -> List[int]:
    order_idx: List[int] = []
    i: Optional[int] = last
    for _ in range(len(waypoints)):  # parent 鏈最長 n 步
        if i is None:
            break
        order_idx.append(i)
        prev = table.parent[(mask, i)]
        mask &= ~(1 << i)
        i = prev
    return [waypoints[k].id for k in reversed(order_idx)]


def _held_karp(
    start_pos: Vec3, start_att: Quat, waypoints: List[Checkpoint], goal: Checkpoint, cost_fn: CostFn
) -> List[int]:
    """精確解：拜訪全部中途點、停在 Goal 的最省順序。"""
    n = len(waypoints)
    table = _table(start_pos, start_att, waypoints, goal, cost_fn)
    full = (1 << n) - 1
    last = min(range(n), key=lambda i: table.best[(full, i)] + table.to_goal[i])
    return _unwind(table, waypoints, full, last)


class _Pick(NamedTuple):
    """目前最好的一組：去幾個中途點、總共幾秒、哪幾個（位元遮罩）、最後停在哪一個。

    `last` 是 -1 代表只去 Goal。"""

    points: int
    seconds: float
    mask: int
    last: int


def _best_subset(
    start_pos: Vec3,
    start_att: Quat,
    waypoints: List[Checkpoint],
    goal: Checkpoint,
    cost_fn: CostFn,
    limit_sec: float,
    per_stop_sec: float,
) -> List[int]:
    """在 limit_sec 內（每停一點另加 per_stop_sec，Goal 也算一停）能拜訪最多點的順序；
    一樣多就選最快的。連 Goal 都來不及時回空清單（只去 Goal）。

    Held-Karp 的表本來就有每個子集合的最小成本，所以挑子集合不用多算，只是多看一遍。
    """
    n = len(waypoints)
    table = _table(start_pos, start_att, waypoints, goal, cost_fn)
    chosen = _Pick(points=0, seconds=table.direct + per_stop_sec, mask=0, last=-1)
    for (mask, i), seconds in table.best.items():
        count = bin(mask).count("1")
        total = seconds + table.to_goal[i] + per_stop_sec * (count + 1)
        if total > limit_sec:
            continue
        if count > chosen.points or (count == chosen.points and total < chosen.seconds):
            chosen = _Pick(count, total, mask, i)
    if chosen.last < 0 or n == 0:
        return []
    return _unwind(table, waypoints, chosen.mask, chosen.last)


def _route(
    start_pos: Vec3,
    start_att: Quat,
    waypoints: List[Checkpoint],
    goal: Checkpoint,
    order: List[int],
    cost_fn: CostFn,
) -> Route:
    legs = []
    pos, att = start_pos, start_att
    by_id = {wp.id: wp for wp in waypoints}
    for cp_id in order + [goal.id]:
        cp = goal if cp_id == goal.id else by_id[cp_id]
        legs.append(Leg(cp_id, cost_fn(pos, att, cp.position, cp.attitude)))
        pos, att = cp.position, cp.attitude
    return Route(order + [goal.id], legs)


def plan_most_points(
    start_pos: Vec3,
    start_att: Quat,
    waypoints: List[Checkpoint],
    goal: Checkpoint,
    limit_sec: float,
    per_stop_sec: float,
    cost: Optional[CostFn] = None,
) -> Route:
    """時間內能拜訪最多中途點、最後停在 Goal 的路線（精確解）。一定包含 Goal。

    中途點超過 MAX_WAYPOINTS 個（規則外）時不挑子集合，交給呼叫端處理。
    """
    cost_fn = cost or leg_seconds
    if not waypoints or len(waypoints) > MAX_WAYPOINTS:
        return plan_route(start_pos, start_att, waypoints, goal, cost_fn)
    order = _best_subset(start_pos, start_att, waypoints, goal, cost_fn, limit_sec, per_stop_sec)
    return _route(start_pos, start_att, waypoints, goal, order, cost_fn)


def plan_route(
    start_pos: Vec3,
    start_att: Quat,
    waypoints: List[Checkpoint],
    goal: Checkpoint,
    cost: Optional[CostFn] = None,
) -> Route:
    """回傳成本最小的順序。waypoints 可以是空的（只去 Goal）。

    超過 MAX_WAYPOINTS 個中途點時不會爆炸，改用最近鄰（規則上限是 12 個 CheckPoint，
    這條路只是保險）。
    """
    cost_fn = cost or leg_seconds
    if not waypoints:
        order: List[int] = []
    elif len(waypoints) > MAX_WAYPOINTS:
        order = _nearest_neighbour(start_pos, start_att, waypoints, cost_fn)
    else:
        order = _held_karp(start_pos, start_att, waypoints, goal, cost_fn)

    return _route(start_pos, start_att, waypoints, goal, order, cost_fn)
