# -*- coding: utf-8 -*-
"""起跑訊號的保險：有人在發 /ib2_user/start 而我們還沒連上時，自己去連。

為什麼：模擬器用 `rostopic pub --once` 送起跑訊號（官方 run.sh 的 go），發佈者只存在 3 秒。
ROS 的正常流程是 master 通知我們「有新的發佈者」，我們再去連；這個通知或連線若晚了 3 秒，
訊號就沒了，節點整場不動、沒有成績。2026-11-11 本機模擬器實際發生一次
（docs/kibo/simulator-internals.md 的 E 表）。

做法只用 ROS 公開的 XMLRPC API，不碰 /ib2_user/start 的訂閱本身（官方標 DO NOT REMOVE）：
1. 每 POLL_SEC 問 master 一次 /ib2_user 底下現在有哪些 topic 有發佈者（getPublishedTopics，唯讀）。
2. 起跑訊號有發佈者、我們的訂閱卻連續兩次都是 0 條連線：向 master 重新登記同一個訂閱
   （registerSubscriber 會回傳目前的發佈者位址；重複登記不會多一筆），
   再把位址交給自己的 publisherUpdate，和 master 通知我們時走同一條路。
3. 收到起跑訊號、節點關閉、超過 WATCH_SEC、或已經主動連了 MAX_CONNECTS 次就結束。

連續兩次才動手，是為了不和正常流程搶：正常時發佈者出現後幾毫秒內就連上了。
動手之後也要再等兩次才會再動手。整段在 daemon thread 裡跑；XMLRPC 呼叫卡住
（rospy 給它 60 秒的逾時）只會讓這個保險失效，不影響正常流程。

蓋得到的：master 的通知晚到或沒到；我們去問發佈者「怎麼連」（requestTopic）時卡住，
下一次再試。蓋不到的：已經問到、TCP 連線卻卡住（那時連線數已經算 1，保險不會再動）。
WATCH_SEC 之後這個保險就不在了：節點啟動後超過這麼久才起跑的場合，只剩 ROS 原本的通知。
"""

import time
import xmlrpc.client

import rosgraph
import rospy

from kibo.buslinks import Unconnected, is_published, loopback_uri

START_TOPIC = "/ib2_user/start"
START_TYPE = "platform_msgs/UserLogic"
START_NAMESPACE = "/ib2_user"
POLL_SEC = 0.25  # 發佈者只存在 3 秒：發現、確認、連上都要在這之內
PATIENCE = 2  # 連續這麼多次都是「有人在發、我們沒連上」才動手
WATCH_SEC = 3600.0  # 最多看這麼久（牆鐘）；之後仍有 ROS 原本的通知
MAX_CONNECTS = 20  # 主動去連最多這麼多次；一直連不上就不再試
MAX_POLLS = int(WATCH_SEC / POLL_SEC) + 2


def watch_for_start(subscriber, started):
    """看著起跑訊號的發佈者，直到 `started()` 為真。回傳主動去連的次數。

    `subscriber` 是 /ib2_user/start 的 rospy.Subscriber。"""
    name = rospy.get_name()
    node_uri = rospy.get_node_uri()
    own_api = loopback_uri(node_uri)
    if own_api is None:
        rospy.logwarn("start watch off: cannot read own API address %r", node_uri)
        return 0
    master = rosgraph.Master(name)
    began = time.time()
    unconnected = Unconnected(PATIENCE)
    connects = 0
    last_error = None
    for _ in range(MAX_POLLS):
        if started() or rospy.is_shutdown() or time.time() - began > WATCH_SEC:
            break
        if connects >= MAX_CONNECTS:
            rospy.logwarn("start watch: gave up after %d connects", connects)
            break
        try:
            published = is_published(master.getPublishedTopics(START_NAMESPACE), START_TOPIC)
            if unconnected.seen(published, subscriber.get_num_connections()):
                publishers = master.registerSubscriber(START_TOPIC, START_TYPE, node_uri)
                if publishers:
                    connects += 1
                    rospy.logwarn(
                        "%s is published but not connected; connecting to %s",
                        START_TOPIC,
                        publishers,
                    )
                    xmlrpc.client.ServerProxy(own_api).publisherUpdate(
                        name, START_TOPIC, publishers
                    )
        except Exception as exc:  # 保險本身不能讓節點出事；同樣的錯只記一次
            if repr(exc) != last_error:
                last_error = repr(exc)
                rospy.logwarn("start watch: %s", last_error)
        time.sleep(POLL_SEC)
    return connects
