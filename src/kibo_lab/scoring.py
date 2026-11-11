"""分數模型（假設值）。

規則書只說：Score = Pt_all × Mag_clear，Pt_all = 各 CheckPoint 依 Lv 的分數加 Goal 分數，
Mag_clear 依剩餘時間，最大約 2 倍。各 Lv 的點數與倍率曲線沒有公布。
這裡的數字是為了讓本機的策略比較有依據；拿到模擬器後用結果 JSON 校正。
"""

from typing import Dict, NamedTuple

from kibo.field import TIME_LIMIT_SEC


class Scoring(NamedTuple):
    level_points: Dict[int, float]
    goal_points: float
    max_multiplier: float
    time_limit_sec: float
    # 規則書沒講清楚的兩件事，各做成開關（council v1-review R3）：
    goal_requires_all: bool = False  # A：Goal 分數要求通過全部 CheckPoint；B：只要 Goal 點通過
    timeout_keeps_points: bool = False  # T1：逾時仍保留已得的 CheckPoint 分；T0：整場 0

    def points_for_level(self, level: int) -> float:
        return self.level_points.get(level, 0.0)

    def multiplier(self, remaining_sec: float) -> float:
        """剩餘時間越多倍率越高，從 1 線性到 max_multiplier。"""
        fraction = max(0.0, min(1.0, remaining_sec / self.time_limit_sec))
        return 1.0 + (self.max_multiplier - 1.0) * fraction

    def total(
        self,
        levels,
        goal_reached: bool,
        remaining_sec: float,
        all_passed: bool = True,
        late: bool = False,
    ) -> float:
        """`late` 是沒在時限內完成回報；`all_passed` 是每個 CheckPoint 都通過了。"""
        if late and not self.timeout_keeps_points:
            return 0.0
        points = sum(self.points_for_level(lv) for lv in levels)
        goal_counts = goal_reached and not late and (all_passed or not self.goal_requires_all)
        if goal_counts:
            points += self.goal_points
        return points * self.multiplier(0.0 if late else remaining_sec)


DEFAULT_SCORING = Scoring(
    level_points={3: 10.0, 2: 6.0, 1: 3.0},
    goal_points=20.0,
    max_multiplier=2.0,
    time_limit_sec=float(TIME_LIMIT_SEC),
)

# 四個「規則世界」。哪一個是真的，要拿到模擬器用兩場探針才知道（ros/README.md）。
WORLDS = {
    "B/T0": DEFAULT_SCORING,
    "B/T1": DEFAULT_SCORING._replace(timeout_keeps_points=True),
    "A/T0": DEFAULT_SCORING._replace(goal_requires_all=True),
    "A/T1": DEFAULT_SCORING._replace(goal_requires_all=True, timeout_keeps_points=True),
}
WORLD_NAMES = ("B/T0", "B/T1", "A/T0", "A/T1")
