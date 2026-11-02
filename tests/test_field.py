import math

from kibo.field import MARKERS, START_POSE


def test_markers_are_ids_1_to_12():
    assert sorted(MARKERS) == list(range(1, 13))


def test_marker_targets_are_unique():
    targets = [m.target for m in MARKERS.values()]
    assert len(set(targets)) == len(targets)


def test_quaternions_are_unit_length():
    # 規則書的值只給到三位小數（0.707），所以容許 1e-2。
    poses = [m.pose for m in MARKERS.values()] + [START_POSE]
    for pose in poses:
        norm = math.sqrt(sum(c * c for c in pose.orientation))
        assert abs(norm - 1.0) < 1e-2, pose
