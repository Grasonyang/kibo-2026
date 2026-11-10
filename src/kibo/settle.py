"""到點穩定：IB2 已經在這個 CheckPoint 的容差內連續待滿 1 秒了嗎？

規則書 2.2.3 要求在餘裕內停 1 秒才算通過；官方每個點又只判第一次通知，所以「什麼時候送」
只有一次機會。這個模組只做一件事：一筆一筆吃有時間戳的姿態，記住「已經連續達標多久」。
任務邏輯負責拿姿態、看時鐘、決定要求幾級；這裡不碰機器人也不碰時鐘。

「穩定」的定義只有一個，兩種來源共用：
- 連續達標的樣本至少 `samples` 筆，而且頭尾的時間戳相隔至少 `window_sec`。
- 一筆沒達標，就從頭數。同一個時間戳的資料只算一次（導航沒更新時不能把同一筆讀五次）。

兩種來源：
- `feed`：移動結束後即時讀到的姿態，一次一筆。
- `feed_tail`：移動的尾段留下的導航紀錄。action 回報成功之前機器人通常已經停在目標上一秒多，
  這段紀錄夠格就不用再等。它是全有全無：整段不夠格（太舊、太短、有一筆沒達標）就當作
  什麼都沒看過，之後從頭數滿，不拿尾段的好樣本去湊。

`strict`：要求的是最高級（Lv3）時，另外要求三個量都在 Lv3 上限的 `notify_margin` 以內。
原因見 `docs/kibo/simulator-internals.md` 的 E8、E9：官方判定用的姿態比我們看到的舊，
Goal 點的滾轉讀數又會把小誤差放大，貼著上限回報很容易被判低一級。
"""

from typing import List, NamedTuple, Optional, Sequence

from kibo.checkpoints import Checkpoint
from kibo.geometry import Pose
from kibo.judge import Judgement, judge, top_band_usage


class SettleRule(NamedTuple):
    samples: int = 5  # 連續達標至少幾筆
    window_sec: float = 1.0  # 頭尾至少相隔幾秒（規則書的 1 秒）
    max_age_sec: float = 0.25  # 尾段紀錄最新一筆比這舊，就不能代表現在
    notify_margin: float = 0.8  # strict 時，三個量都要在 Lv3 上限的這個比例以內
    top_level: int = 3  # 最高的通過等級；notify_margin 只在要求這一級時才有意義


DEFAULT_RULE = SettleRule()


class Steadiness(object):
    """一個 CheckPoint 上的連續達標紀錄。每到一個點建一個新的。"""

    def __init__(self, checkpoint: Checkpoint, rule: SettleRule = DEFAULT_RULE) -> None:
        self._cp = checkpoint
        self._rule = rule
        self._count = 0  # 目前連續達標幾筆
        self._first_stamp: Optional[float] = None  # 這一串的第一筆
        self._newest_stamp: Optional[float] = None  # 這一串的最新一筆
        self._unstamped = False  # 這一串裡有沒有時間戳的樣本（那就只能數筆數）
        self._seen_stamp: Optional[float] = None  # 上一筆被判定的樣本，用來認出重複資料
        self.last: Optional[Judgement] = None  # 最後一次判定（重複資料不算）
        self.tail_report = ""  # 上一次 feed_tail 為什麼沒過；過了或沒紀錄是空字串

    def good_enough(self, judgement: Judgement, required_level: int, strict: bool) -> bool:
        """這一筆判定夠不夠格算進連續達標。"""
        if judgement.level < required_level:
            return False
        if strict and required_level >= self._rule.top_level:
            return top_band_usage(judgement, self._cp) <= self._rule.notify_margin
        return True

    def feed(self, pose: Pose, required_level: int, strict: bool) -> Optional[Judgement]:
        """吃一筆即時姿態，回傳它的判定；與上一筆同一個時間戳的資料不判，回 None。"""
        if pose.stamp is not None and pose.stamp == self._seen_stamp:
            return None
        self._seen_stamp = pose.stamp
        judgement = judge(pose, self._cp)
        self.last = judgement
        if not self.good_enough(judgement, required_level, strict):
            self.reset()
            return judgement
        if self._count == 0:
            self._first_stamp = pose.stamp
            self._unstamped = False
        if pose.stamp is None:
            self._unstamped = True
        self._count += 1
        self._newest_stamp = pose.stamp
        return judgement

    def feed_tail(self, poses: Sequence[Pose], now: float, required_level: int) -> bool:
        """吃移動尾段的導航紀錄（舊的在前）。夠格就立刻穩定並回 True；否則清空並回 False。

        尾段一律用 strict 的標準，因為夠格的話馬上就要送通知了。"""
        self.tail_report = ""
        stamped: List[Pose] = [p for p in poses if p.stamp is not None]
        if not stamped:
            return False
        self.reset()
        judgements = [judge(pose, self._cp) for pose in stamped]
        newest, oldest = stamped[-1].stamp, stamped[0].stamp
        span = newest - oldest if newest is not None and oldest is not None else 0.0
        age = now - newest if newest is not None else float("inf")
        fresh_and_long_enough = (
            len(stamped) >= self._rule.samples
            and span >= self._rule.window_sec
            and age <= self._rule.max_age_sec
        )
        if fresh_and_long_enough and all(
            self.good_enough(j, required_level, True) for j in judgements
        ):
            self._count = len(stamped)
            self._first_stamp, self._newest_stamp = oldest, newest
            self._seen_stamp = newest
            self.last = judgements[-1]
            return True
        self.tail_report = (
            "%d samples over %.2fs, newest %.2fs old, worst Lv%d, used %.0f%% of the Lv3 margin"
            % (
                len(stamped),
                span,
                age,
                min(j.level for j in judgements),
                max(top_band_usage(j, self._cp) for j in judgements) * 100.0,
            )
        )
        return False

    def reset(self) -> None:
        """從頭數。最後一次判定與「上一筆看過的資料」留著。"""
        self._count = 0
        self._first_stamp = None
        self._newest_stamp = None
        self._unstamped = False

    @property
    def stable(self) -> bool:
        if self._count < self._rule.samples:
            return False
        if self._unstamped or self._first_stamp is None or self._newest_stamp is None:
            return True  # 沒有時間戳可比，只能相信筆數（每筆之間呼叫端有等）
        return self._newest_stamp - self._first_stamp >= self._rule.window_sec
