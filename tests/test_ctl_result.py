"""移動指令的結果：ROS action 的（狀態、結果碼）翻成任務邏輯懂的 MOVE_*。"""

import pytest

from kibo.ctl_result import (
    ACTION_DONE,
    ACTION_STOPPED,
    ACTION_TIMEOUT,
    MOVE_ABORTED,
    MOVE_INVALID,
    MOVE_SUCCESS,
    MOVE_TIMEOUT,
    TERMINATE_ABORTED,
    TERMINATE_INVALID_CMD,
    TERMINATE_INVALID_NAV,
    TERMINATE_SUCCESS,
    TERMINATE_TIME_OUT,
    mismatched_codes,
    move_outcome,
)


@pytest.mark.parametrize(
    "status,result_type,expected",
    [
        (ACTION_DONE, TERMINATE_SUCCESS, MOVE_SUCCESS),
        (ACTION_DONE, TERMINATE_ABORTED, MOVE_ABORTED),
        (ACTION_DONE, TERMINATE_TIME_OUT, MOVE_TIMEOUT),
        (ACTION_DONE, TERMINATE_INVALID_NAV, MOVE_INVALID),
        (ACTION_DONE, TERMINATE_INVALID_CMD, MOVE_INVALID),
        (ACTION_DONE, None, MOVE_ABORTED),  # 被拒絕，或 server 沒帶 result
        (ACTION_DONE, 99, MOVE_ABORTED),  # 不認得的結果碼
        (ACTION_TIMEOUT, None, MOVE_TIMEOUT),  # 我們自己等到逾時並取消
        (ACTION_STOPPED, None, MOVE_ABORTED),  # 收到停止要求
        (ACTION_TIMEOUT, TERMINATE_SUCCESS, MOVE_TIMEOUT),  # 逾時就是逾時，不看結果碼
    ],
)
def test_move_outcome(status, result_type, expected):
    assert move_outcome(status, result_type) == expected


def test_result_codes_match_the_action_definition():
    # ib2_msgs/action/CtlCommand.action 的常數：
    # SUCCESS 0、ABORTED 1、TIME_OUT 2、INVALID_NAV 3、INVALID_CMD 4
    assert (
        TERMINATE_SUCCESS,
        TERMINATE_ABORTED,
        TERMINATE_TIME_OUT,
        TERMINATE_INVALID_NAV,
        TERMINATE_INVALID_CMD,
    ) == (0, 1, 2, 3, 4)


def test_a_changed_message_definition_is_noticed():
    official = {
        "TERMINATE_SUCCESS": 0,
        "TERMINATE_ABORTED": 1,
        "TERMINATE_TIME_OUT": 2,
        "TERMINATE_INVALID_NAV": 3,
        "TERMINATE_INVALID_CMD": 4,
    }
    assert mismatched_codes(official) == []
    changed = dict(official, TERMINATE_TIME_OUT=5)
    del changed["TERMINATE_INVALID_CMD"]
    assert mismatched_codes(changed) == ["TERMINATE_INVALID_CMD", "TERMINATE_TIME_OUT"]
