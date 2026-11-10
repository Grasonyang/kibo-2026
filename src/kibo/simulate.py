"""本機的「資格賽」：跑很多場隨機場景，印出每場與平均的估計分數。

    uv run python -m kibo.simulate --runs 10 --checkpoints 8
    uv run python -m kibo.simulate --runs 10 --checkpoints 12 --fail 0.2 --noise 0.08 -v

分數是假裁判算的，只能相對比較策略，不能當真實成績。
"""

import argparse
import sys
from typing import List, Tuple

from kibo.fake_robot import CAMERA_FIX_MAX_M, FakeRobot, FakeRobotConfig, fake_config
from kibo.mission import DEFAULT_MISSION, MissionConfig, MissionReport, run_mission
from kibo.scenarios import random_checkpoints_message, valid_count


def run_once(
    seed: int, count: int, robot_cfg: FakeRobotConfig, mission_cfg: MissionConfig
) -> Tuple[FakeRobot, MissionReport]:
    robot = FakeRobot(random_checkpoints_message(count, seed), robot_cfg, seed)
    report = run_mission(robot, mission_cfg)
    return robot, report


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="本機的資格賽：跑隨機場景，印出估計分數。")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--checkpoints", type=int, default=8, help="含 Goal，規則是 6 到 12")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--noise", type=float, default=0.01, help="到點位置誤差標準差（公尺）")
    parser.add_argument("--fail", type=float, default=0.0, help="每次移動失敗的機率")
    parser.add_argument("--slowdown", type=float, default=1.0, help="假機器人實際比移動模型慢幾倍")
    parser.add_argument(
        "--camera", action="store_true", help="假機器人開相機，不穩時用 marker 修正"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="印出每場的 log")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if not valid_count(args.checkpoints):
        parser.error("--checkpoints must be between 2 and 12")

    robot_cfg = fake_config(args.noise, args.fail, args.slowdown, args.camera)
    scores = []
    for i in range(args.runs):
        mission_cfg = DEFAULT_MISSION._replace(
            camera_fix_max_m=CAMERA_FIX_MAX_M if args.camera else 0.0
        )
        robot, report = run_once(args.seed + i, args.checkpoints, robot_cfg, mission_cfg)
        score = robot.score()
        scores.append(score)
        print(
            "run %2d: score %6.1f  levels %s  dropped %s  goal %s  finished at %5.1fs%s"
            % (
                i + 1,
                score,
                robot.passed_levels,
                report.dropped,
                "yes" if report.goal_reached else "NO",
                report.elapsed_sec,
                "  aborted: " + report.aborted if report.aborted else "",
            )
        )
        if args.verbose:
            for line in robot.logs:
                print("    " + line)
    print("mean score over %d runs: %.1f" % (len(scores), sum(scores) / len(scores)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
