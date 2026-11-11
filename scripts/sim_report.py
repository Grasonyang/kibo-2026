"""整理本機模擬器每一場的結果：官方評分、完成時間、每段腿的模型誤差。

    uv run python scripts/sim_report.py            # 全部場次
    uv run python scripts/sim_report.py --last 3   # 最近三場
    uv run python scripts/sim_report.py --legs     # 連每段腿都列

讀的是 `sim/krpc7th-simulator/share/logs/<時間戳>/`（位置同 scripts/_common.sh：
主 checkout 的 sim/，或環境變數 KIBO_SIM_ROOT）。沒有 result.json 的場次（評分模組
沒收到任務開始，或節點掛了，或還在跑）會標成「無成績」。

「版本」是那一場同步進模擬器的 commit（有未提交的改動時帶 +dirty），節點啟動時印在 log 裡；
戳記出現之前的場次是 `-`。模擬器自己啟動失敗的場次（docs/kibo/simulator-internals.md 的 E10：
機器人整場不受控）標成「模擬器啟動失敗」、不列數字：那一場的結果不代表我們的程式，統計時排除。
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

from kibo.buildstamp import find_build
from kibo.geometry import distance, quat_angle
from kibo.motion import rotation_seconds, translation_seconds

LEG_START = re.compile(r"\[t=([0-9.]+)[^\]]*\] route \[")
LEG_END = re.compile(r"\[t=([0-9.]+)[^\]]*\] move to #(\d+) attempt 1: (\w+)")
# 模擬器載入 IB2 模型失敗時 Gazebo 印在 system.log 的那一行（E10）。原文每段字之間夾著終端機的
# 顏色碼，比對前要先去掉。system.log 一場有幾百 MB，這一行在開機階段（實測在第 325 行、
# 約 14 KB 處），所以只看開頭一段。這是假設：那一行若出現在這一段之後，報表會把壞掉的場次當成
# 一般場次列出來，沒有任何訊號。看到「0 點、腿的誤差幾十秒」的場次，先自己去 system.log 找這一行。
SIM_FAILED = "Sensors failed to initialize when loading model[ib2]"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SYSTEM_LOG_HEAD_BYTES = 2 * 1024 * 1024


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


def _lines(path: str) -> List[str]:
    """檔案的每一行；讀不到就當作空的。"""
    try:
        with open(path, errors="replace") as f:
            return f.readlines()
    except OSError:
        return []


def simulator_failed(system_log: str) -> bool:
    """這一場是不是模擬器自己啟動失敗（E10）。讀不到 system.log 就當作不是。"""
    try:
        with open(system_log, "rb") as f:
            head = f.read(SYSTEM_LOG_HEAD_BYTES).decode("utf-8", "replace")
    except OSError:
        return False
    return SIM_FAILED in ANSI.sub("", head)


def read_run(path: str) -> Dict:
    run: Dict = {"name": os.path.basename(path), "legs": []}
    lines = _lines(os.path.join(path, "user_programs_logs", "user_program_output.log"))
    run["build"] = find_build(lines)
    run["sim_failed"] = simulator_failed(os.path.join(path, "judge_module_logs", "system.log"))
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
        "%-14s %-14s %-8s %7s %5s %8s  %s"
        % ("場", "版本", "難度", "通過", "Goal", "完成秒", "腿的誤差（實際-預測）")
    )
    for name in names:
        run = read_run(os.path.join(root, name))
        build, level = run["build"] or "-", run.get("level", "?")
        if run["sim_failed"]:
            print("%-14s %-14s %-8s 模擬器啟動失敗（E10），這一場不算" % (name, build, level))
            continue
        if "levels" not in run:
            print("%-14s %-14s %-8s 無成績" % (name, build, level))
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
            "%-14s %-14s %-8s %3d/%-3d %5s %8s  %s  %s"
            % (
                name,
                build,
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
