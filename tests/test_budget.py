from kibo.budget import BudgetConfig, plan_within_budget
from kibo.checkpoints import Checkpoint
from kibo.geometry import IDENTITY_QUAT
from kibo.planner import Speeds

ONE_METRE_PER_SEC = Speeds(linear_mps=1.0, angular_dps=1000.0)
CONFIG = BudgetConfig(settle_sec=5.0, margin_sec=10.0, speeds=ONE_METRE_PER_SEC)


def cp(cp_id, position):
    return Checkpoint(cp_id, position, position, IDENTITY_QUAT, IDENTITY_QUAT, [], [], [])


START = (0.0, 0.0, 0.0)
GOAL = cp(9, (0.0, 0.0, 0.0))


def test_everything_fits_when_time_is_plentiful():
    waypoints = [cp(1, (1.0, 0.0, 0.0)), cp(2, (2.0, 0.0, 0.0))]
    far_goal = cp(9, (3.0, 0.0, 0.0))
    plan = plan_within_budget(
        START, IDENTITY_QUAT, waypoints, far_goal, remaining_sec=300.0, config=CONFIG
    )
    assert plan.route.order == [1, 2, 9]
    assert plan.dropped == []
    # 1 + 1 + 1 公尺 = 3 秒，加三個點各 5 秒穩定 = 18 秒
    assert plan.estimated_sec == 18.0


def test_far_detour_is_dropped_first_when_short_on_time():
    # 點 1 在順路上，點 2 要繞 10 公尺；時間只夠其中一個。
    waypoints = [cp(1, (1.0, 0.0, 0.0)), cp(2, (0.0, 10.0, 0.0))]
    plan = plan_within_budget(
        START, IDENTITY_QUAT, waypoints, GOAL, remaining_sec=30.0, config=CONFIG
    )
    assert plan.dropped == [2]
    assert plan.route.order == [1, 9]


def test_goal_is_never_dropped_even_when_nothing_fits():
    waypoints = [cp(1, (50.0, 0.0, 0.0))]
    plan = plan_within_budget(
        START, IDENTITY_QUAT, waypoints, GOAL, remaining_sec=12.0, config=CONFIG
    )
    assert plan.route.order == [9]
    assert plan.dropped == [1]
