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
from geometry_msgs.msg import PoseStamped
from ib2_msgs.msg import (
    CtlCommandAction,
    CtlCommandGoal,
    CtlCommandResult,
    CtlStatusType,
    Navigation,
)
from krpc_ib2_msgs.msg import CheckpointPassedAction, CheckpointPassedGoal
from krpc_ib2_msgs.srv import CheckPoints, MissionFinished, MissionStart
from platform_msgs.msg import UserLogic
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse

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

SERVICE_TIMEOUT_SEC = 10.0
ACTION_SERVER_TIMEOUT_SEC = 10.0
NAV_FRESH_SEC = 1.0  # 導航資料比這舊就當作沒有
POLL_SEC = 0.2


class RosRobot(Robot):
    def __init__(self):
        self._nav = None  # 最新的 Navigation 訊息
        self._nav_lock = threading.Lock()
        self._stop = False
        self._active_goals = []  # 正在執行的 action client，停止時要取消

        self._command = actionlib.SimpleActionClient("/ctl/command", CtlCommandAction)
        self._checkpoint = actionlib.SimpleActionClient(
            "/event/checkpoint_passed", CheckpointPassedAction
        )
        self._mission_start = rospy.ServiceProxy("/event/mission_start", MissionStart)
        self._mission_finished = rospy.ServiceProxy("/event/mission_finished", MissionFinished)
        self._checkpoints = rospy.ServiceProxy("/mission/get_checkpoints", CheckPoints)
        self._nav_sub = rospy.Subscriber("/sensor_fusion/navigation", Navigation, self._on_nav)

    # ---- Robot 介面 ----
    def now(self):
        return rospy.get_time()

    def sleep(self, sec):
        rospy.sleep(sec)

    def log(self, message):
        rospy.loginfo(message)

    def stop_requested(self):
        return self._stop or rospy.is_shutdown()

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
        return Pose((p.x, p.y, p.z), (q.x, q.y, q.z, q.w))

    def move_to(self, target, timeout_sec):
        if not self._command.wait_for_server(rospy.Duration(ACTION_SERVER_TIMEOUT_SEC)):
            rospy.logerr("/ctl/command server unavailable")
            return MOVE_ABORTED
        goal = CtlCommandGoal(
            target=self._pose_stamped(target),
            type=CtlStatusType(type=CtlStatusType.MOVE_TO_ABSOLUTE_TARGET),
        )
        result = self._run_action(self._command, goal, timeout_sec)
        if result is None:
            return MOVE_TIMEOUT
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
        result = self._run_action(self._checkpoint, goal, timeout_sec=15.0)
        if result is None:
            return False
        rospy.loginfo(
            "checkpoint_passed #%d: success=%s %s", checkpoint_id, result.success, result.message
        )
        return bool(result.success)

    # ---- 給節點用 ----
    def request_stop(self):
        """停止要求：取消所有執行中的 action，等它們結束。"""
        self._stop = True
        for client in list(self._active_goals):
            try:
                client.cancel_goal()
                client.wait_for_result(rospy.Duration(5.0))
            except Exception as exc:  # noqa: BLE001 - 停止流程不能因例外中斷
                rospy.logwarn("cancel failed: %s", exc)

    # ---- 內部 ----
    def _on_nav(self, msg):
        with self._nav_lock:
            self._nav = msg

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
        try:
            rospy.wait_for_service(name, timeout=SERVICE_TIMEOUT_SEC)
            return proxy()
        except (rospy.ROSException, rospy.ServiceException) as exc:
            rospy.logerr("%s failed: %s", name, exc)
            return None

    def _run_action(self, client, goal, timeout_sec):
        """送出 goal，輪詢到完成、逾時或停止；逾時與停止都會取消。回傳 result 或 None。"""
        client.send_goal(goal)
        self._active_goals.append(client)
        deadline = rospy.get_time() + timeout_sec
        max_polls = int(timeout_sec / POLL_SEC) + 2
        try:
            for _ in range(max_polls):
                if client.wait_for_result(rospy.Duration(POLL_SEC)):
                    return client.get_result()
                if self.stop_requested() or rospy.get_time() > deadline:
                    break
            client.cancel_goal()
            client.wait_for_result(rospy.Duration(5.0))
            return None
        finally:
            if client in self._active_goals:
                self._active_goals.remove(client)


class UserNode(object):
    def __init__(self):
        self._robot = RosRobot()
        self._started = False
        # DO NOT REMOVE THESE THREE LINES（官方範本要求）
        self._start_sub = rospy.Subscriber("/ib2_user/start", UserLogic, self._on_start)
        self._stop_srv = rospy.Service("/ib2_user/stop", StopProcessingUserNode, self._on_stop)
        rospy.set_param("/ib2_user/ready", True)
        rospy.loginfo("kibo user node ready")

    def _on_start(self, msg):
        if self._started:
            rospy.logwarn("start already processed")
            return
        self._started = True
        rospy.loginfo("start %s", msg)
        try:
            report = run_mission(self._robot, DEFAULT_MISSION)
            rospy.loginfo("mission report: %s", report)
        except Exception as exc:  # noqa: BLE001 - 任何例外都不能讓節點靜悄悄死掉
            rospy.logerr("mission failed: %s", exc)

    def _on_stop(self, request):
        try:
            self._robot.request_stop()
            rospy.loginfo("stop processing done")
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.SUCCESS)
        except Exception as exc:  # noqa: BLE001
            rospy.logerr("stop processing failed: %s", exc)
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.ERROR)


def main():
    rospy.init_node("krpc_user_node")
    UserNode()
    rospy.spin()


if __name__ == "__main__":
    main()
