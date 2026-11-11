"""程式版本的戳記：這一場跑的是哪一個 commit？

`scripts/_common.sh` 的 `sync_user` 每次同步時在節點旁邊寫一個 `build_stamp.txt`，內容是一個字：
commit 的短雜湊，工作目錄有未提交的改動時後面多 `+dirty`。節點啟動時把它印成一行，
`scripts/sim_report.py` 再從 log 讀回來。這一行的格式只在這個檔案裡定義，寫的與讀的共用。

讀不到就是 `unknown`：戳記只是記錄，不能讓任務因此出事。
"""

import re
from typing import Iterable, Optional

STAMP_FILE = "build_stamp.txt"
UNKNOWN = "unknown"

_STAMP = re.compile(r"[0-9A-Za-z+._-]{1,40}")
_LINE = re.compile(r"\bbuild: ([0-9A-Za-z+._-]{1,40})")
_MAX_CHARS = 200  # 只讀第一行的開頭；檔案再怪也不多讀


def read_build_stamp(path: str) -> str:
    """戳記檔第一行的第一個字；檔案不在、讀不了、那個字不像戳記（有別的符號、超過 40 個字元）
    都回 UNKNOWN，不丟例外。"""
    try:
        with open(path, encoding="utf-8") as stamp_file:
            words = stamp_file.readline(_MAX_CHARS).split()
    except (OSError, ValueError):  # ValueError 包含解碼失敗
        return UNKNOWN
    if not words:
        return UNKNOWN
    return words[0] if _STAMP.fullmatch(words[0]) else UNKNOWN


def build_line(stamp: str) -> str:
    """節點啟動時印的那一行。"""
    return "build: %s" % stamp


def find_build(lines: Iterable[str]) -> Optional[str]:
    """從節點的 log 找回戳記；沒有那一行（戳記出現之前的場次）回 None。"""
    for line in lines:
        found = _LINE.search(line)
        if found:
            return found.group(1)
    return None
