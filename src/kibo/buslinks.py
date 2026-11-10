"""讀 ROS 節點的連線清單（slave API `getBusInfo` 的回傳）。純函式，不 import rospy。

用途只有一個：起跑前確認官方事件 API 節點的事件 topic 已經有人連上（見 ros/user_node.py 的
`_wait_for_event_listener`）。清單每一列是
`[連線編號, 對方, 方向, 傳輸, topic, 是否已連上, ...]`，方向 "o" 是往外送（publisher 那一側）。
"""

from typing import Any, Iterable, Sequence

# 這些訂閱者只是在錄資料，不是評分模組；它們連上不代表事件有人處理。
RECORDER_HINTS: Sequence[str] = ("rosbag", "record")


def topic_has_listener(bus_info: Any, topic: str, ignore: Iterable[str] = RECORDER_HINTS) -> bool:
    """`bus_info` 裡有沒有 `topic` 的、已建立的對外連線（不算錄資料的節點）。

    格式不對的列一律略過；整個東西不是清單就當作沒有。"""
    if not isinstance(bus_info, (list, tuple)):
        return False
    hints = tuple(ignore)
    for row in bus_info:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        if row[4] != topic or row[2] != "o":
            continue
        peer = str(row[1])
        if any(hint in peer for hint in hints):
            continue
        if len(row) > 5 and not row[5]:
            continue
        return True
    return False
