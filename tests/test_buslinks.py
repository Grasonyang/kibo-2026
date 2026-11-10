"""起跑前要確認事件 topic 的每個訂閱者都已經連上；這裡測「怎麼讀 ROS 的連線資訊」。

資料形狀照 ROS master 的 getSystemState 與節點的 getBusInfo（都是清單的清單）。
"""

from kibo.buslinks import missing_listeners, topic_parties

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
