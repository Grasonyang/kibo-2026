import time

from kibo.checkpoints import Checkpoint
from kibo.geometry import IDENTITY_QUAT
from kibo.planner import Speeds, leg_seconds, plan_route


def cp(cp_id, position, attitude=IDENTITY_QUAT):
    return Checkpoint(cp_id, position, position, IDENTITY_QUAT, attitude, [], [], [])


def test_route_visits_collinear_points_in_order_and_ends_at_goal():
    # 三個點排成一直線，終點在旁邊：正著走 3 + sqrt(10) ≈ 6.16，反著走 5 + sqrt(2) ≈ 6.41。
    waypoints = [cp(3, (3.0, 0.0, 0.0)), cp(1, (1.0, 0.0, 0.0)), cp(2, (2.0, 0.0, 0.0))]
    goal = cp(9, (0.0, 1.0, 0.0))
    route = plan_route((0.0, 0.0, 0.0), IDENTITY_QUAT, waypoints, goal)
    assert route.order == [1, 2, 3, 9]


def test_route_with_no_waypoints_goes_straight_to_goal():
    goal = cp(9, (0.0, 1.0, 0.0))
    route = plan_route((0.0, 0.0, 0.0), IDENTITY_QUAT, [], goal)
    assert route.order == [9]
    assert len(route.legs) == 1


def test_leg_seconds_adds_travel_and_turn_time():
    yaw_90 = (0.0, 0.0, 0.7071068, 0.7071068)
    speeds = Speeds(linear_mps=0.5, angular_dps=30.0)
    # 1 公尺 / 0.5 m/s = 2 秒，90° / 30°/s = 3 秒
    assert (
        abs(leg_seconds((0.0, 0.0, 0.0), IDENTITY_QUAT, (1.0, 0.0, 0.0), yaw_90, speeds) - 5.0)
        < 1e-6
    )


def test_turning_cost_changes_the_order():
    # 兩個點等距，但其中一個要大轉彎；先去不用轉的那個。
    yaw_180 = (0.0, 0.0, 1.0, 0.0)
    waypoints = [cp(1, (0.0, 1.0, 0.0), yaw_180), cp(2, (0.0, -1.0, 0.0))]
    goal = cp(9, (0.0, 0.0, 0.0), yaw_180)
    route = plan_route((0.0, 0.0, 0.0), IDENTITY_QUAT, waypoints, goal)
    assert route.order == [2, 1, 9]


def test_twelve_waypoints_plan_in_under_a_second():
    waypoints = [cp(i, (float(i % 4), float(i // 4), float(i % 3))) for i in range(1, 12)]
    goal = cp(12, (0.0, 0.0, 0.0))
    started = time.perf_counter()
    route = plan_route((0.2, 0.0, 0.0), IDENTITY_QUAT, waypoints, goal)
    assert time.perf_counter() - started < 1.0
    assert sorted(route.order) == list(range(1, 13))
    assert route.order[-1] == 12
