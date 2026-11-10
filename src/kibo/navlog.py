"""導航紀錄：收進導航資料，回答「現在在哪」與「最近幾秒在哪」。純 Python，自己上鎖。

為什麼獨立成一個模組：導航大約 200 Hz 進來，任務邏輯卻只需要兩件事。要留多久、
留多密、多舊就不算數，這些規則以前散在 ROS 節點裡，本機沒有 ROS 就測不到，也真的錯過一次
（沒降頻時 64 筆只跨 0.33 秒，「到點前最後 1 秒」根本湊不滿）。

- `add` 每一筆都呼叫，便宜：大部分只更新「最新一筆」，隔 `step_sec` 才進紀錄。
- `latest` 是最新一筆，比 `fresh_sec` 舊就回 None（不假裝知道位置）。
- `recent` 是紀錄裡最近幾秒的姿態，舊的在前。
時間一律用導航資料自己的 stamp，與呼叫端給的 `now` 比。
"""

import collections
import threading
from typing import Deque, List, Optional

from kibo.geometry import Pose


class NavLog(object):
    def __init__(self, step_sec: float = 0.05, capacity: int = 64, fresh_sec: float = 1.0) -> None:
        """預設每 0.05 秒留一筆、留 64 筆（約 3 秒）；比 1 秒舊的資料不算數。"""
        self._step_sec = step_sec
        self._fresh_sec = fresh_sec
        self._lock = threading.Lock()
        self._kept: Deque[Pose] = collections.deque(maxlen=capacity)
        self._latest: Optional[Pose] = None
        self._first_stamp: Optional[float] = None
        self._count = 0

    def add(self, pose: Pose) -> None:
        """收進一筆。沒有 stamp 的不收；時間倒退（時鐘重設）就把舊紀錄清掉重來。"""
        stamp = pose.stamp
        if stamp is None:
            return
        with self._lock:
            newest = self._kept[-1].stamp if self._kept else None
            if newest is not None and stamp < newest:
                self._kept.clear()
                self._first_stamp = None
                self._count = 0
                newest = None
            self._latest = pose
            self._count += 1
            if self._first_stamp is None:
                self._first_stamp = stamp
            if newest is None or stamp - newest >= self._step_sec:
                self._kept.append(pose)

    def latest(self, now: float) -> Optional[Pose]:
        """最新一筆；沒有資料或比 fresh_sec 舊就回 None。"""
        with self._lock:
            pose = self._latest
        if pose is None or pose.stamp is None or now - pose.stamp > self._fresh_sec:
            return None
        return pose

    def recent(self, now: float, seconds: float) -> List[Pose]:
        """紀錄裡 stamp 在最近 seconds 秒內的姿態，舊的在前。"""
        oldest = now - seconds
        with self._lock:
            return [p for p in self._kept if p.stamp is not None and p.stamp >= oldest]

    @property
    def count(self) -> int:
        """總共收過幾筆（含沒進紀錄的）。"""
        with self._lock:
            return self._count

    def rate_hz(self) -> float:
        """從第一筆到最新一筆的平均頻率；不到兩筆回 0。"""
        with self._lock:
            latest, first, count = self._latest, self._first_stamp, self._count
        if latest is None or latest.stamp is None or first is None or count < 2:
            return 0.0
        span = latest.stamp - first
        return (count - 1) / span if span > 0.0 else 0.0
