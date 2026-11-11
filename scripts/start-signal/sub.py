#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""起跑訊號重現用的最小節點：訂閱 /ib2_user/start、設 /ib2_user/ready，等最多 9 秒。印一行 JSON。

argv[1] 是用加號接起來的選項：
- plain：什麼都不加（官方範本的行為）
- watch：開 ros/start_watch.py 的保險（和正式節點用同一份程式）
- drop ：丟掉 master 對起跑訊號的通知（通知沒到）
- delay:<秒>：master 的通知晚這麼多秒才處理（5 = 實際量到的延遲；0.6 = 剛好和保險同時到）
例：`delay:5+watch`。JSON 的欄位：`got` 有沒有收到、`starts` 起跑的回呼被叫了幾次（要是 1）、
`connects` 保險主動去連了幾次、`master_update_sec` master 的通知在 ready 之後幾秒到（沒到是 null）。
"""

import json
import os
import sys
import threading
import time

os.environ.setdefault("RES_OPTIONS", "single-request")  # 與 ros/user_node.py 相同
sys.path.insert(0, "/repo/ros")
sys.path.insert(0, "/repo/src")

import rospy  # noqa: E402
import rospy.impl.masterslave as masterslave  # noqa: E402
from platform_msgs.msg import UserLogic  # noqa: E402
from start_watch import START_TOPIC, watch_for_start  # noqa: E402

OPTIONS = set(sys.argv[1].split("+"))
WAIT_SEC = 9.0
SETTLE_SEC = 1.0
DELAY_SEC = sum(float(option[6:]) for option in OPTIONS if option.startswith("delay:"))
got = threading.Event()
info = {"mode": sys.argv[1], "master_update_sec": None, "connects": 0, "starts": 0}
clock = {"ready": None}
original_update = masterslave.ROSHandler.publisherUpdate


def traced_update(self, caller_id, topic, publishers):
    """記下 master 的通知何時到；drop 選項不處理它，delay 選項晚一點才處理。"""
    if topic == START_TOPIC and caller_id == "/master" and publishers:
        if info["master_update_sec"] is None and clock["ready"] is not None:
            info["master_update_sec"] = round(time.time() - clock["ready"], 2)
        if "drop" in OPTIONS:
            return 1, "dropped on purpose", 0
        time.sleep(DELAY_SEC)  # XMLRPC 伺服器一個要求一個執行緒，睡在這裡不會擋到保險
    return original_update(self, caller_id, topic, publishers)


traced_update.__dict__.update(getattr(original_update, "__dict__", {}))
masterslave.ROSHandler.publisherUpdate = traced_update


def on_start(message):
    info["starts"] += 1
    got.set()


def main():
    rospy.init_node("krpc_user")
    subscriber = rospy.Subscriber(START_TOPIC, UserLogic, on_start)
    rospy.set_param("/ib2_user/ready", True)
    clock["ready"] = time.time()
    watcher = None
    if "watch" in OPTIONS:

        def watch():
            info["connects"] = watch_for_start(subscriber, got.is_set)

        watcher = threading.Thread(target=watch)
        watcher.daemon = True
        watcher.start()
    info["got"] = got.wait(WAIT_SEC)
    info["sec"] = round(time.time() - clock["ready"], 2)
    if watcher is not None:
        watcher.join(2.0)  # 等保險的執行緒把次數寫回來
    time.sleep(SETTLE_SEC)  # 晚到的第二則訊號（如果有）也要數到
    print(json.dumps(info, sort_keys=True))
    sys.stdout.flush()
    try:
        rospy.delete_param("/ib2_user/ready")
    except Exception:  # master 不在了也無妨，這只是收尾
        pass


if __name__ == "__main__":
    main()
