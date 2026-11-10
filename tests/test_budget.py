import pytest

from kibo.budget import BudgetConfig, plan_within_budget
from kibo.checkpoints import Checkpoint
from kibo.geometry import IDENTITY_QUAT

# 預設的移動時間模型：沿機體 X 軸 1 m 是 2√(1/0.022511) = 13.33 秒；
# 沿 Y 軸 10 m 是 10/0.2 + 0.2/0.012382 = 66.15 秒。
CONFIG = BudgetConfig(settle_sec=5.0, margin_sec=10.0)


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
    # 三段各 1 公尺 = 3 x 13.33 秒，加三個點各 5 秒穩定
    assert plan.estimated_sec == pytest.approx(3 * 13.33 + 15.0, abs=0.05)


def test_far_detour_is_dropped_first_when_short_on_time():
    # 點 1 在順路上（來回 26.7 秒），點 2 要繞 10 公尺（單程 66 秒）；時間只夠其中一個。
    waypoints = [cp(1, (1.0, 0.0, 0.0)), cp(2, (0.0, 10.0, 0.0))]
    plan = plan_within_budget(
        START, IDENTITY_QUAT, waypoints, GOAL, remaining_sec=60.0, config=CONFIG
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


def test_a_far_cluster_is_given_up_instead_of_the_near_points():
    # 遠處有兩個點擠在一起（6 m 外，來回約 84 秒），近處有兩個點（合計約 32 秒）。
    # 逐一刪「省最多秒」的點會先刪近的（遠的那兩個互相掩護，各自只省 6 秒），最後一個都不剩；
    # 正確答案是整組放棄遠的，留下近的兩個。
    waypoints = [
        cp(1, (-0.5, 0.0, 0.0)),
        cp(2, (-1.0, 0.0, 0.0)),
        cp(3, (6.0, 0.0, 0.0)),
        cp(4, (6.2, 0.0, 0.0)),
    ]
    plan = plan_within_budget(
        START, IDENTITY_QUAT, waypoints, GOAL, remaining_sec=60.0, config=CONFIG
    )
    assert plan.route.order == [1, 2, 9]
    assert sorted(plan.dropped) == [3, 4]
    assert plan.estimated_sec + CONFIG.margin_sec <= 60.0


def test_among_equally_many_points_the_quickest_set_is_kept():
    # 只夠去一個：選來回最快的那個（0.5 m），不是 1 m 的。
    waypoints = [cp(1, (1.0, 0.0, 0.0)), cp(2, (-0.5, 0.0, 0.0))]
    plan = plan_within_budget(
        START, IDENTITY_QUAT, waypoints, GOAL, remaining_sec=40.0, config=CONFIG
    )
    assert plan.route.order == [2, 9]
    assert plan.dropped == [1]
