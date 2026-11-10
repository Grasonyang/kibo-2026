"""整理本機模擬器每一場的結果：官方評分、完成時間、每段腿的模型誤差。

    uv run python scripts/sim_report.py            # 全部場次
    uv run python scripts/sim_report.py --last 3   # 最近三場
    uv run python scripts/sim_report.py --legs     # 連每段腿都列

讀的是 `sim/krpc7th-simulator/share/logs/<時間戳>/`（位置同 scripts/_common.sh：
主 checkout 的 sim/，或環境變數 KIBO_SIM_ROOT）。沒有 result.json 的場次（評分模組
沒收到任務開始，或節點掛了，或還在跑）會標成「無成績」。
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

from kibo.geometry import distance, quat_angle
from kibo.motion import rotation_seconds, translation_seconds

LEG_START = re.compile(r"\[t=([0-9.]+)[^\]]*\] route \[")
LEG_END = re.compile(r"\[t=([0-9.]+)[^\]]*\] move to #(\d+) attempt 1: (\w+)")


def logs_root() -> str:
    root = os.environ.get("KIBO_SIM_ROOT")
    if not root:
        here = os.path.dirname(os.path.abspath(__file__))
        listing = subprocess.run(
            ["git", "-C", here, "worktree", "list", "--porcelain"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        ).stdout
        main = listing.splitlines()[0][len("worktree ") :] if listing else os.path.dirname(here)
        root = os.path.join(main, "sim")
    return os.path.join(root, "krpc7th-simulator", "share", "logs")


def _seconds(stamp: str) -> float:
    """評分模組的時間戳 'YYYYMMDD HHMMSSmmm'（模擬時鐘，從 1970 起算）。"""
    return (
        int(stamp[9:11]) * 3600
        + int(stamp[11:13]) * 60
        + int(stamp[13:15])
        + int(stamp[15:18]) / 1e3
    )


def read_run(path: str) -> Dict:
    run: Dict = {"name": os.path.basename(path), "legs": []}
    try:
        with open(os.path.join(path, "cheat_sheet.json")) as f:
            cheat = json.load(f)
    except (OSError, ValueError):
        return run
    checkpoints = {c["checkpointid"]: c for c in cheat["Checkpoints"]}
    run["level"] = cheat.get("Level", "?")
    run["count"] = len(checkpoints)
    try:
        with open(os.path.join(path, "judge_module_logs", "result.json")) as f:
            report = json.load(f)["JudgeReport"]
    except (OSError, ValueError, KeyError):
        return run
    mission = report["mission"]
    run["duration"] = mission.get("duration_sec")
    run["goal"] = bool(report["goal"]["success"])
    run["levels"] = {d["checkpoint_id"]: d["level"] for d in report["checkpoint_detail"]}
    if not mission.get("start"):
        return run
    t_start = _seconds(mission["start"])
    try:
        with open(os.path.join(path, "judge_module_logs", "localization_history.txt")) as f:
            history = [json.loads(line) for line in f]
        with open(
            os.path.join(path, "user_programs_logs", "user_program_output.log"), errors="replace"
        ) as f:
            lines = f.readlines()
    except (OSError, ValueError):
        return run
    if not history:
        return run

    def pose_at(t: float) -> Optional[Tuple[tuple, tuple]]:
        index = max(0, min(len(history) - 1, int(round((t - t_start) / 0.1))))
        sample = history[index]
        if not sample.get("position"):
            return None
        return tuple(sample["position"]), tuple(sample["orientation"])

    started: Optional[float] = None
    for line in lines:
        m = LEG_START.search(line)
        if m:
            started = float(m.group(1))
        m = LEG_END.search(line)
        if m and started is not None:
            cp = checkpoints.get(int(m.group(2)))
            pose = pose_at(started)
            if cp and pose:
                target, attitude = tuple(cp["position"]), tuple(cp["attitude"]["quaternion"])
                predicted = translation_seconds(pose[0], pose[1], target) + rotation_seconds(
                    pose[1], attitude
                )
                run["legs"].append(
                    {
                        "cp": int(m.group(2)),
                        "metres": distance(pose[0], target),
                        "degrees": quat_angle(pose[1], attitude),
                        "predicted": predicted,
                        "actual": float(m.group(1)) - started,
                        "result": m.group(3),
                    }
                )
            started = None
    return run


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="整理本機模擬器每一場的結果。")
    parser.add_argument("--last", type=int, default=0, help="只看最近幾場")
    parser.add_argument("--legs", action="store_true", help="列出每段腿")
    args = parser.parse_args(argv)
    root = logs_root()
    try:
        names = sorted(n for n in os.listdir(root) if re.match(r"^\d{14}$", n))
    except OSError:
        print("找不到 %s" % root)
        return 1
    if args.last > 0:
        names = names[-args.last :]
    print(
        "%-14s %-8s %7s %5s %8s  %s"
        % ("場", "難度", "通過", "Goal", "完成秒", "腿的誤差（實際-預測）")
    )
    for name in names:
        run = read_run(os.path.join(root, name))
        if "levels" not in run:
            print("%-14s %-8s 無成績" % (name, run.get("level", "?")))
            continue
        levels = run["levels"]
        passed = [lv for lv in levels.values() if lv > 0]
        all_three = "全 Lv3" if passed and all(lv == 3 for lv in passed) else str(sorted(passed))
        errors = [leg["actual"] - leg["predicted"] for leg in run["legs"]]
        summary = ""
        if errors:
            mean = sum(errors) / len(errors)
            sd = math.sqrt(sum((e - mean) ** 2 for e in errors) / len(errors))
            summary = "%+.2f ± %.2f s（%d 段）" % (mean, sd, len(errors))
        print(
            "%-14s %-8s %3d/%-3d %5s %8s  %s  %s"
            % (
                name,
                run["level"],
                len(passed),
                run["count"],
                "到" if run["goal"] else "沒到",
                "%.1f" % run["duration"] if run["duration"] is not None else "-",
                summary,
                all_three,
            )
        )
        if args.legs:
            for leg in run["legs"]:
                print(
                    "    #%-2d %5.2f m %5.0f°  預測 %5.1f  實際 %5.1f  %+5.1f %s"
                    % (
                        leg["cp"],
                        leg["metres"],
                        leg["degrees"],
                        leg["predicted"],
                        leg["actual"],
                        leg["actual"] - leg["predicted"],
                        "" if leg["result"] == "success" else leg["result"],
                    )
                )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
