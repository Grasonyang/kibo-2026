"""scripts/check.sh：任何一個檢查失敗，腳本就要以非 0 結束，不能印「全部通過」。

用一個假的 `uv` 放在 PATH 最前面：參數含指定字串時失敗，其他都成功。這樣不會真的跑檢查
（也不會在 pytest 裡再跑一次 pytest），只驗證腳本怎麼處理每一步的結束碼。
"""

import os
import stat
import subprocess

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..")
FAKE_UV = """#!/usr/bin/env bash
case "$*" in *"$FAIL_ON"*) exit 1 ;; esac
exit 0
"""
STEPS = ["sync", "ruff format", "ruff check", "pyright", "vermin", "pytest"]


def run_check(tmp_path, fail_on):
    fake = tmp_path / "uv"
    fake.write_text(FAKE_UV)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH="%s%s%s" % (tmp_path, os.pathsep, os.environ["PATH"]))
    env["FAIL_ON"] = fail_on
    return subprocess.run(
        ["bash", os.path.join(REPO, "scripts", "check.sh")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        timeout=60,
    )


def test_it_passes_when_every_step_passes(tmp_path):
    done = run_check(tmp_path, "no step contains this")
    assert done.returncode == 0
    assert "全部通過" in done.stdout


@pytest.mark.parametrize("step", STEPS)
def test_it_fails_when_any_one_step_fails(tmp_path, step):
    # ruff check 與 pyright 曾經失敗了也照樣印「全部通過」：它們和 vermin 用 && 串在同一行，
    # set -e 不管串接裡不是最後一個的指令。
    done = run_check(tmp_path, step)
    assert done.returncode != 0
    assert "全部通過" not in done.stdout
