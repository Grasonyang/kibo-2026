import json

import pytest

from conftest import GOAL_12, MANUAL_CHECKPOINT_1, checkpoints_message
from kibo.checkpoints import Band, parse_checkpoints


def test_parses_manual_example_fields(three_point_message):
    cp = parse_checkpoints(three_point_message).by_id(1)
    assert cp.position == pytest.approx(
        (1.4421152111823452, -0.5013235815457989, 0.6649623093633403)
    )
    assert cp.marker_position == pytest.approx((1.451, -1.001, 0.6806))
    assert cp.attitude[3] == pytest.approx(-0.10270913665940805)


def test_bands_are_ordered_strictest_first_even_if_server_shuffles():
    shuffled = json.loads(json.dumps(MANUAL_CHECKPOINT_1))
    shuffled["score_bands"] = list(reversed(shuffled["score_bands"]))
    cp = parse_checkpoints(checkpoints_message([shuffled, GOAL_12])).by_id(1)
    assert cp.position_bands == [Band(0.1, 3), Band(0.2, 2), Band(0.3, 1)]


def test_goal_and_waypoints_are_separated(three_point_message):
    cps = parse_checkpoints(three_point_message)
    assert cps.goal.id == 12
    assert [cp.id for cp in cps.waypoints] == [1, 6]


def test_goal_not_in_list_degrades_to_last_checkpoint_with_warning():
    cps = parse_checkpoints(checkpoints_message([MANUAL_CHECKPOINT_1, GOAL_12], goal_id=99))
    assert cps.goal_id == 12
    assert any("goalpoint_id=99" in w for w in cps.warnings)


def test_mismatched_count_is_only_a_warning():
    message = json.loads(checkpoints_message([MANUAL_CHECKPOINT_1, GOAL_12]))
    message["checkpoint_count"] = 5
    cps = parse_checkpoints(json.dumps(message))
    assert len(cps.checkpoints) == 2
    assert any("checkpoint_count=5" in w for w in cps.warnings)


def test_one_broken_checkpoint_is_skipped_not_fatal():
    broken = json.loads(json.dumps(MANUAL_CHECKPOINT_1))
    broken["position"] = [1.0, 2.0]
    cps = parse_checkpoints(checkpoints_message([broken, GOAL_12]))
    assert [cp.id for cp in cps.checkpoints] == [12]
    assert any("skipped" in w for w in cps.warnings)


def test_missing_attitude_gets_a_look_at_attitude():
    from kibo.geometry import Pose
    from kibo.judge import judge

    bare = json.loads(json.dumps(MANUAL_CHECKPOINT_1))
    del bare["attitude"]
    cp = parse_checkpoints(checkpoints_message([bare, GOAL_12])).by_id(1)
    assert judge(Pose(cp.position, cp.attitude), cp).centering_deg < 0.01


def test_hopeless_json_still_raises():
    with pytest.raises(ValueError):
        parse_checkpoints('{"checkpoint_count": 1, "checkpoints": [5], "goalpoint_id": 5}')
    with pytest.raises(ValueError):
        parse_checkpoints("not json at all")
    with pytest.raises(ValueError):
        parse_checkpoints('{"checkpoints": [], "goalpoint_id": 1}')


def test_missing_goalpoint_field_and_unreadable_count_only_warn():
    message = json.loads(checkpoints_message([MANUAL_CHECKPOINT_1, GOAL_12]))
    del message["goalpoint_id"]
    message["checkpoint_count"] = "N/A"
    cps = parse_checkpoints(json.dumps(message))
    assert cps.goal_id == 12
    assert any("goalpoint_id missing" in w for w in cps.warnings)
    assert any("checkpoint_count unreadable" in w for w in cps.warnings)
