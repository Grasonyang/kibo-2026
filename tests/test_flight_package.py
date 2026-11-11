"""提交包只帶飛行需要的東西（council sim-bringup-review 的 S2、issue #5）。

決賽程式要給 JAXA 審查；假機器人、假分數表、參數掃描這些本機實驗用的模組不該跟著去。
結構上的保證：`scripts/_common.sh` 的 `sync_user` 把整個 `src/kibo/` 送進提交包，
所以 `src/kibo/` 裡只能有節點真的用得到的模組，開發用的放 `src/kibo_lab/`。
"""

import ast
import os
import shutil
import subprocess
import tarfile

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
FLIGHT = os.path.join(ROOT, "src", "kibo")
NODE = os.path.join(ROOT, "ros")


def _python_files(folder):
    return sorted(name for name in os.listdir(folder) if name.endswith(".py"))


def _imports(path):
    """這個檔案匯入的模組名稱（`import a.b`、`from a.b import c` 都回 "a.b"）。"""
    with open(path, encoding="utf-8") as source:
        tree = ast.parse(source.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update("%s.%s" % (node.module, alias.name) for alias in node.names)
    return names


def _flight_modules_used_by_the_node():
    """從 ros/ 的每個檔案出發，沿著 import 走得到的 kibo 模組。"""
    todo = [os.path.join(NODE, name) for name in _python_files(NODE)]
    reached = set()
    while todo:
        for name in _imports(todo.pop()):
            parts = name.split(".")
            if parts[0] != "kibo" or len(parts) < 2 or parts[1] in reached:
                continue
            path = os.path.join(FLIGHT, parts[1] + ".py")
            if os.path.exists(path):
                reached.add(parts[1])
                todo.append(path)
    return reached


def test_every_module_in_the_flight_package_is_used_by_the_node():
    # 節點用不到的模組躺在 src/kibo/ 裡，就會被送去審查：搬去 src/kibo_lab/，或真的用上它。
    in_package = {name[:-3] for name in _python_files(FLIGHT)} - {"__init__"}
    assert in_package - _flight_modules_used_by_the_node() == set()


def test_flight_code_never_imports_the_lab():
    for folder in (FLIGHT, NODE):
        for name in _python_files(folder):
            imported = _imports(os.path.join(folder, name))
            assert not any(module.split(".")[0] == "kibo_lab" for module in imported), name


def test_the_submission_package_has_the_node_the_flight_modules_and_nothing_else(tmp_path):
    if shutil.which("rsync") is None:
        pytest.skip("scripts/pack.sh 需要 rsync")
    # 假的模擬器目錄：裡面有上一版同步進去的開發用模組，還有容器留下的 .pyc。
    scripts = tmp_path / "sim" / "krpc7th-simulator" / "users" / "catkin_ws" / "src"
    scripts = scripts / "krpc_user" / "scripts"
    (scripts / "kibo" / "__pycache__").mkdir(parents=True)
    (scripts / "kibo" / "__pycache__" / "mission.cpython-36.pyc").write_bytes(b"stale")
    (scripts / "kibo" / "fake_robot.py").write_text("# 上一版留下的\n")
    (scripts / "__pycache__").mkdir()
    (scripts / "__pycache__" / "start_watch.cpython-36.pyc").write_bytes(b"stale")
    env = dict(os.environ, KIBO_SIM_ROOT=str(tmp_path / "sim"), KIBO_DIST_DIR=str(tmp_path / "out"))

    done = subprocess.run(
        ["bash", os.path.join(ROOT, "scripts", "pack.sh"), "Probe"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert done.returncode == 0, done.stdout.decode()

    with tarfile.open(str(tmp_path / "out" / "Probe.tar.gz")) as archive:
        names = [member.name for member in archive.getmembers() if member.isfile()]
    assert not [name for name in names if "__pycache__" in name or name.endswith(".pyc")]
    prefix = "catkin_ws/src/krpc_user/scripts/"
    packed = sorted(name[len(prefix) :] for name in names if name.startswith(prefix))
    expected = (
        ["kibo/" + name for name in _python_files(FLIGHT)]
        + _python_files(NODE)
        + ["user_template.py"]  # 官方範本，照原樣留著
    )
    assert packed == sorted(expected)
