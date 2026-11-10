"""起跑前要確認評分模組已經連上事件 topic；這裡測「怎麼讀連線清單」。"""

from kibo.buslinks import topic_has_listener

TOPIC = "/gs/data"
JUDGE = [3, "/kibo_rpc_judge", "o", "TCPROS", TOPIC, True, "TCPROS connection on port 40105"]
ROSBAG = [4, "/record_rosbag", "o", "TCPROS", TOPIC, True, "TCPROS connection on port 40105"]
OTHER_TOPIC = [5, "/rosout", "o", "TCPROS", "/rosout", True]


def test_no_connections_means_nobody_is_listening():
    assert not topic_has_listener([], TOPIC)


def test_the_judge_connected_on_the_event_topic_counts():
    assert topic_has_listener([OTHER_TOPIC, JUDGE], TOPIC)


def test_a_recorder_alone_does_not_count():
    # 2026-11-10 那場 0 分：rosbag 先連上了，評分模組還沒。
    assert not topic_has_listener([OTHER_TOPIC, ROSBAG], TOPIC)


def test_a_connection_that_is_not_established_yet_does_not_count():
    pending = list(JUDGE)
    pending[5] = False
    assert not topic_has_listener([pending], TOPIC)


def test_inbound_connections_on_the_same_topic_do_not_count():
    inbound = list(JUDGE)
    inbound[2] = "i"
    assert not topic_has_listener([inbound], TOPIC)


def test_old_style_rows_without_the_connected_flag_count():
    assert topic_has_listener([JUDGE[:5]], TOPIC)


def test_garbage_is_treated_as_nobody_listening():
    assert not topic_has_listener(None, TOPIC)
    assert not topic_has_listener([None, "x", [1, 2]], TOPIC)


def test_other_listeners_do_not_stand_in_for_the_judge():
    # 2026-11-10 批次的 normal 場：飛行記錄與狀態顯示先連上，評分模組還沒，開始事件一樣遺失。
    recorder = [6, "/krpc_flight_recorder", "o", "TCPROS", TOPIC, True]
    indicator = [7, "/krpc_status_indicator", "o", "TCPROS", TOPIC, True]
    assert not topic_has_listener([recorder, indicator], TOPIC, must_contain="judge")
    assert topic_has_listener([recorder, indicator, JUDGE], TOPIC, must_contain="judge")
