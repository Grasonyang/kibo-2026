import math

from kibo.field import MARKERS, START_POSE


def test_markers_are_ids_1_to_12():
    assert sorted(MARKERS) == list(range(1, 13))


def test_marker_targets_are_unique():
    targets = [m.target for m in MARKERS.values()]
    assert len(set(targets)) == len(targets)


def test_quaternions_are_unit_length():
    poses = [m.pose for m in MARKERS.values()] + [START_POSE]
    for pose in poses:
        norm = math.sqrt(sum(c * c for c in pose.orientation))
        assert abs(norm - 1.0) < 1e-6, pose


def test_marker_normals_point_into_the_cabin():
    # 每個 marker 沿法線走 0.5 m（CheckPoint 的距離）都要落在安全區的 x、y 範圍內。
    from kibo.field import SAFE_AREA_MAX, SAFE_AREA_MIN
    from kibo.geometry import add, rotate, scale

    for marker in MARKERS.values():
        normal = rotate(marker.pose.orientation, (0.0, 0.0, 1.0))
        point = add(marker.pose.position, scale(normal, 0.5))
        for axis in (0, 1):
            assert SAFE_AREA_MIN[axis] <= point[axis] <= SAFE_AREA_MAX[axis], marker
