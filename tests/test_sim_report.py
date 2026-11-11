"""scripts/sim_report.py：每場的版本看得到；模擬器自己啟動失敗的場次要標出來（issue #14）。"""

import importlib.util
import json
import os

import pytest

from kibo.buildstamp import build_line

ROOT = os.path.join(os.path.dirname(__file__), "..")
# 場次 20261111063731 的 system.log 第 325 行，原樣（Gazebo 在每一段字之間夾了終端機的顏色碼）。
E10 = (
    "\x1b[1;31m[Err] [Model.cc:1034] \x1b[0m\x1b[1;31mSensors failed to initialize when loading "
    "model[\x1b[0m\x1b[1;31mib2\x1b[0m\x1b[1;31m] via the factory mechanism.\x1b[0m\x1b[1;31m "
    "Plugins for the model will not be loaded.\n"
)
BOOT = "[ INFO] [1794379100.1]: Finished loading Gazebo ROS API Plugin.\n"  # 開機時的普通訊息


@pytest.fixture
def sim_report():
    spec = importlib.util.spec_from_file_location(
        "sim_report", os.path.join(ROOT, "scripts", "sim_report.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_run(logs, name, build=None, system_log="", passed=(3, 3)):
    """造一場的記錄目錄：兩個點（1 與 Goal 12），各自的等級是 passed。"""
    run = logs / name
    (run / "judge_module_logs").mkdir(parents=True)
    (run / "user_programs_logs").mkdir()
    cheat = {"Level": "normal", "Checkpoints": [{"checkpointid": 1}, {"checkpointid": 12}]}
    (run / "cheat_sheet.json").write_text(json.dumps(cheat))
    report = {
        "mission": {"duration_sec": 123.4},
        "goal": {"success": passed[1] > 0},
        "checkpoint_detail": [
            {"checkpoint_id": 1, "level": passed[0]},
            {"checkpoint_id": 12, "level": passed[1]},
        ],
    }
    (run / "judge_module_logs" / "result.json").write_text(json.dumps({"JudgeReport": report}))
    (run / "judge_module_logs" / "system.log").write_text(system_log)
    lines = ["[rosout][INFO] 2026-11-11 06:47:13,481: kibo user node ready\n"]
    if build is not None:
        lines.insert(0, "[rosout][INFO] 2026-11-11 06:47:13,470: " + build_line(build) + "\n")
    (run / "user_programs_logs" / "user_program_output.log").write_text("".join(lines))
    return str(run)


@pytest.fixture
def logs(tmp_path):
    folder = tmp_path / "krpc7th-simulator" / "share" / "logs"
    folder.mkdir(parents=True)
    return folder


def rows(sim_report, logs, capsys, monkeypatch):
    """跑報表，回傳 {場次: 那一列的文字}。"""
    monkeypatch.setenv("KIBO_SIM_ROOT", str(logs.parent.parent.parent))
    assert sim_report.main([]) == 0
    printed = capsys.readouterr().out.splitlines()
    return {line.split()[0]: line for line in printed[1:]}, printed[0]


def test_a_run_knows_which_build_it_flew(sim_report, logs):
    run = sim_report.read_run(make_run(logs, "20261111064600", build="a149a80+dirty"))
    assert run["build"] == "a149a80+dirty"


def test_a_run_from_before_the_stamp_existed_has_no_build(sim_report, logs):
    run = sim_report.read_run(make_run(logs, "20261110130057"))
    assert run["build"] is None


def test_the_report_has_a_column_for_the_build(sim_report, logs, capsys, monkeypatch):
    make_run(logs, "20261111064600", build="a149a80")
    make_run(logs, "20261110130057")
    by_run, header = rows(sim_report, logs, capsys, monkeypatch)
    assert "版本" in header
    assert "a149a80" in by_run["20261111064600"]
    assert "a149a80" not in by_run["20261110130057"]


def test_a_run_where_the_simulator_failed_to_start_is_flagged(sim_report, logs):
    # simulator-internals 的 E10：機器人整場不受控，這一場的數字不代表我們的程式。
    run = sim_report.read_run(make_run(logs, "20261111063731", system_log=E10, passed=(0, 0)))
    assert run["sim_failed"]
    assert not sim_report.read_run(make_run(logs, "20261111064600"))["sim_failed"]
    healthy = make_run(logs, "20261111013157", system_log=BOOT * 300)
    assert not sim_report.read_run(healthy)["sim_failed"]


def test_the_failure_is_found_among_the_boot_messages(sim_report, logs):
    # 真的 system.log 有幾百 MB，那一行在開頭（第 325 行、約 14 KB 處）。
    noisy = BOOT * 324 + E10 + BOOT * 5000
    run = sim_report.read_run(make_run(logs, "20261111063731", system_log=noisy, passed=(0, 0)))
    assert run["sim_failed"]


def test_the_report_shows_a_failed_simulator_instead_of_its_numbers(
    sim_report, logs, capsys, monkeypatch
):
    make_run(logs, "20261111063731", build="aee945c", system_log=E10, passed=(0, 0))
    make_run(logs, "20261111064600", build="aee945c")
    by_run, _ = rows(sim_report, logs, capsys, monkeypatch)
    assert "模擬器啟動失敗" in by_run["20261111063731"]
    assert "0/2" not in by_run["20261111063731"]  # 不印會被當成我們的成績的數字
    assert "aee945c" in by_run["20261111063731"]
    assert "2/2" in by_run["20261111064600"] and "模擬器啟動失敗" not in by_run["20261111064600"]
