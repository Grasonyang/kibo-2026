"""到點穩定：IB2 已經在這個 CheckPoint 的容差內連續待滿 1 秒了嗎？

規則書 2.2.3 要求在餘裕內停 1 秒才算通過；官方每個點又只判第一次通知，所以「什麼時候送」
只有一次機會。這個模組只做一件事：一筆一筆吃姿態，記住「已經連續達標幾筆」。
任務邏輯負責拿姿態、看時鐘、決定要求幾級；這裡不碰機器人也不碰時鐘。

「穩定」= 連續達標至少 `samples` 筆。一筆沒達標就從頭數；同一個時間戳的資料只算一次
（導航沒更新時不能把同一筆讀五次）。姿態有兩種來源：

- `feed`：移動結束後即時讀到的姿態，一次一筆。每筆之間任務邏輯會等一個取樣間隔，
  所以 5 筆大約就是 1 秒；這裡只數筆數，不另外卡時間戳的跨度（時間戳有幾毫秒的抖動，
  卡「剛好 1.000 秒」會平白多等一筆，極端時等到逾時）。
- `feed_tail`：移動的尾段留下的導航紀錄。action 回報成功之前機器人通常已經停在目標上
  一秒多，這段紀錄夠格就不用再等。紀錄比即時取樣密得多，所以除了筆數還要求頭尾相隔
  `window_sec`、最新一筆夠新。它是全有全無：不夠格就當作什麼都沒看過，之後從頭數，
  不拿尾段的好樣本去湊。

`strict`：要求的是最高級（Lv3）時，另外要求三個量都在 Lv3 上限的 `notify_margin` 以內。
原因見 `docs/kibo/simulator-internals.md` 的 E8、E9：官方判定用的姿態比我們看到的舊，
Goal 點的滾轉讀數又會把小誤差放大，貼著上限回報很容易被判低一級。
"""

from typing import NamedTuple, Optional, Sequence

from kibo.checkpoints import Checkpoint
from kibo.geometry import Pose
from kibo.judge import Judgement, judge, top_band_usage


class SettleRule(NamedTuple):
    samples: int  # 連續達標至少幾筆
    window_sec: float  # 尾段紀錄的頭尾至少相隔幾秒（規則書的 1 秒）
    max_age_sec: float  # 尾段紀錄最新一筆比這舊，就不能代表現在
    notify_margin: float  # strict 時，三個量都要在 Lv3 上限的這個比例以內
    top_level: int  # 最高的通過等級；notify_margin 只在要求這一級時才有意義


class Steadiness(object):
    """一個 CheckPoint 上的連續達標紀錄。每到一個點建一個新的。"""

    def __init__(self, checkpoint: Checkpoint, rule: SettleRule) -> None:
        self._cp = checkpoint
        self._rule = rule
        self._count = 0  # 目前連續達標幾筆
        self._seen_stamp: Optional[float] = None  # 上一筆被判定的樣本，用來認出重複資料
        self.last: Optional[Judgement] = None  # 最後一次判定（重複資料不算）
        self.last_pose: Optional[Pose] = None  # 最後一次判定用的姿態
        self.tail_report = ""  # 上一次 feed_tail 為什麼沒過；過了或沒紀錄是空字串

    def _good_enough(self, judgement: Judgement, required_level: int, strict: bool) -> bool:
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
        self.last, self.last_pose = judgement, pose
        self._count = self._count + 1 if self._good_enough(judgement, required_level, strict) else 0
        return judgement

    def feed_tail(self, poses: Sequence[Pose], now: float, required_level: int) -> bool:
        """吃移動尾段的導航紀錄（舊的在前）。夠格就立刻穩定並回 True；否則從頭數並回 False。

        沒有時間戳的姿態不算數。尾段一律用 strict 的標準，因為夠格的話馬上就要送通知了。"""
        self.tail_report = ""
        stamped = [(p.stamp, p) for p in poses if p.stamp is not None]
        if not stamped:
            return False
        self._count = 0
        judgements = [judge(pose, self._cp) for _, pose in stamped]
        newest, oldest = stamped[-1][0], stamped[0][0]
        span, age = newest - oldest, now - newest
        long_and_fresh = (
            len(stamped) >= self._rule.samples
            and span >= self._rule.window_sec
            and age <= self._rule.max_age_sec
        )
        if long_and_fresh and all(self._good_enough(j, required_level, True) for j in judgements):
            self._count = len(stamped)
            self._seen_stamp = newest
            self.last, self.last_pose = judgements[-1], stamped[-1][1]
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

    @property
    def stable(self) -> bool:
        return self._count >= self._rule.samples
