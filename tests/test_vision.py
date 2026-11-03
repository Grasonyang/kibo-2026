"""用合成影像測相機模組：把一張 marker 貼到已知位姿的畫面上，看算回來的位置對不對。"""

import math

import pytest

from kibo.vision import body_correction, camera_to_body, expected_marker_in_body

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

FX = 800.0
K = [FX, 0.0, 320.0, 0.0, FX, 240.0, 0.0, 0.0, 1.0]
NO_DISTORTION = [0.0, 0.0, 0.0, 0.0, 0.0]
SIDE = 0.02


def render_marker(marker_id, position_camera, size=(640, 480)):
    """把 marker 投影到相機畫面：先畫一張正面的 marker（含白邊），再用 homography 貼上去。"""
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    if hasattr(aruco, "generateImageMarker"):
        tile = aruco.generateImageMarker(dictionary, marker_id, 200)
    else:
        tile = aruco.drawMarker(dictionary, marker_id, 200)
    tile = cv2.copyMakeBorder(tile, 50, 50, 50, 50, cv2.BORDER_CONSTANT, value=255)

    half = SIDE / 2.0
    border = half * 1.5  # 白邊也要投影，比例與 tile 的 50/200 一致
    corners_3d = np.array(
        [[-border, border, 0], [border, border, 0], [border, -border, 0], [-border, -border, 0]],
        dtype=np.float64,
    )
    rvec = np.array(
        [math.pi, 0.0, 0.0]
    )  # marker 正對相機：marker 的 Z 朝相機、Y 朝上（繞 X 轉 180°）
    tvec = np.array(position_camera, dtype=np.float64)
    projected, _ = cv2.projectPoints(
        corners_3d, rvec, tvec, np.array(K).reshape(3, 3), np.array(NO_DISTORTION)
    )
    src = np.array([[0, 0], [300, 0], [300, 300], [0, 300]], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(src, projected.reshape(4, 2).astype(np.float32))
    canvas = np.full((size[1], size[0]), 255, dtype=np.uint8)
    warped = cv2.warpPerspective(tile, homography, size, borderValue=255)
    return np.minimum(canvas, warped)


def test_marker_position_is_recovered_from_a_synthetic_image():
    from kibo.vision import observe_markers

    truth = (0.03, -0.02, 0.45)  # 相機座標系：右 3 cm、上 2 cm、前 45 cm
    image = render_marker(7, truth)
    seen = observe_markers(image, K, NO_DISTORTION, SIDE)
    assert list(seen) == [7]
    # 35 px 的 marker 角點只有像素級精度，深度約差 1.5%；1 cm 的容差對「修正幾公分」夠用。
    assert seen[7].position_camera == pytest.approx(truth, abs=0.01)


def test_camera_axes_map_to_body_axes_with_mount_offset():
    # 相機前方 0.5 m、右 0.1 m、下 0.2 m → 機體前方 0.64 m（含 0.14 安裝位移）、右即 -Y、下即 -Z
    assert camera_to_body((0.1, 0.2, 0.5)) == pytest.approx((0.64, -0.1, -0.2))


def test_expected_marker_position_uses_body_frame():
    yaw_90 = (0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5))  # 機頭朝世界 +Y
    marker = (1.0, 2.0, 0.0)
    body = (1.0, 1.0, 0.0)
    # marker 在機體正前方 1 m
    assert expected_marker_in_body(body, yaw_90, marker) == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_correction_moves_toward_where_the_marker_should_be():
    # marker 預期在前方 0.5 m，實際看到在 0.6 m：我們太遠，要往前 0.1 m
    assert body_correction((0.6, 0.0, 0.0), (0.5, 0.0, 0.0)) == pytest.approx((0.1, 0.0, 0.0))
