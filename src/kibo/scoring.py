"""分數模型（假設值）。

規則書只說：Score = Pt_all × Mag_clear，Pt_all = 各 CheckPoint 依 Lv 的分數加 Goal 分數，
Mag_clear 依剩餘時間，最大約 2 倍。各 Lv 的點數與倍率曲線沒有公布。
這裡的數字是為了讓本機的策略比較有依據；拿到模擬器後用結果 JSON 校正。
"""

from typing import Dict, NamedTuple


class Scoring(NamedTuple):
    level_points: Dict[int, float]
    goal_points: float
    max_multiplier: float
    time_limit_sec: float

    def points_for_level(self, level: int) -> float:
        return self.level_points.get(level, 0.0)

    def multiplier(self, remaining_sec: float) -> float:
        """剩餘時間越多倍率越高，從 1 線性到 max_multiplier。"""
        fraction = max(0.0, min(1.0, remaining_sec / self.time_limit_sec))
        return 1.0 + (self.max_multiplier - 1.0) * fraction

    def total(self, levels, goal_reached: bool, remaining_sec: float) -> float:
        points = sum(self.points_for_level(lv) for lv in levels)
        if goal_reached:
            points += self.goal_points
        return points * self.multiplier(remaining_sec)


DEFAULT_SCORING = Scoring(
    level_points={3: 10.0, 2: 6.0, 1: 3.0},
    goal_points=20.0,
    max_multiplier=2.0,
    time_limit_sec=300.0,
)
