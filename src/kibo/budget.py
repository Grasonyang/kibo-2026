"""時間預算：剩下的點來不來得及？來不及就放棄哪些？

為什麼需要：Goal 分數與剩餘時間倍率是乘在**全部**分數上的。寧可少去一個點，
也不能讓 Goal 來不及。這裡的規則：

1. 先規劃全部剩餘點的路線，估計總秒數（每段移動 + 每點穩定時間）。
2. 加上安全餘裕後若超過剩餘時間，就刪掉「每分每秒最不划算」的點，重算。
3. Goal 永遠不刪。
"""

from typing import List, NamedTuple, Optional

from kibo.checkpoints import Checkpoint
from kibo.geometry import Quat, Vec3
from kibo.planner import DEFAULT_SPEEDS, Route, Speeds, leg_seconds, plan_route
from kibo.scoring import DEFAULT_SCORING, Scoring


class BudgetConfig(NamedTuple):
    settle_sec: float = 8.0  # 每個點到位後穩定並等伺服器判定的時間
    margin_sec: float = 25.0  # 留給 Goal 與完成回報的保險
    speeds: Speeds = DEFAULT_SPEEDS
    scoring: Scoring = DEFAULT_SCORING


DEFAULT_BUDGET = BudgetConfig()


class Plan(NamedTuple):
    route: Route
    dropped: List[int]  # 這次決定放棄的 CheckPoint id
    estimated_sec: float


def estimated_seconds(route: Route, settle_sec: float) -> float:
    """整條路線含每一點的穩定時間（Goal 也要穩定才能判定）。"""
    return route.seconds + settle_sec * len(route.order)


def _marginal_seconds(
    route: Route, by_id, start_pos: Vec3, start_att: Quat, speeds: Speeds, settle_sec: float
):
    """沿目前路線，每個中途點「拿掉它能省多少秒」。"""
    pos, att = start_pos, start_att
    stops = [by_id[cp_id] for cp_id in route.order]
    savings = {}
    for i, cp in enumerate(stops[:-1]):  # 最後一個是 Goal，不算
        before = (pos, att) if i == 0 else (stops[i - 1].position, stops[i - 1].attitude)
        after = stops[i + 1]
        with_cp = leg_seconds(before[0], before[1], cp.position, cp.attitude, speeds) + leg_seconds(
            cp.position, cp.attitude, after.position, after.attitude, speeds
        )
        without_cp = leg_seconds(before[0], before[1], after.position, after.attitude, speeds)
        savings[cp.id] = with_cp - without_cp + settle_sec
    return savings


def plan_within_budget(
    start_pos: Vec3,
    start_att: Quat,
    waypoints: List[Checkpoint],
    goal: Checkpoint,
    remaining_sec: float,
    config: BudgetConfig = DEFAULT_BUDGET,
    target_level: int = 3,
) -> Plan:
    """回傳在剩餘時間內做得完的計畫。可能放棄一些點，但一定包含 Goal。"""
    remaining = list(waypoints)
    dropped: List[int] = []
    by_id = {cp.id: cp for cp in waypoints}
    by_id[goal.id] = goal
    points = config.scoring.points_for_level(target_level)

    def cost(a_pos, a_att, b_pos, b_att):
        return leg_seconds(a_pos, a_att, b_pos, b_att, config.speeds)

    route = plan_route(start_pos, start_att, remaining, goal, cost)
    for _ in range(len(waypoints) + 1):  # 每輪最多刪一點，所以迴圈有上限
        est = estimated_seconds(route, config.settle_sec)
        if est + config.margin_sec <= remaining_sec or not remaining:
            return Plan(route, dropped, est)
        savings = _marginal_seconds(
            route, by_id, start_pos, start_att, config.speeds, config.settle_sec
        )
        # 每一分要花最多秒的那個點最不划算；分數都一樣時就是省最多秒的。
        victim: Optional[int] = max(savings, key=lambda cp_id: savings[cp_id] / max(points, 1e-9))
        if victim is None:
            break
        dropped.append(victim)
        remaining = [cp for cp in remaining if cp.id != victim]
        route = plan_route(start_pos, start_att, remaining, goal, cost)
    return Plan(route, dropped, estimated_seconds(route, config.settle_sec))
