"""移動指令的結果：把 ROS action 的（狀態、結果碼）翻成任務邏輯懂的 MOVE_*。純函式。

結果碼是 `ib2_msgs/action/CtlCommand.action` 定義的常數，這裡照抄成整數，本機沒有 ROS 也能測。
節點啟動時會核對它們與訊息定義一致（ros/user_node.py）。
"""

from typing import Dict, List, Mapping, Optional

from kibo.mission import MOVE_ABORTED, MOVE_INVALID, MOVE_SUCCESS, MOVE_TIMEOUT

# 我們自己等 action 的結局
ACTION_DONE = "done"  # action 結束了（成功、失敗或被拒絕）
ACTION_TIMEOUT = "timeout"  # 等到期限，已取消
ACTION_STOPPED = "stopped"  # 收到停止要求，已取消

# CtlCommandResult.type
TERMINATE_SUCCESS = 0
TERMINATE_ABORTED = 1
TERMINATE_TIME_OUT = 2
TERMINATE_INVALID_NAV = 3
TERMINATE_INVALID_CMD = 4

RESULT_CODES: Dict[str, int] = {
    "TERMINATE_SUCCESS": TERMINATE_SUCCESS,
    "TERMINATE_ABORTED": TERMINATE_ABORTED,
    "TERMINATE_TIME_OUT": TERMINATE_TIME_OUT,
    "TERMINATE_INVALID_NAV": TERMINATE_INVALID_NAV,
    "TERMINATE_INVALID_CMD": TERMINATE_INVALID_CMD,
}


def mismatched_codes(defined: Mapping[str, Optional[int]]) -> List[str]:
    """訊息定義裡的常數（名稱 -> 值）與這裡照抄的不一樣的那些名稱；空清單代表一致。"""
    return sorted(name for name, value in RESULT_CODES.items() if defined.get(name) != value)


def move_outcome(action_status: str, result_type: Optional[int]) -> str:
    """`result_type` 是 CtlCommandResult.type；action 被拒絕或沒帶結果時是 None。"""
    if action_status == ACTION_TIMEOUT:
        return MOVE_TIMEOUT
    if action_status != ACTION_DONE or result_type is None:
        return MOVE_ABORTED
    if result_type == TERMINATE_SUCCESS:
        return MOVE_SUCCESS
    if result_type in (TERMINATE_INVALID_NAV, TERMINATE_INVALID_CMD):
        return MOVE_INVALID  # 再送一次也不會變合法
    if result_type == TERMINATE_TIME_OUT:
        return MOVE_TIMEOUT
    return MOVE_ABORTED
