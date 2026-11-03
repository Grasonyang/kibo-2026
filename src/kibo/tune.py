"""參數掃描：同一批隨機場景，換不同的任務參數，看平均分與最低分。

    uv run python -m kibo.tune --runs 20 --checkpoints 10

資格賽取 10 次平均，一次爆掉影響很大，所以除了平均也看最低分。
分數來自假裁判，只能相對比較；拿到模擬器資料校正假機器人之後才有意義。
"""

import argparse
import sys
from typing import List, NamedTuple, Tuple

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
    ]


def robot_variants(base: FakeRobotConfig) -> List[Tuple[str, FakeRobotConfig]]:
    return [("沒相機", base), ("有相機", base._replace(camera=True))]


def evaluate(variant: Variant, runs: int, count: int, seed: int, robot_cfg: FakeRobotConfig):
    """回傳 {世界: 平均分} 與到 Goal 的場數。"""
    totals = {name: 0.0 for name in WORLD_NAMES}
    goals = 0
    for i in range(runs):
        robot = FakeRobot(random_checkpoints_message(count, seed + i), robot_cfg, seed + i)
        report = run_mission(robot, variant.config)
        for name in WORLD_NAMES:
            totals[name] += robot.score(WORLDS[name])
        goals += 1 if report.goal_reached else 0
    return {name: totals[name] / runs for name in WORLD_NAMES}, goals


def regret_table(rows):
    """rows: [(名稱, {世界: 平均}, goals)]。每格的後悔 = 該世界最好的變體 − 這個變體。"""
    best = {name: max(r[1][name] for r in rows) for name in WORLD_NAMES}
    return [
        (label, means, goals, max(best[n] - means[n] for n in WORLD_NAMES))
        for label, means, goals in rows
    ]


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
        rows = []
        for variant in variants():
            means, goals = evaluate(variant, args.runs, args.checkpoints, args.seed, cfg)
            rows.append((variant.name, means, goals))
        print("%-22s %7s %7s %7s %7s %7s %6s" % ("變體", *WORLD_NAMES, "最大後悔", "Goal"))
        for label, means, goals, regret in regret_table(rows):
            print(
                "%-22s %7.1f %7.1f %7.1f %7.1f %7.1f %3d/%d"
                % (label, *[means[n] for n in WORLD_NAMES], regret, goals, args.runs)
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
