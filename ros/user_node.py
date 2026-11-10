#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""ROS 接線層：把 Int-Ball2 的 topic、service、action 接到 kibo 的任務邏輯。

這個檔案要放進官方範本的 krpc_user/scripts/（見 ros/README.md）。它只做翻譯：
ROS 訊息 <-> kibo 的 Pose 與 MOVE_* 結果。決策全部在 kibo.mission。

保留了官方範本標 DO NOT REMOVE 的三件事：
- 訂閱 /ib2_user/start（任務起點）
- 提供 /ib2_user/stop（停止要求：先取消動作再回應）
- 設定 /ib2_user/ready = True

執行環境是 Python 3.6.9 / ROS Melodic。shebang 與官方範本相同（/usr/bin/python3；
映像裡的 `python` 是 2.7）。
"""

import collections
import os
import sys
import threading
import time
import xmlrpc.client

# kibo/ 由 scripts/sim.sh 同步到這個檔案旁邊。直接執行時 sys.path[0] 本來就是這裡；
# 若日後改由 catkin 安裝後的包裝腳本啟動，這行讓 `import kibo` 仍然找得到。
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

# 一定要在 import rospy 之前。模擬器的映像是 Ubuntu 18.04（glibc 2.27），容器名稱靠 Docker 內建
# DNS 解析；glibc 預設同時送 A 與 AAAA 查詢，其中一個回應會被丟掉，於是**每個執行緒**頭幾次
# 查詢各卡 5 秒（rospy 連 master 與服務時都會查）。實測第一場因此在起跑時白等了 10 秒。
# single-request 讓兩個查詢一前一後送，就不會卡。實機上沒有這個問題，設了也無害。
os.environ.setdefault("RES_OPTIONS", "single-request")

import actionlib
import rosgraph
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

from kibo.buslinks import missing_listeners, topic_parties
from kibo.geometry import Pose
from kibo.mission import (
    DEFAULT_MISSION,
    MOVE_ABORTED,
    MOVE_INVALID,
    MOVE_SUCCESS,
    MOVE_TIMEOUT,
    Robot,
    run_mission,
)
from kibo.vision import gray_from_raw, observe_markers

SERVICE_TIMEOUT_SEC = 10.0  # 等服務出現，以及等它回應，各自的上限
SERVICE_POLL_SEC = 0.05
SERVICE_MAX_POLLS = int(SERVICE_TIMEOUT_SEC / SERVICE_POLL_SEC) + 2
ACTION_SERVER_TIMEOUT_SEC = 10.0
NOTIFY_TIMEOUT_SEC = 15.0
CANCEL_WAIT_SEC = 5.0
NAV_FRESH_SEC = 1.0  # 導航資料比這舊就當作沒有
NAV_HISTORY_STEP_SEC = 0.05  # 導航實測約 200 Hz；紀錄降到 20 Hz 就夠判斷「到點前最後 1 秒」
NAV_HISTORY_LEN = 64  # 20 Hz x 64 筆，約 3 秒
IMAGE_FRESH_SEC = 1.0
POLL_SEC = 0.2
EVENT_SERVICE = "/event/mission_start"
EVENT_TOPIC = "/gs/data"  # 官方的事件 API 把 mission_start 等事件轉發到這個 topic，評分模組在聽
EVENT_WAIT_SEC = 10.0  # 等「訂閱者都連上」的上限（牆鐘）
EVENT_QUERY_SEC = 2.0  # 問一次連線狀況的上限（牆鐘）；XMLRPC 本身沒有逾時
EVENT_MAX_POLLS = int(EVENT_WAIT_SEC / POLL_SEC) + 2
EVENT_ABSENT_POLLS = 3  # 連續這麼多次都沒有人發佈 EVENT_TOPIC，才認定這裡沒有這種接法

ACTION_DONE = "done"
ACTION_TIMEOUT = "timeout"
ACTION_STOPPED = "stopped"


class RosRobot(Robot):
    def __init__(self):
        self._nav = None  # 最新的 Navigation 訊息
        self._nav_history = collections.deque(maxlen=NAV_HISTORY_LEN)  # 最近幾秒的 Pose
        self._nav_count = 0
        self._nav_first_stamp = None  # 第一筆導航的 stamp，算頻率用
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
        # 只留最新一張：影像很大，排隊只會讓我們看到舊畫面
        self._image_sub = rospy.Subscriber(
            "/camera_main/image_raw", Image, self._on_image, queue_size=1, buff_size=2**24
        )
        self._info_sub = rospy.Subscriber(
            "/camera_main/camera_info", CameraInfo, self._on_info, queue_size=1
        )

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

    def recent_poses(self, seconds):
        oldest = rospy.get_time() - seconds
        with self._nav_lock:
            return [pose for pose in self._nav_history if pose.stamp >= oldest]

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
        self._wait_for_event_listeners()
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
    def _wait_for_event_listeners(self):
        """等到事件 topic 的訂閱者都連上，再送任務開始。有牆鐘上限；這裡沒有這種接法就不等。

        為什麼：官方的事件 API 節點把 mission_start 轉發到一個沒有 latch 的 topic（EVENT_TOPIC），
        評分模組要連上才收得到。API 節點與我們同時啟動；我們若在評分模組連上之前就呼叫
        mission_start，「開始」會遺失，之後整場的通過通知與完成回報都被評分模組當成
        「任務還沒開始」丟掉。2026-11-10 本機模擬器實際發生過兩次（整場沒有成績）。
        官方範本沒中，只是因為它被 DNS 延遲拖了 5 秒。

        規則不認節點名字：master 登記的訂閱者全部都和發佈者連上了，就出發。
        這段等待用牆鐘計時（模擬時鐘停住也不會卡住），最多 EVENT_WAIT_SEC；等不到照樣出發，
        因為不出發一定 0 分。等待的秒數算在我們自己的時間預算裡（保守，見 kibo.mission 的 t0）。"""
        try:
            # 服務出現之後，API 節點的發佈者一定已經登記（它先建 publisher 才建 service）。
            rospy.wait_for_service(EVENT_SERVICE, timeout=SERVICE_TIMEOUT_SEC)
        except rospy.ROSException as exc:
            rospy.logerr("%s unavailable: %s", EVENT_SERVICE, exc)
            return
        started = time.time()
        absent = 0
        status = None
        for _ in range(EVENT_MAX_POLLS):
            status = self._bounded(self._event_listener_status, EVENT_QUERY_SEC)
            if status is not None:
                publishers, missing = status
                if publishers and not missing:
                    rospy.loginfo("event listeners connected after %.1fs", time.time() - started)
                    return
                absent = 0 if publishers else absent + 1
                if absent >= EVENT_ABSENT_POLLS:
                    rospy.loginfo("nobody publishes %s here; not waiting", EVENT_TOPIC)
                    return
            if self.stop_requested() or time.time() - started > EVENT_WAIT_SEC:
                break
            time.sleep(POLL_SEC)
        rospy.logwarn(
            "listeners on %s not all connected after %.1fs (last status: %s); starting anyway",
            EVENT_TOPIC,
            time.time() - started,
            status,
        )

    @staticmethod
    def _event_listener_status():
        """回傳 (EVENT_TOPIC 的發佈者, 還沒連上任何一個發佈者的訂閱者)。

        問 master 誰發誰訂（getSystemState），再問每個發佈者它的連線（slave API 的 getBusInfo）。
        這幾個 XMLRPC 呼叫都沒有逾時，所以一定要經過 `_bounded` 呼叫。"""
        caller = rospy.get_name()
        master = rosgraph.Master(caller)
        publishers, subscribers = topic_parties(master.getSystemState(), EVENT_TOPIC)
        missing = []
        for publisher in publishers:
            reply = xmlrpc.client.ServerProxy(master.lookupNode(publisher)).getBusInfo(caller)
            bus_info = reply[2] if isinstance(reply, (list, tuple)) and len(reply) >= 3 else None
            missing.extend(missing_listeners(bus_info, EVENT_TOPIC, subscribers))
        return publishers, missing

    @staticmethod
    def _bounded(function, wall_timeout_sec):
        """在 daemon thread 裡呼叫 `function()`，最多等 wall_timeout_sec（牆鐘）。

        回傳它的結果；逾時或丟例外回 None（例外記一行）。逾時時那個 thread 會留在背景，
        不會擋住任務。"""
        box = {}
        done = threading.Event()

        def worker():
            try:
                box["result"] = function()
            except Exception as exc:  # 查詢失敗只是「不知道」，不能讓任務出事
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=worker, name="bounded", daemon=True).start()
        if not done.wait(wall_timeout_sec):
            rospy.logwarn("query did not answer within %.1fs", wall_timeout_sec)
            return None
        if "error" in box:
            rospy.logwarn("query failed: %r", box["error"])
            return None
        return box.get("result")

    def _on_nav(self, msg):
        stamp = msg.pose.header.stamp.to_sec()
        with self._nav_lock:
            self._nav = msg
            self._nav_count += 1
            if self._nav_first_stamp is None:
                self._nav_first_stamp = stamp
            history = self._nav_history
            if history and 0.0 <= stamp - history[-1].stamp < NAV_HISTORY_STEP_SEC:
                return  # 這個 callback 一秒跑 200 次，大部分在這裡就結束
            p = msg.pose.pose.position
            q = msg.pose.pose.orientation
            history.append(Pose((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), stamp=stamp))

    def _on_image(self, msg):
        with self._image_lock:
            self._image = msg

    def _on_info(self, msg):
        with self._image_lock:
            self._camera_info = msg

    @staticmethod
    def _to_gray(image):
        gray = gray_from_raw(image.data, image.width, image.height, image.step, image.encoding)
        if gray is None:
            rospy.logwarn("unsupported image: encoding=%s step=%d", image.encoding, image.step)
        return gray

    def _on_ctl(self, msg):
        """/ctl/status 的 type 是 CtlStatusType，裡面才是 int32 type（手冊 6.3.2）。
        只在狀態改變時記一行，第一場就能看到 RELEASE 何時結束、有沒有 DISTURBED。"""
        new_type = msg.type.type
        if new_type != self._ctl_type:
            rospy.loginfo(
                "[t=%.1f] ctl_status %s -> %s", rospy.get_time(), self._ctl_type, new_type
            )
            self._ctl_type = new_type

    def survey(self):
        """只印資料、不阻塞、不丟例外：nav 頻率（第一筆到最新一筆）、stamp、status、
        camera_info、影像 encoding、sim time。失敗只 log，絕不影響任務。"""
        try:
            self._survey()
        except Exception as exc:  # 診斷碼不能讓任務變 0 分
            rospy.logwarn("[survey] failed: %s", exc)

    def _survey(self):
        with self._nav_lock:
            nav, count, first = self._nav, self._nav_count, self._nav_first_stamp
        # 用導航自己的 stamp 算頻率：節點剛啟動時模擬時鐘可能還是 0，不能拿啟動時刻當起點。
        window = 1e-3
        if nav is not None and first is not None:
            window = max(nav.pose.header.stamp.to_sec() - first, 1e-3)
        rospy.loginfo(
            "[survey] use_sim_time=%s now=%.3f nav_msgs=%d over %.1fs (%.1f Hz)",
            rospy.get_param("/use_sim_time", False),
            rospy.get_time(),
            count,
            window,
            count / window,
        )
        if nav is not None:
            p = nav.pose.pose.position
            rospy.loginfo(
                "[survey] nav frame=%s stamp=%.3f age=%.3f status=%s pos=(%.3f, %.3f, %.3f)",
                nav.pose.header.frame_id,
                nav.pose.header.stamp.to_sec(),
                (rospy.Time.now() - nav.pose.header.stamp).to_sec(),
                getattr(nav, "status", None),
                p.x,
                p.y,
                p.z,
            )
        else:
            rospy.logwarn("[survey] no navigation message yet")
        with self._image_lock:
            image, info = self._image, self._camera_info
        if info is not None:
            rospy.loginfo(
                "[survey] camera_info %dx%d K=%s D=%s",
                info.width,
                info.height,
                list(info.K),
                list(info.D),
            )
        if image is not None:
            rospy.loginfo(
                "[survey] image %dx%d encoding=%s step=%d",
                image.width,
                image.height,
                image.encoding,
                image.step,
            )
        rospy.loginfo("[survey] ctl_status=%s", self._ctl_type)

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
        # 牆鐘與 ROS 時間各自有上限：sim time 停住時牆鐘擋，牆鐘跑太快時 ROS 時間擋；次數也有上限。
        ros_deadline = rospy.get_time() + SERVICE_TIMEOUT_SEC
        for _ in range(SERVICE_MAX_POLLS):
            if done.wait(SERVICE_POLL_SEC):
                break
            if rospy.get_time() > ros_deadline or rospy.is_shutdown():
                break
        if not done.is_set():
            rospy.logerr("%s did not respond within %.0fs", name, SERVICE_TIMEOUT_SEC)
            return None
        if "error" in box:
            rospy.logerr("%s failed: %s", name, box["error"])
            return None
        waited = SERVICE_TIMEOUT_SEC - (ros_deadline - rospy.get_time())
        if waited > 1.0:  # 正常是幾毫秒；慢了要在 log 留下證據
            rospy.logwarn("%s took %.1fs", name, waited)
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
                if self.stop_requested() or rospy.get_time() > deadline:
                    break
            # 走到這裡有三種：收到停止、過了期限、輪詢次數用完。後兩種都是逾時。
            client.cancel_goal()
            client.wait_for_result(rospy.Duration(CANCEL_WAIT_SEC))
            return (ACTION_STOPPED if self.stop_requested() else ACTION_TIMEOUT), None
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
            if rospy.get_param("~survey_only", False):
                # 第 1 場「只收資料」：開始、等 5 秒累積訊息、印 survey、完成回報，不飛。
                rospy.logwarn("survey_only: not flying")
                self._robot.mission_start()
                rospy.sleep(5.0)
                self._robot.survey()
                self._robot.mission_finish()
                return
            self._robot.survey()  # 不阻塞、不丟例外；只是在任務前印一次數字
            # run_mission 自己保證 mission_finish（例外也會），這裡只做接線。
            report = run_mission(self._robot, self._config())
            rospy.loginfo("mission report: %s", report)
        except Exception as exc:  # 任何例外都不能讓節點靜悄悄死掉
            rospy.logerr("mission failed: %s", exc)

    @staticmethod
    def _config():
        """比賽用 DEFAULT_MISSION。探針只在資格賽模擬器上用，用 ROS 參數開，跑完就不要再帶。"""
        config = DEFAULT_MISSION._replace(
            notify_even_if_level0=bool(rospy.get_param("~probe_notify_even_if_level0", False)),
            skip_one_waypoint=bool(rospy.get_param("~probe_skip_one_waypoint", False)),
            deliberate_late_after=int(rospy.get_param("~probe_deliberate_late_after", 0)),
        )
        if config.probes_on:
            rospy.logwarn("PROBE FLAGS ON via ROS params; never submit this to the final round")
        return config

    def _on_stop(self, request):
        try:
            self._robot.request_stop()
            rospy.loginfo("stop processing done")
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.SUCCESS)
        except Exception as exc:
            rospy.logerr("stop processing failed: %s", exc)
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.ERROR)


def main():
    rospy.init_node("krpc_user")  # 官方用 /krpc_user 這個名字擷取 log、結束節點（run.sh）
    UserNode()
    rospy.spin()


if __name__ == "__main__":
    main()
