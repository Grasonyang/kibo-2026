"""讀 ROS 的連線資訊：誰在發、誰訂了、誰已經真的連上。純函式，不 import rospy。

用途只有一個：起跑前確認事件 topic 的每個訂閱者都已經連上發佈者，再送任務開始
（見 ros/user_node.py 的 `_wait_for_event_listeners`）。規則不認節點名字：
「master 登記的訂閱者全部都連上了」就算好，所以評分模組改名、多一個或少一個旁聽的節點都不受影響。

兩種資料：
- master 的 `getSystemState`：`[publishers, subscribers, services]`，每一項是 `[名稱, [節點…]]`。
- 節點的 `getBusInfo`：每一列 `[連線編號, 對方, 方向, 傳輸, topic, 是否已連上, …]`，
  方向 "o" 是往外送（發佈者那一側）。
"""

from typing import Any, List, Sequence, Tuple


def _nodes_for(section: Any, name: str) -> List[str]:
    if not isinstance(section, (list, tuple)):
        return []
    for entry in section:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2 and entry[0] == name:
            nodes = entry[1]
            if isinstance(nodes, (list, tuple)):
                return [str(node) for node in nodes]
    return []


def topic_parties(system_state: Any, topic: str) -> Tuple[List[str], List[str]]:
    """master 登記的（發佈者, 訂閱者）節點名稱。格式不對或沒有這個 topic 就回兩個空清單。"""
    if not isinstance(system_state, (list, tuple)) or len(system_state) < 2:
        return [], []
    return _nodes_for(system_state[0], topic), _nodes_for(system_state[1], topic)


def missing_listeners(bus_info: Any, topic: str, subscribers: Sequence[str]) -> List[str]:
    """`subscribers` 裡還沒和這個發佈者建立連線的節點；空清單代表大家都連上了。

    `bus_info` 是發佈者那個節點的 getBusInfo。格式不對的列一律略過，所以讀不懂時
    結果是「全部都還沒連上」，呼叫端會繼續等到上限，而不是誤以為可以出發。"""
    connected = set()
    if isinstance(bus_info, (list, tuple)):
        for row in bus_info:
            if not isinstance(row, (list, tuple)) or len(row) < 5:
                continue
            if row[4] != topic or row[2] != "o":
                continue
            if len(row) > 5 and not row[5]:
                continue  # 連線還在建立中
            connected.add(str(row[1]))
    return [node for node in subscribers if node not in connected]
