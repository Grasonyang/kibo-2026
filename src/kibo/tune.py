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


class Variant(NamedTuple):
    name: str
    config: MissionConfig


def variants() -> List[Variant]:
    base = DEFAULT_MISSION
    budget = base.budget
    return [
        Variant("預設（保險 25s，穩定 8s）", base),
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
    scores = []
    goals = 0
    for i in range(runs):
        robot = FakeRobot(random_checkpoints_message(count, seed + i), robot_cfg, seed + i)
        report = run_mission(robot, variant.config)
        scores.append(robot.score())
        goals += 1 if report.goal_reached else 0
    return sum(scores) / len(scores), min(scores), goals


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="掃描任務參數，印出平均分與最低分。")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--checkpoints", type=int, default=10)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--noise", type=float, default=0.05)
    parser.add_argument("--fail", type=float, default=0.1)
    parser.add_argument("--speed", type=float, default=0.1)
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
        "%d 場、%d 點、誤差 %.2fm、失敗率 %.0f%%、速度 %.2fm/s"
        % (args.runs, args.checkpoints, args.noise, args.fail * 100, args.speed)
    )
    for robot_name, cfg in robot_variants(robot_cfg):
        print("--- %s ---" % robot_name)
        print("%-26s %8s %8s %6s" % ("變體", "平均", "最低", "到 Goal"))
        for variant in variants():
            mean, worst, goals = evaluate(variant, args.runs, args.checkpoints, args.seed, cfg)
            print("%-26s %8.1f %8.1f %3d/%d" % (variant.name, mean, worst, goals, args.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
