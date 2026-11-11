"""kibo_lab.tune 的純函式：四世界的最大後悔。"""

from kibo_lab.scoring import WORLD_NAMES, WORLDS
from kibo_lab.tune import Row, max_regret


def row(label, b0, b1, a0, a1):
    return Row(label, {"B/T0": b0, "B/T1": b1, "A/T0": a0, "A/T1": a1}, 0.0, 0.0, 0)


def test_max_regret_is_the_worst_gap_to_the_best_variant_in_any_world():
    rows = [row("x", 100, 100, 80, 80), row("y", 90, 110, 85, 70)]
    regret = max_regret(rows)
    # x 在 B/T1 輸 10；y 在 B/T0 輸 10、A/T1 輸 10
    assert regret == {"x": 10.0, "y": 10.0}


def test_a_variant_best_everywhere_has_zero_regret():
    rows = [row("best", 100, 100, 100, 100), row("worse", 50, 60, 70, 80)]
    assert max_regret(rows)["best"] == 0.0
    assert max_regret(rows)["worse"] == 50.0


def test_world_names_match_the_world_table():
    assert set(WORLD_NAMES) == set(WORLDS)
