# 開發環境

本專案只有一個語言：**Python**。工具鏈以 **uv** 為基礎。為什麼不用 Rust，見 [ADR-0001](../adr/0001-python-for-ros-melodic.md)。

## 兩個 Python：工具用的與執行用的

| | 版本 | 用在哪 |
|---|---|---|
| 執行環境（模擬器、Web 模擬器、實機 IB2） | **Python 3.6.9**、ROS 1 Melodic | 競賽程式真正跑的地方，由 JAXA 的 Docker image 決定，不能改 |
| 開發工具（本機 uv） | 3.8（`.python-version`） | ruff、pyright、pytest、vermin。uv 與 ruff 都不再支援 3.6，3.8 是能用的最接近版本 |

所以 **`src/` 的程式碼必須能在 3.6 執行**，不能只靠本機測試通過。規則：

- 不用 3.7 以後的語法或標準庫：`dataclasses`、`from __future__ import annotations`、`:=`、位置專用參數（`/`）、`list[int]` 這類內建泛型、`typing.Literal`／`Protocol`／`TypedDict`、`functools.cached_property`。
- 資料型別用 `typing.NamedTuple`（類別語法在 3.6.1 起可用）或一般 class。
- 第三方套件以 Melodic 映像內已有的為準（rospy、numpy、OpenCV 3.3.1、cv_bridge）；本機要用其他套件，先確認映像裡有，否則不要用。本機的 `opencv-contrib-python-headless` 是 5.x，只當開發依賴；`vision.py` 同時支援 3.x 與 4.7+ 的 ArUco API，cv2 延後 import。
- `vermin` 會檢查 `src/` 需要的最低 Python 版本，目標 3.6，是「驗證指令」的一部分。它是靜態推測，**最終仍以本機模擬器（Docker 內的 3.6.9）為準**。

## 共通原則

- 環境可重現：版本釘在檔案裡、鎖檔進版控、指令從專案根目錄執行。
- 不依賴全域安裝：lint、型別檢查、測試工具都是專案的 dev 依賴，agent 在乾淨的 worktree 裡就能跑。
- 每個 worktree 各自有一份 `.venv`。開 worktree 後先跑下方的「安裝」。
- 競賽提交物必須只含程式碼；不要把模擬器本體、log、rosbag 放進版控（已在 `.gitignore`）。

## 專案結構

| 路徑 | 內容 |
|---|---|
| `src/kibo/` | 不依賴 ROS 的純 Python 邏輯（場地資料、路徑規劃、幾何運算），本機可直接單元測試。整個目錄會進提交包：節點用不到的模組不放這裡 |
| `src/kibo_lab/` | 本機實驗用的工具（假機器人、假裁判、隨機場景、假設的分數表、參數掃描）。不進提交包；`src/kibo/` 與 `ros/` 不得匯入它（`tests/test_flight_package.py`） |
| `tests/` | pytest；測 `src/kibo/` 與 `src/kibo_lab/` |
| `krpc_user/` | 提交給模擬器的 catkin package，尚未建立：取得 JAXA 的開發資源後，由 `scripts/setup-sim.sh` 匯入官方範本（見 [docs/kibo/simulator.md](../kibo/simulator.md)） |
| `sim/` | 解壓後的官方模擬器（不進版控） |
| `docs/kibo/` | 規則與 API 摘要 |
| `docs/reference/` | 官方 PDF（不進版控，見該目錄 README） |

ROS 相關程式（要 `import rospy`、`krpc_ib2_msgs`）只能在模擬器的容器裡執行，不放進 `src/kibo/`，也不在本機測試。邏輯寫成純函式放 `src/kibo/`，ROS 節點只負責把訊息接到那些函式。

## 日常指令

| 目的 | 指令 |
|---|---|
| 加依賴 | `uv add <pkg>`（先確認 Melodic 映像有這個套件） |
| 加開發依賴 | `uv add --dev <pkg>` |
| 執行 | `uv run <cmd>`（不手動 activate venv） |

不用 `pip install`，不手動編輯 `uv.lock`。

## 驗證指令

```markdown
- 安裝：`uv sync --locked`
- 格式：`uv run ruff format --check .`
- 靜態檢查：`uv run ruff check . && uv run pyright && uv run vermin --target=3.6- --no-tips --violations src ros`
- 測試（全部）：`uv run pytest`
- 測試（單檔）：`uv run pytest tests/test_x.py`
```

`--locked` 在 `uv.lock` 與 `pyproject.toml` 不一致時會失敗，agent 因此不會悄悄改到鎖檔。

`scripts/check.sh` 一次跑完安裝、格式、靜態檢查與全部測試，任何一步失敗就停；改上面的指令時要一起改它。
`scripts/install-hooks.sh` 把它掛成這個 clone 的 pre-push hook（選用，`--remove` 還原）。

另有一道不在上面的關卡：改了會進 `krpc_user/` 的程式，交付前要在本機模擬器跑一次（`scripts/sim.sh run`），把分數與 `share/logs/latest/` 的結論貼進交付報告。提交前一定要在 Web 模擬器的「Preliminary」跑到 `FINISHED`（規則書 3.1）。

## 本機模擬器

需要 Docker，約 6 GB image、40 GB 空間。本機是 aarch64，`build.sh` 要加 `--arm64`（手冊 4.4.3）；`scripts/sim.sh` 已處理。用法見 [docs/kibo/simulator.md](../kibo/simulator.md)。

跑模擬器時要守的四件事（每一件都實際出過事）：

- **以官方的結果為準**：跑完用 `uv run python scripts/sim_report.py --last 1` 看 `result.json` 的等級。節點自己的 log 顯示「任務完成」不代表有成績。
- **「無成績」先分辨是誰的問題**：`judge_module_logs/judge.log` 有 `before mission start` 是起跑保護沒擋住；`system.log` 有 `Plugins for the model will not be loaded` 是模擬器自己啟動失敗，重跑即可。
- **起跑流程有自己的重現腳本**：`scripts/start-signal/run.sh "<模式…>" <次數>` 用兩個容器重現「起跑訊號漏接」（只需要官方映像，不啟動模擬器本體，一次約 5 秒）。動到 `ros/user_node.py` 的啟動段或 `ros/start_watch.py` 時跑 `"plain watch" 60` 與 `"drop drop+watch" 10`。
- **背景連跑多場時不要改 `src/`、`ros/`、`krpc_user/`**：`scripts/sim.sh run` 每一場啟動時才同步程式碼，後面的場次會吃到改到一半的檔案。要改就開另一個 worktree。
- **一次只能跑一場**：容器名稱與埠是固定的。埠被占用時設 `KIBO_SIM_PORT`。

## 共用工具基線

核對日期：2026-11-03，本機實際版本。

| 工具 | 版本 | 備註 |
|---|---|---|
| git、gh | gh 2.102 以上 | `--parent`、`--add-blocked-by` 需要 2.102 以上 |
| uv | 0.9.15 | Python 的唯一入口 |
| Docker | 29.2.1 | 本機模擬器用 |
| 本機架構 | aarch64 | 與 Web 模擬器、實機 Jetson TX2 同為 ARM64 |

版本更新後請回來改這張表。
