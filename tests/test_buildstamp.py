"""程式版本的戳記（issue #14）：每場模擬要看得出跑的是哪一版程式。

`scripts/_common.sh` 的 `sync_user` 寫一個小檔，節點啟動時印一行，`scripts/sim_report.py` 讀回來。
"""

import os
import shutil
import subprocess
import tarfile

import pytest

from kibo.buildstamp import UNKNOWN, build_line, find_build, read_build_stamp

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_the_stamp_is_the_first_line_of_the_file(tmp_path):
    stamp = tmp_path / "build_stamp.txt"
    stamp.write_text("a149a80+dirty\n之後的東西不看\n")
    assert read_build_stamp(str(stamp)) == "a149a80+dirty"


def test_a_missing_stamp_file_reads_as_unknown_instead_of_failing(tmp_path):
    assert read_build_stamp(str(tmp_path / "nowhere.txt")) == UNKNOWN


def test_an_empty_or_unreadable_stamp_reads_as_unknown(tmp_path):
    empty = tmp_path / "build_stamp.txt"
    empty.write_text("\n")
    assert read_build_stamp(str(empty)) == UNKNOWN
    assert read_build_stamp(str(tmp_path)) == UNKNOWN  # 是目錄，不是檔案
    binary = tmp_path / "binary.txt"
    binary.write_bytes(b"\xff\xfe\x00garbage")
    assert read_build_stamp(str(binary)) == UNKNOWN


def test_a_stamp_is_one_short_word_whatever_the_file_holds(tmp_path):
    odd = tmp_path / "build_stamp.txt"
    odd.write_text("abc1234 with spaces and more " + "x" * 500)
    assert read_build_stamp(str(odd)) == "abc1234"


@pytest.mark.parametrize("content", ["abc1234!!!x\n", "x" * 41 + "\n", "a%sb\n", "\ufeffabc1234\n"])
def test_a_first_word_that_does_not_look_like_a_stamp_reads_as_unknown(tmp_path, content):
    # 不截一段來用：戳記要嘛整個可信，要嘛不知道。% 之類的符號也不能進 log 的格式字串。
    odd = tmp_path / "build_stamp.txt"
    odd.write_text(content, encoding="utf-8")
    assert read_build_stamp(str(odd)) == UNKNOWN


def test_the_line_the_node_logs_can_be_found_again_in_the_log():
    log = [
        "[rosout][INFO] 2026-11-11 06:47:13,470: " + build_line("a149a80+dirty") + "\n",
        "[rosout][INFO] 2026-11-11 06:47:13,481: kibo user node ready\n",
    ]
    assert find_build(log) == "a149a80+dirty"
    assert find_build(log[1:]) is None
    assert find_build([build_line(UNKNOWN)]) == UNKNOWN


# ---- 同步時寫下版本 ----


def _git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        + ["-c", "commit.gpgsign=false"]  # 使用者全域開了簽章也不要在測試裡簽
        + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert done.returncode == 0, done.stdout
    return done.stdout.strip()


def _packed_stamp(repo, tmp_path, name):
    """在 repo 裡跑 pack.sh，回傳包裡 build_stamp.txt 的內容。"""
    env = dict(os.environ, KIBO_SIM_ROOT=str(tmp_path / "sim"), KIBO_DIST_DIR=str(tmp_path / "out"))
    done = subprocess.run(
        ["bash", str(repo / "scripts" / "pack.sh"), name],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert done.returncode == 0, done.stdout
    with tarfile.open(str(tmp_path / "out" / (name + ".tar.gz"))) as archive:
        member = archive.extractfile("catkin_ws/src/krpc_user/scripts/build_stamp.txt")
        assert member is not None
        return member.read().decode().strip(), done.stdout


def test_syncing_writes_the_commit_and_whether_the_tree_was_clean(tmp_path):
    if shutil.which("rsync") is None or shutil.which("git") is None:
        pytest.skip("需要 rsync 與 git")
    # 一個只有同步用得到的東西的小 repo，這樣才能自己決定它乾不乾淨。
    repo = tmp_path / "repo"
    for folder in ("scripts", "krpc_user", "ros", os.path.join("src", "kibo")):
        shutil.copytree(
            os.path.join(ROOT, folder),
            str(repo / folder),
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    (tmp_path / "sim" / "krpc7th-simulator" / "users" / "catkin_ws" / "src").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    commit = _git(repo, "rev-parse", "--short", "HEAD")

    stamp, output = _packed_stamp(repo, tmp_path, "Clean")
    assert stamp == commit
    assert "未提交" not in output

    (repo / "src" / "kibo" / "brand_new.py").write_text("# 新檔，還沒 git add\n")
    stamp, _ = _packed_stamp(repo, tmp_path, "Untracked")
    assert stamp == commit + "+dirty"
    (repo / "src" / "kibo" / "brand_new.py").unlink()

    (repo / "ros" / "user_node.py").write_text("# 改了沒提交\n")
    stamp, output = _packed_stamp(repo, tmp_path, "Dirty")
    assert stamp == commit + "+dirty"
    assert "未提交" in output  # 打包時要提醒：這一包對不回任何一個 commit
