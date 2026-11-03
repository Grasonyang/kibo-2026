#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ROS 接線層：把 Int-Ball2 的 topic、service、action 接到 kibo 的任務邏輯。

這個檔案要放進官方範本的 krpc_user/scripts/（見 ros/README.md）。它只做翻譯：
ROS 訊息 <-> kibo 的 Pose 與 MOVE_* 結果。決策全部在 kibo.mission。

保留了官方範本標 DO NOT REMOVE 的三件事：
- 訂閱 /ib2_user/start（任務起點）
- 提供 /ib2_user/stop（停止要求：先取消動作再回應）
- 設定 /ib2_user/ready = True

執行環境是 Python 3.6.9 / ROS Melodic。尚未在模擬器實測。
"""

import threading

import actionlib
import rospy
from actionlib_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from ib2_msgs.msg import (
    CtlCommandAction,
    CtlCommandGoal,
    CtlCommandResult,
    CtlStatus,
    CtlStatusType,
    Navigation,
)
from krpc_ib2_msgs.msg import CheckpointPassedAction, CheckpointPassedGoal
from krpc_ib2_msgs.srv import CheckPoints, MissionFinished, MissionStart
from platform_msgs.msg import UserLogic
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse
from sensor_msgs.msg import CameraInfo, Image

from kibo.judge import Pose
from kibo.mission import (
    DEFAULT_MISSION,
    MOVE_ABORTED,
    MOVE_INVALID,
    MOVE_SUCCESS,
    MOVE_TIMEOUT,
    Robot,
    run_mission,
)
from kibo.vision import observe_markers

SERVICE_TIMEOUT_SEC = 10.0  # 等服務出現，以及等它回應，各自的上限
ACTION_SERVER_TIMEOUT_SEC = 10.0
NOTIFY_TIMEOUT_SEC = 15.0
CANCEL_WAIT_SEC = 5.0
NAV_FRESH_SEC = 1.0  # 導航資料比這舊就當作沒有
IMAGE_FRESH_SEC = 1.0
POLL_SEC = 0.2

ACTION_DONE = "done"
ACTION_TIMEOUT = "timeout"
ACTION_STOPPED = "stopped"


class RosRobot(Robot):
    def __init__(self):
        self._nav = None  # 最新的 Navigation 訊息
        self._nav_lock = threading.Lock()
        self._stop = threading.Event()
        self._active_lock = threading.Lock()
        self._active_goals = []  # 正在執行的 action client，停止時要取消

        self._command = actionlib.SimpleActionClient("/ctl/command", CtlCommandAction)
        self._checkpoint = actionlib.SimpleActionClient(
            "/event/checkpoint_passed", CheckpointPassedAction
        )
        self._mission_start = rospy.ServiceProxy("/event/mission_start", MissionStart)
        self._mission_finished = rospy.ServiceProxy("/event/mission_finished", MissionFinished)
        self._checkpoints = rospy.ServiceProxy("/mission/get_checkpoints", CheckPoints)
        self._nav_sub = rospy.Subscriber("/sensor_fusion/navigation", Navigation, self._on_nav)
        self._ctl_type = None  # /ctl/status 最新的控制狀態，只拿來 log
        self._ctl_sub = rospy.Subscriber("/ctl/status", CtlStatus, self._on_ctl)
        # 相機（選用）：只在 settle 不穩定時用來修正幾公分
        self._image = None
        self._camera_info = None
        self._image_lock = threading.Lock()
        self._image_sub = rospy.Subscriber("/camera_main/image_raw", Image, self._on_image)
        self._info_sub = rospy.Subscriber("/camera_main/camera_info", CameraInfo, self._on_info)

    # ---- Robot 介面 ----
    def now(self):
        return rospy.get_time()

    def sleep(self, sec):
        rospy.sleep(sec)

    def log(self, message):
        rospy.loginfo(message)

    def stop_requested(self):
        return self._stop.is_set() or rospy.is_shutdown()

    def pose(self):
        with self._nav_lock:
            nav = self._nav
        if nav is None:
            return None
        age = (rospy.Time.now() - nav.pose.header.stamp).to_sec()
        if age > NAV_FRESH_SEC:
            return None
        p = nav.pose.pose.position
        q = nav.pose.pose.orientation
        return Pose((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), stamp=nav.pose.header.stamp.to_sec())

    def move_to(self, target, timeout_sec):
        if not self._command.wait_for_server(rospy.Duration(ACTION_SERVER_TIMEOUT_SEC)):
            rospy.logerr("/ctl/command server unavailable")
            return MOVE_ABORTED
        goal = CtlCommandGoal(
            target=self._pose_stamped(target),
            type=CtlStatusType(type=CtlStatusType.MOVE_TO_ABSOLUTE_TARGET),
        )
        status, result = self._run_action(self._command, goal, timeout_sec)
        rospy.loginfo(
            "move_to done: status=%s result=%s ctl_status=%s",
            status,
            getattr(result, "type", None),
            self._ctl_type,
        )
        if status == ACTION_TIMEOUT:
            return MOVE_TIMEOUT
        if status == ACTION_STOPPED or result is None:
            return MOVE_ABORTED  # 被停止、被拒絕，或 server 沒帶 result
        if result.type == CtlCommandResult.TERMINATE_SUCCESS:
            return MOVE_SUCCESS
        if result.type in (
            CtlCommandResult.TERMINATE_INVALID_NAV,
            CtlCommandResult.TERMINATE_INVALID_CMD,
        ):
            return MOVE_INVALID
        if result.type == CtlCommandResult.TERMINATE_TIME_OUT:
            return MOVE_TIMEOUT
        return MOVE_ABORTED

    def mission_start(self):
        res = self._call(self._mission_start, "/event/mission_start")
        return bool(res is not None and res.success)

    def mission_finish(self):
        res = self._call(self._mission_finished, "/event/mission_finished")
        return bool(res is not None and res.success)

    def get_checkpoints_message(self):
        res = self._call(self._checkpoints, "/mission/get_checkpoints")
        if res is None or not res.success:
            return None
        return res.message

    def notify_checkpoint(self, checkpoint_id):
        if not self._checkpoint.wait_for_server(rospy.Duration(ACTION_SERVER_TIMEOUT_SEC)):
            rospy.logerr("/event/checkpoint_passed server unavailable")
            return False
        goal = CheckpointPassedGoal(checkpoint_id=checkpoint_id)
        status, result = self._run_action(self._checkpoint, goal, NOTIFY_TIMEOUT_SEC)
        if status != ACTION_DONE or result is None:
            rospy.logwarn("checkpoint_passed #%d: %s", checkpoint_id, status)
            return False
        rospy.loginfo(
            "checkpoint_passed #%d: success=%s %s", checkpoint_id, result.success, result.message
        )
        return bool(result.success)

    def marker_in_body(self, marker_id):
        """最新影像裡若看得到該 marker，回它在機體座標系的位置；否則 None。"""
        with self._image_lock:
            image, info = self._image, self._camera_info
        if image is None or info is None:
            return None
        if (rospy.Time.now() - image.header.stamp).to_sec() > IMAGE_FRESH_SEC:
            return None
        gray = self._to_gray(image)
        if gray is None:
            return None
        try:
            seen = observe_markers(gray, list(info.K), list(info.D) if info.D else None)
        except Exception as exc:  # 影像處理失敗不能中斷任務
            rospy.logwarn("marker detection failed: %s", exc)
            return None
        observation = seen.get(marker_id)
        return observation.position_body if observation else None

    def move_relative(self, delta, timeout_sec):
        if not self._command.wait_for_server(rospy.Duration(ACTION_SERVER_TIMEOUT_SEC)):
            return MOVE_ABORTED
        target = PoseStamped()
        target.header.stamp = rospy.Time.now()
        target.header.frame_id = "body"
        target.pose.position.x, target.pose.position.y, target.pose.position.z = delta
        target.pose.orientation.w = 1.0
        goal = CtlCommandGoal(
            target=target, type=CtlStatusType(type=CtlStatusType.MOVE_TO_RELATIVE_TARGET)
        )
        status, result = self._run_action(self._command, goal, timeout_sec)
        if status == ACTION_TIMEOUT:
            return MOVE_TIMEOUT
        if status == ACTION_STOPPED or result is None:
            return MOVE_ABORTED
        return MOVE_SUCCESS if result.type == CtlCommandResult.TERMINATE_SUCCESS else MOVE_ABORTED

    # ---- 給節點用 ----
    def request_stop(self):
        """停止要求：取消所有執行中的 action，等它們結束。"""
        self._stop.set()
        with self._active_lock:
            clients = list(self._active_goals)
        for client in clients:
            try:
                client.cancel_goal()
                client.wait_for_result(rospy.Duration(CANCEL_WAIT_SEC))
            except Exception as exc:  # 停止流程不能因任何例外中斷
                rospy.logwarn("cancel failed: %s", exc)

    # ---- 內部 ----
    def _on_nav(self, msg):
        with self._nav_lock:
            self._nav = msg

    def _on_ctl(self, msg):
        self._ctl_type = msg.type.type if hasattr(msg.type, "type") else msg.type

    def _on_image(self, msg):
        with self._image_lock:
            self._image = msg

    def _on_info(self, msg):
        with self._image_lock:
            self._camera_info = msg

    @staticmethod
    def _to_gray(msg):
        """sensor_msgs/Image 轉灰階 numpy 陣列。不用 cv_bridge，少一個依賴。"""
        import cv2
        import numpy as np

        channels = {"mono8": 1, "bgr8": 3, "rgb8": 3, "bgra8": 4, "rgba8": 4}.get(msg.encoding)
        if channels is None:
            rospy.logwarn_throttle(10.0, "unsupported image encoding %s", msg.encoding)
            return None
        array = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step // 1)[
            :, : msg.width * channels
        ]
        array = array.reshape(msg.height, msg.width, channels) if channels > 1 else array
        if channels == 1:
            return array
        code = {
            "bgr8": cv2.COLOR_BGR2GRAY,
            "rgb8": cv2.COLOR_RGB2GRAY,
            "bgra8": cv2.COLOR_BGRA2GRAY,
        }
        return cv2.cvtColor(array, code.get(msg.encoding, cv2.COLOR_RGBA2GRAY))

    @staticmethod
    def _pose_stamped(pose):
        msg = PoseStamped()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = "iss_body"
        msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = pose.position
        (
            msg.pose.orientation.x,
            msg.pose.orientation.y,
            msg.pose.orientation.z,
            msg.pose.orientation.w,
        ) = pose.orientation
        return msg

    def _call(self, proxy, name):
        """呼叫服務，等服務出現與等它回應都有上限。

        ServiceProxy 本身沒有逾時，server 收了請求不回應會永遠阻塞，所以放到
        daemon thread 裡用 Event 等；逾時就回 None（那個 thread 會留在背景，
        但不會擋住任務）。
        """
        try:
            rospy.wait_for_service(name, timeout=SERVICE_TIMEOUT_SEC)
        except rospy.ROSException as exc:
            rospy.logerr("%s unavailable: %s", name, exc)
            return None

        box = {}
        done = threading.Event()

        def worker():
            try:
                box["result"] = proxy()
            except rospy.ServiceException as exc:
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=worker, name=name, daemon=True).start()
        # 用 rospy 的時間等，模擬時間與牆鐘不同步時逾時單位才一致；次數有上限。
        deadline = rospy.get_time() + SERVICE_TIMEOUT_SEC
        max_polls = int(SERVICE_TIMEOUT_SEC / 0.05) + 2
        for _ in range(max_polls):
            if done.is_set():
                break
            if rospy.get_time() > deadline:
                rospy.logerr("%s did not respond within %.0fs", name, SERVICE_TIMEOUT_SEC)
                return None
            rospy.sleep(0.05)
        if not done.is_set():
            return None
        if "error" in box:
            rospy.logerr("%s failed: %s", name, box["error"])
            return None
        return box.get("result")

    def _run_action(self, client, goal, timeout_sec):
        """送出 goal，輪詢到完成、逾時或停止；逾時與停止都會取消。

        回傳 (狀態, result)。狀態是 ACTION_DONE、ACTION_TIMEOUT 或 ACTION_STOPPED；
        goal 被拒絕時狀態是 ACTION_DONE 但 result 為 None。
        """
        client.send_goal(goal)
        with self._active_lock:
            self._active_goals.append(client)
        deadline = rospy.get_time() + timeout_sec
        max_polls = int(timeout_sec / POLL_SEC) + 2
        try:
            for _ in range(max_polls):
                if client.wait_for_result(rospy.Duration(POLL_SEC)):
                    if client.get_state() == GoalStatus.REJECTED:
                        return ACTION_DONE, None
                    return ACTION_DONE, client.get_result()
                if self.stop_requested():
                    break
                if rospy.get_time() > deadline:
                    client.cancel_goal()
                    client.wait_for_result(rospy.Duration(CANCEL_WAIT_SEC))
                    return ACTION_TIMEOUT, None
            client.cancel_goal()
            client.wait_for_result(rospy.Duration(CANCEL_WAIT_SEC))
            return ACTION_STOPPED, None
        finally:
            with self._active_lock:
                if client in self._active_goals:
                    self._active_goals.remove(client)


class UserNode(object):
    def __init__(self):
        self._robot = RosRobot()
        self._started = False
        self._start_lock = threading.Lock()
        # DO NOT REMOVE THESE THREE LINES（官方範本要求）
        self._start_sub = rospy.Subscriber("/ib2_user/start", UserLogic, self._on_start)
        self._stop_srv = rospy.Service("/ib2_user/stop", StopProcessingUserNode, self._on_stop)
        rospy.set_param("/ib2_user/ready", True)
        rospy.loginfo("kibo user node ready")

    def _on_start(self, msg):
        with self._start_lock:
            if self._started:
                rospy.logwarn("start already processed")
                return
            self._started = True
        rospy.loginfo("start %s", msg)
        try:
            report = run_mission(self._robot, DEFAULT_MISSION)
            rospy.loginfo("mission report: %s", report)
        except Exception as exc:  # 任何例外都不能讓節點靜悄悄死掉，也不能沒有完成回報
            rospy.logerr("mission failed: %s", exc)
            try:
                rospy.logwarn("mission_finished after failure: %s", self._robot.mission_finish())
            except Exception as finish_exc:
                rospy.logerr("mission_finished also failed: %s", finish_exc)

    def _on_stop(self, request):
        try:
            self._robot.request_stop()
            rospy.loginfo("stop processing done")
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.SUCCESS)
        except Exception as exc:
            rospy.logerr("stop processing failed: %s", exc)
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.ERROR)


def main():
    rospy.init_node("krpc_user_node")
    UserNode()
    rospy.spin()


if __name__ == "__main__":
    main()
