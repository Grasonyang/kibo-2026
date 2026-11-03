"""參數掃描：同一批隨機場景，換不同的任務參數，看平均分與最低分。

    uv run python -m kibo.tune --runs 20 --checkpoints 10

資格賽取 10 次平均，所以主要看平均；最低分與標準差用來抓「偶爾整場爆掉」。
四個規則世界並排、算最大後悔，只有名次跨世界不變的結論才算數。
分數來自假裁判，只能相對比較；拿到模擬器資料校正假機器人之後才有意義。
"""

import argparse
import sys
from typing import Dict, List, NamedTuple, Tuple

from kibo.fake_robot import FakeRobot, FakeRobotConfig
from kibo.mission import DEFAULT_MISSION, MissionConfig, run_mission
from kibo.scenarios import random_checkpoints_message
from kibo.scoring import WORLD_NAMES, WORLDS


class Variant(NamedTuple):
    name: str
    config: MissionConfig


def variants() -> List[Variant]:
    base = DEFAULT_MISSION
    budget = base.budget
    return [
        Variant("預設（保險 25s，穩定 8s）", base),
        Variant("不校正速度", base._replace(calibrate_speed=False)),
        Variant("保險 10s", base._replace(budget=budget._replace(margin_sec=10.0))),
        Variant("保險 45s", base._replace(budget=budget._replace(margin_sec=45.0))),
        Variant("穩定估 4s", base._replace(budget=budget._replace(settle_sec=4.0))),
        Variant("穩定估 12s", base._replace(budget=budget._replace(settle_sec=12.0))),
        Variant("只求 Lv2", base._replace(target_level=2)),
        Variant("趕時間門檻 90s", base._replace(hurry_sec=90.0)),
        Variant("不刪點（只做對照）", base._replace(budget=budget._replace(allow_drop=False))),
    ]


def robot_variants(base: FakeRobotConfig) -> List[Tuple[str, FakeRobotConfig]]:
    return [("沒相機", base), ("有相機", base._replace(camera=True))]


class Row(NamedTuple):
    label: str
    means: Dict[str, float]  # 世界 -> 平均
    worst: float  # 預設世界（B/T0）的最低分
    sd: float  # 預設世界的單場標準差
    goals: int


def evaluate(variant: Variant, runs: int, count: int, seed: int, robot_cfg: FakeRobotConfig) -> Row:
    totals = {name: 0.0 for name in WORLD_NAMES}
    default_scores: List[float] = []
    goals = 0
    for i in range(runs):
        robot = FakeRobot(random_checkpoints_message(count, seed + i), robot_cfg, seed + i)
        report = run_mission(robot, variant.config)
        for name in WORLD_NAMES:
            totals[name] += robot.score(WORLDS[name])
        default_scores.append(robot.score(WORLDS[WORLD_NAMES[0]]))
        goals += 1 if report.goal_reached else 0
    mean = sum(default_scores) / runs
    sd = (sum((s - mean) ** 2 for s in default_scores) / max(runs - 1, 1)) ** 0.5
    return Row(
        variant.name, {n: totals[n] / runs for n in WORLD_NAMES}, min(default_scores), sd, goals
    )


def max_regret(rows: List[Row]) -> Dict[str, float]:
    """每個變體在最不利的世界裡比該世界最好的變體差幾分。"""
    best = {name: max(r.means[name] for r in rows) for name in WORLD_NAMES}
    return {r.label: max(best[n] - r.means[n] for n in WORLD_NAMES) for r in rows}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="掃描任務參數，印出四個規則世界的平均分與最大後悔。"
    )
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--checkpoints", type=int, default=10)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--noise", type=float, default=0.05)
    parser.add_argument("--fail", type=float, default=0.1)
    parser.add_argument("--speed", type=float, default=0.1, help="假機器人的真實線速度（m/s）")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if not 2 <= args.checkpoints <= 12:
        parser.error("--checkpoints must be between 2 and 12")

    base = FakeRobotConfig()
    robot_cfg = base._replace(
        position_noise_m=args.noise,
        move_fail_prob=args.fail,
        speeds=base.speeds._replace(linear_mps=args.speed),
    )
    print(
        "%d 場、%d 點、誤差 %.2fm、失敗率 %.0f%%、真速 %.2fm/s（規劃假設 %.2f）"
        % (
            args.runs,
            args.checkpoints,
            args.noise,
            args.fail * 100,
            args.speed,
            DEFAULT_MISSION.budget.speeds.linear_mps,
        )
    )
    print(
        "世界：A=Goal 需全部通過，B=只需 Goal 點；T0=逾時整場 0，T1=逾時保留已得分。"
        "只有四欄名次都不變的結論才算數。"
    )
    for robot_name, cfg in robot_variants(robot_cfg):
        print("--- %s ---" % robot_name)
        rows = [evaluate(v, args.runs, args.checkpoints, args.seed, cfg) for v in variants()]
        regret = max_regret(rows)
        print(
            "%-22s %7s %7s %7s %7s %7s %6s %5s %6s"
            % ("變體", *WORLD_NAMES, "最大後悔", "最低", "sd", "Goal")
        )
        for r in rows:
            print(
                "%-22s %7.1f %7.1f %7.1f %7.1f %7.1f %6.1f %5.1f %3d/%d"
                % (
                    r.label,
                    *[r.means[n] for n in WORLD_NAMES],
                    regret[r.label],
                    r.worst,
                    r.sd,
                    r.goals,
                    args.runs,
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
