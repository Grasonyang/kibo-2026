"""相機看 AR marker：從影像算出 marker 相對機體的位置（第二版的「到點後微調」用）。

為什麼：導航給的位置可能漂移，但伺服器判定是以 marker 為基準的。相機直接看 marker
得到的相對位置最接近伺服器用的基準，拿它和「目標上應該看到的位置」相減，就是該修正的量。

執行環境是 OpenCV 3.3.1（手冊 5.13），本機開發是 5.x，兩邊的 ArUco API 不同：
- 3.x：`Dictionary_get`、`DetectorParameters_create`、`detectMarkers`。
- 4.7+：`getPredefinedDictionary`、`DetectorParameters()`、`ArucoDetector`。
這裡兩種都支援。位姿不用 `estimatePoseSingleMarkers`（新版已移除），改用 `solvePnP`，
3.3.1 與 5.x 都有。cv2 與 numpy 只在呼叫時才 import，沒裝也不影響其他模組。

座標：OpenCV 相機座標系是 X 右、Y 下、Z 前；機體座標系是 X 前、Y 左、Z 上；
相機裝在機體前方 0.14 m（手冊 5.13.2）。
"""

from typing import Dict, NamedTuple, Optional, Sequence

from kibo.geometry import Quat, Vec3, add, quat_conj, rotate, sub
from kibo.judge import CAMERA_OFFSET

MARKER_SIDE_M = 0.02  # 手冊 5.13.1：2 cm
DICTIONARY_NAME = "DICT_4X4_50"  # 手冊只說 4x4，ID 1 到 12；50 是最小的 4x4 字典


class MarkerObservation(NamedTuple):
    marker_id: int
    position_camera: Vec3  # marker 中心在相機座標系（公尺）
    position_body: Vec3  # 同一點換到機體座標系


def _aruco():
    import cv2  # noqa: PLC0415 - 延後 import，沒有 OpenCV 的環境也能用其他模組

    return cv2, cv2.aruco


def _detect(gray, dictionary_name: str):
    """回傳 {marker_id: 4x2 角點}。角點順序是左上、右上、右下、左下（ArUco 的慣例）。"""
    cv2, aruco = _aruco()
    dictionary_id = getattr(aruco, dictionary_name)
    if hasattr(aruco, "ArucoDetector"):  # OpenCV 4.7 以後
        detector = aruco.ArucoDetector(
            aruco.getPredefinedDictionary(dictionary_id), aruco.DetectorParameters()
        )
        corners, ids, _ = detector.detectMarkers(gray)
    else:  # OpenCV 3.x
        corners, ids, _ = aruco.detectMarkers(
            gray, aruco.Dictionary_get(dictionary_id), parameters=aruco.DetectorParameters_create()
        )
    found: Dict[int, object] = {}
    if ids is None:
        return found
    for marker_id, quad in zip(ids.flatten().tolist(), corners):
        found[int(marker_id)] = quad.reshape(4, 2)
    return found


def _solve_pose(corners, camera_matrix, distortion, side_m: float) -> Optional[Vec3]:
    """marker 中心在相機座標系的位置；解不出來回 None。"""
    cv2, _ = _aruco()
    import numpy as np  # noqa: PLC0415

    half = side_m / 2.0
    object_points = np.array(
        [[-half, half, 0.0], [half, half, 0.0], [half, -half, 0.0], [-half, -half, 0.0]],
        dtype=np.float64,
    )
    flags = getattr(cv2, "SOLVEPNP_IPPE_SQUARE", cv2.SOLVEPNP_ITERATIVE)
    ok, _rvec, tvec = cv2.solvePnP(
        object_points,
        np.asarray(corners, dtype=np.float64),
        np.asarray(camera_matrix, dtype=np.float64).reshape(3, 3),
        np.asarray(distortion, dtype=np.float64) if distortion is not None else None,
        flags=flags,
    )
    if not ok:
        return None
    t = tvec.flatten()
    return (float(t[0]), float(t[1]), float(t[2]))


def camera_to_body(p_camera: Vec3, camera_offset: Vec3 = CAMERA_OFFSET) -> Vec3:
    """相機座標系（X 右、Y 下、Z 前）換到機體座標系（X 前、Y 左、Z 上），再加相機安裝位置。"""
    return add((p_camera[2], -p_camera[0], -p_camera[1]), camera_offset)


def observe_markers(
    gray,
    camera_matrix: Sequence[float],
    distortion: Optional[Sequence[float]],
    side_m: float = MARKER_SIDE_M,
    dictionary_name: str = DICTIONARY_NAME,
) -> Dict[int, MarkerObservation]:
    """灰階影像裡每個看得到的 marker，以及它相對機體的位置。

    camera_matrix 是 CameraInfo.K（9 個數），distortion 是 CameraInfo.D。
    """
    observations: Dict[int, MarkerObservation] = {}
    for marker_id, corners in _detect(gray, dictionary_name).items():
        p_cam = _solve_pose(corners, camera_matrix, distortion, side_m)
        if p_cam is None:
            continue
        observations[marker_id] = MarkerObservation(marker_id, p_cam, camera_to_body(p_cam))
    return observations


def expected_marker_in_body(
    body_position: Vec3, body_orientation: Quat, marker_position: Vec3
) -> Vec3:
    """站在某個姿態時，marker 應該出現在機體座標系的哪裡。"""
    return rotate(quat_conj(body_orientation), sub(marker_position, body_position))


def body_correction(observed_body: Vec3, expected_body: Vec3) -> Vec3:
    """機體該往哪裡平移（機體座標系），才會讓 marker 出現在該出現的地方。

    marker 看起來比預期更靠前，代表我們太遠，要往前（+X）移；所以修正 = 觀測 - 預期。
    """
    return sub(observed_body, expected_body)
