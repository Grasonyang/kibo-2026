"""讀 ROS 的連線資訊：誰在發、誰訂了、誰已經真的連上。純函式，不 import rospy。

兩個用途，都在起跑那一刻：
- 送出去的：起跑前確認事件 topic 的每個訂閱者都已經連上發佈者，再送任務開始
  （`ros/user_node.py` 的 `_wait_for_event_listeners`）。
- 收進來的：起跑訊號的發佈者只存在 3 秒，有人在發而我們還沒連上時自己去連
  （`ros/start_watch.py` 的 `watch_for_start`）。

第一個用途不認節點名字：「master 登記的訂閱者全部都連上了」就算好，
所以評分模組改名、多一個或少一個旁聽的節點都不受影響。

三種資料：
- master 的 `getSystemState`：`[publishers, subscribers, services]`，每一項是 `[名稱, [節點…]]`。
- 節點的 `getBusInfo`：每一列 `[連線編號, 對方, 方向, 傳輸, topic, 是否已連上, …]`，
  方向 "o" 是往外送（發佈者那一側）。
- master 的 `getPublishedTopics`：`[[topic, 型別], …]`，只列至少有一個發佈者的 topic。
"""

from typing import Any, List, Optional, Sequence, Tuple


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


def is_published(published_topics: Any, topic: str) -> bool:
    """master 的 getPublishedTopics 裡有沒有這個 topic（有就代表現在至少有一個發佈者）。
    讀不懂就當作沒有：呼叫端只會少做一次多餘的連線，不會誤動作。"""
    if not isinstance(published_topics, (list, tuple)):
        return False
    for entry in published_topics:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2 and entry[0] == topic:
            return True
    return False


def loopback_uri(node_uri: Any) -> Optional[str]:
    """節點自己的 XMLRPC 位址換成 127.0.0.1、同一個埠：呼叫自己不必經過名稱解析
    （模擬器裡名稱解析偶爾會卡 5 秒）。看不出埠號就回 None。"""
    if not isinstance(node_uri, str):
        return None
    port = node_uri.rstrip("/").rsplit(":", 1)[-1]
    if not port.isdigit() or not 0 < int(port) < 65536:
        return None
    return "http://127.0.0.1:%d/" % int(port)


class Unconnected(object):
    """數「有人在發、我們卻沒連上」連續看到幾次；到 `patience` 次就該自己去連。

    連續才算：正常流程在發佈者出現後幾毫秒內就連上，只看到一次就動手會和它搶。
    說了「該去連」之後從頭數起：連線要一點時間才會算數，馬上再連一次只是疊上去。"""

    def __init__(self, patience: int) -> None:
        self.patience = patience
        self.count = 0

    def seen(self, published: bool, connections: int) -> bool:
        """記下這一次看到的情況；回傳現在是不是該自己去連。"""
        self.count = self.count + 1 if published and connections == 0 else 0
        if self.count < self.patience:
            return False
        self.count = 0
        return True
