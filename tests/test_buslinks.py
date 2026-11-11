"""起跑前要確認事件 topic 的每個訂閱者都已經連上；這裡測「怎麼讀 ROS 的連線資訊」。

資料形狀照 ROS master 的 getSystemState 與節點的 getBusInfo（都是清單的清單）。
"""

from kibo.buslinks import (
    Unconnected,
    is_published,
    loopback_uri,
    missing_listeners,
    topic_parties,
)

TOPIC = "/gs/data"
API = "/krpc_api_node"
JUDGE = "/kibo_rpc_judge"
RECORDER = "/krpc_flight_recorder"

# getSystemState：[publishers, subscribers, services]，每一項是 [名稱, [節點…]]
STATE = [
    [["/rosout", ["/krpc_user", API]], [TOPIC, [API]]],
    [["/rosout", ["/rosout"]], [TOPIC, [JUDGE, RECORDER]]],
    [["/event/mission_start", [API]]],
]


def link(peer, topic=TOPIC, direction="o", connected=True):
    # getBusInfo 的一列：[連線編號, 對方, 方向, 傳輸, topic, 是否已連上, 說明]
    return [1, peer, direction, "TCPROS", topic, connected, "TCPROS connection"]


def test_topic_parties_lists_who_publishes_and_who_subscribes():
    assert topic_parties(STATE, TOPIC) == ([API], [JUDGE, RECORDER])


def test_a_topic_nobody_publishes_has_no_parties():
    # 實機沒有這個 topic：沒有發佈者，就不用等任何人。
    assert topic_parties(STATE, "/not/there") == ([], [])


def test_everyone_connected_means_nobody_is_missing():
    bus = [link("/rosout", topic="/rosout"), link(JUDGE), link(RECORDER)]
    assert missing_listeners(bus, TOPIC, [JUDGE, RECORDER]) == []


def test_the_judge_not_connected_yet_is_reported_missing():
    # 2026-11-10 兩場無成績：別的訂閱者先連上了，評分模組還沒，開始事件就送出去了。
    assert missing_listeners([link(RECORDER)], TOPIC, [JUDGE, RECORDER]) == [JUDGE]


def test_a_connection_still_being_set_up_does_not_count():
    assert missing_listeners([link(JUDGE, connected=False)], TOPIC, [JUDGE]) == [JUDGE]


def test_inbound_links_and_other_topics_do_not_count():
    bus = [link(JUDGE, direction="i"), link(JUDGE, topic="/rosout")]
    assert missing_listeners(bus, TOPIC, [JUDGE]) == [JUDGE]


def test_old_style_rows_without_the_connected_flag_count_as_connected():
    assert missing_listeners([link(JUDGE)[:5]], TOPIC, [JUDGE]) == []


def test_no_registered_subscribers_means_nothing_to_wait_for():
    assert missing_listeners([], TOPIC, []) == []


def test_garbage_is_read_as_nothing_known():
    assert topic_parties(None, TOPIC) == ([], [])
    assert topic_parties([["oops"], 3], TOPIC) == ([], [])
    assert missing_listeners(None, TOPIC, [JUDGE]) == [JUDGE]
    assert missing_listeners([None, "x", [1, 2]], TOPIC, [JUDGE]) == [JUDGE]


# ---- 起跑訊號：有人在發而我們還沒連上時，自己去連（ros/user_node.py 的 _watch_for_start）----


def test_a_topic_is_published_when_the_master_lists_it():
    # getPublishedTopics：[[topic, type], …]，只列至少有一個發佈者的 topic
    listed = [["/ib2_user/start", "platform_msgs/UserLogic"], ["/rosout", "rosgraph_msgs/Log"]]
    assert is_published(listed, "/ib2_user/start")
    assert not is_published(listed, "/ib2_user/stop")


def test_an_unreadable_topic_list_counts_as_not_published():
    for garbage in (None, "nope", 3, [None, "x", ["only-one-field"], []]):
        assert not is_published(garbage, "/ib2_user/start")


def test_the_node_reaches_its_own_api_without_a_name_lookup():
    # 節點向 master 登記的位址用主機名稱；呼叫自己走 127.0.0.1 同一個埠，不經過 DNS。
    assert loopback_uri("http://krpc-user:40805/") == "http://127.0.0.1:40805/"
    assert loopback_uri("http://10.0.0.7:5123") == "http://127.0.0.1:5123/"


def test_an_address_without_a_usable_port_gives_none():
    for bad in (None, "", "krpc-user", "http://krpc-user/", "http://krpc-user:abc/", "http://h:0/"):
        assert loopback_uri(bad) is None


def test_one_unconnected_look_is_not_enough_to_step_in():
    # 正常流程在發佈者出現後幾毫秒內就連上；只看到一次「還沒連上」就動手會和它搶。
    watch = Unconnected(patience=2)
    assert not watch.seen(published=True, connections=0)
    assert watch.seen(published=True, connections=0)


def test_being_connected_or_unpublished_starts_the_count_again():
    watch = Unconnected(patience=2)
    assert not watch.seen(published=True, connections=0)
    assert not watch.seen(published=True, connections=1)
    assert not watch.seen(published=True, connections=0)
    assert not watch.seen(published=False, connections=0)
    assert not watch.seen(published=True, connections=0)
    assert watch.seen(published=True, connections=0)


def test_after_stepping_in_it_waits_the_same_patience_before_trying_again():
    # 去連之後要一點時間連線才會算數；每次輪詢都再連一次只會疊出一堆並行的連線。
    # 但一直沒連上（對方剛好不通）還是要再試。
    watch = Unconnected(patience=2)
    looks = [watch.seen(published=True, connections=0) for _ in range(6)]
    assert looks == [False, True, False, True, False, True]
