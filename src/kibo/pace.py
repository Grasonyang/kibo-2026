"""節奏：機器人實際比移動模型慢幾倍？

只吃數字：每飛完一段腿，餵「這段多長、模型預測幾秒、實際幾秒」，隨時可以問現在的倍數。
任務邏輯（`kibo.mission`）拿這個倍數放大規劃用的秒數；這裡不知道姿態、路線或 log。

規則（council v1-review 的 R2、sim-bringup-review 的 S1）：

- 比的是全部腿加起來的「實際秒數 / 預測秒數」，不是最近一段。
- 預測秒數累積不夠就不下結論：一兩段腿的誤差太大。
- 很短的腿不算：一兩秒的誤差佔比太大。
- 慢超過死區才動，只往慢修，有上限；之後的腿把整體拉回死區內就回到照模型，不留棘輪。

模型在本機模擬器上每段腿只差一兩秒（docs/kibo/motion-model.md），所以這是保險：
Web 模擬器或實機若整體比較慢，規劃用的秒數會等比例放大。
"""

from typing import NamedTuple


class PaceRule(NamedTuple):
    enabled: bool = True  # 關掉就永遠照模型
    min_speed_ratio: float = 0.5  # 上限：最多當作比模型慢 1/0.5 = 2 倍
    # 死區：實測在模型的 1/0.9 = 1.11 倍以內不校正。原本是 1.25 倍；慢 20% 到 24% 落在裡面完全不修，
    # 15 秒的保險被吃光（council sim-bringup-review 的 S1）。
    below_ratio: float = 0.9
    min_leg_m: float = 0.5  # 只用這麼長以上的腿
    min_predicted_sec: float = 20.0  # 模型秒數累積到這麼多才下結論，一段腿不算數


DEFAULT_PACE = PaceRule()


class Pace(object):
    """一場任務的節奏紀錄。`predicted_sec`、`actual_sec` 是算數的那些腿的累積。"""

    def __init__(self, rule: PaceRule = DEFAULT_PACE) -> None:
        self.rule = rule
        self.predicted_sec = 0.0
        self.actual_sec = 0.0

    def add_leg(self, metres: float, predicted_sec: float, actual_sec: float) -> None:
        """一段飛完（或逾時）的腿。逾時的腿也可以餵：實際秒數至少是逾時值，
        算出來的倍數是下界，只會往慢修，方向安全。"""
        if not self.rule.enabled or metres < self.rule.min_leg_m:
            return
        self.predicted_sec += predicted_sec
        self.actual_sec += actual_sec

    def slowdown(self) -> float:
        """現在該當作比模型慢幾倍；1.0 = 照模型。不會小於 1。"""
        if self.predicted_sec <= 0.0 or self.predicted_sec < self.rule.min_predicted_sec:
            return 1.0
        slowdown = self.actual_sec / self.predicted_sec
        if slowdown <= 1.0 / self.rule.below_ratio:
            return 1.0
        return min(slowdown, 1.0 / self.rule.min_speed_ratio)
