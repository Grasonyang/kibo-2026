"""時間預算：剩下的點來不來得及？來不及就放棄哪些？

為什麼需要：完成回報與剩餘時間倍率是乘在**全部**分數上的。寧可少去幾個點，
也不能讓 Goal 來不及。這裡的規則：

1. 先規劃全部剩餘點的路線，估計總秒數（每段移動 + 每點穩定時間）。
2. 加上安全餘裕後若超過剩餘時間，就改成「時間內能去最多點」的那一組（精確解）；
   一樣多選最快的。每個點的分數一樣（都以 Lv3 為目標），所以點數就是唯一的排序依據。
3. Goal 永遠不刪。

還不知道的（要問主辦）：漏了點之後 Goal 分數還給不給（規則書附錄 #20 的字面是
「passes all CheckPoints ... and reaches the GoalPoint」），以及時間倍率的公式。
倍率若很陡，「全部都來得及也故意少去一個遠的點」可能分數更高；公式公布前不這樣做。
"""

from typing import Dict, List, NamedTuple

from kibo.checkpoints import Checkpoint
from kibo.geometry import Quat, Vec3
from kibo.motion import DEFAULT_SPEEDS, Speeds, leg_seconds
from kibo.planner import MAX_WAYPOINTS, Route, plan_most_points, plan_route


class BudgetConfig(NamedTuple):
    settle_sec: float = 1.0  # 每個點到位後自判穩定加送通知；尾段已穩定時約 0.1 秒，否則約 1 秒
    margin_sec: float = 15.0  # 保險：模型每段腿約 ±1.6 秒，12 段累積約 ±6 秒，再留完成回報的時間
    speeds: Speeds = DEFAULT_SPEEDS
    allow_drop: bool = True  # False 只用來做對照（tune 的「不刪點」變體），比賽不要關


DEFAULT_BUDGET = BudgetConfig()


class Plan(NamedTuple):
    route: Route
    dropped: List[int]  # 這次決定放棄的 CheckPoint id
    estimated_sec: float


def estimated_seconds(route: Route, settle_sec: float) -> float:
    """整條路線含每一點的穩定時間（Goal 也要穩定才能判定）。"""
    return route.seconds + settle_sec * len(route.order)


def _savings(
    route: Route,
    by_id: Dict[int, Checkpoint],
    start_pos: Vec3,
    start_att: Quat,
    speeds: Speeds,
    settle_sec: float,
) -> Dict[int, float]:
    """沿目前路線，每個中途點「拿掉它能省多少秒」。"""
    stops = [by_id[cp_id] for cp_id in route.order]
    savings: Dict[int, float] = {}
    for i, cp in enumerate(stops[:-1]):  # 最後一個是 Goal，不算
        before = (
            (start_pos, start_att) if i == 0 else (stops[i - 1].position, stops[i - 1].attitude)
        )
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
) -> Plan:
    """回傳在剩餘時間內做得完的計畫。可能放棄一些點，但一定包含 Goal。"""
    remaining = list(waypoints)
    dropped: List[int] = []
    by_id = {cp.id: cp for cp in waypoints}
    by_id[goal.id] = goal

    def cost(a_pos, a_att, b_pos, b_att):
        return leg_seconds(a_pos, a_att, b_pos, b_att, config.speeds)

    route = plan_route(start_pos, start_att, remaining, goal, cost)
    est = estimated_seconds(route, config.settle_sec)
    if est + config.margin_sec <= remaining_sec or not remaining or not config.allow_drop:
        return Plan(route, dropped, est)

    if len(remaining) <= MAX_WAYPOINTS:
        # 來不及：精確地挑「時間內能去最多點」的那一組。逐一刪點會被擠在一起的遠點騙到
        # （它們互相掩護，各自看起來只省幾秒）。
        route = plan_most_points(
            start_pos,
            start_att,
            remaining,
            goal,
            remaining_sec - config.margin_sec,
            config.settle_sec,
            cost,
        )
        kept = set(route.order)
        dropped = [cp.id for cp in waypoints if cp.id not in kept]
        return Plan(route, dropped, estimated_seconds(route, config.settle_sec))

    for _ in range(len(waypoints)):  # 規則外的保險（點太多）：每輪刪一點，最多 len(waypoints) 輪
        est = estimated_seconds(route, config.settle_sec)
        if est + config.margin_sec <= remaining_sec or not remaining:
            break
        savings = _savings(route, by_id, start_pos, start_att, config.speeds, config.settle_sec)
        victim = max(savings, key=lambda cp_id: savings[cp_id])
        dropped.append(victim)
        remaining = [cp for cp in remaining if cp.id != victim]
        route = plan_route(start_pos, start_att, remaining, goal, cost)
    return Plan(route, dropped, estimated_seconds(route, config.settle_sec))
