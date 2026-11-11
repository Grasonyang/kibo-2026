# kibo-2026

第 7 屆 Kibo Robot Programming Challenge（Kibo-RPC）：為 ISS 上的自由飛行機器人 Int-Ball2 寫任務程式，在 5 分鐘內拜訪隨機配置的檢查點、讀 AR marker、抵達終點並回報。

- 資格賽：2027-01-21 到 02-17，**程式提交截止 2027-01-20 23:59（JST）**
- 語言：Python（執行環境 3.6.9、ROS 1 Melodic）。不用 Rust 的原因見 [ADR-0001](docs/adr/0001-python-for-ros-melodic.md)

## 先看這個

- **目前做到哪裡**：[docs/STATUS.md](docs/STATUS.md)（成績、已完成、還沒做、在等什麼、還不知道什麼）。
- 零基礎入口：[docs/solution/README.md](docs/solution/README.md)（比賽在玩什麼、怎麼解、程式怎麼讀、怎麼跑）。
- 圖在 [FigJam](https://www.figma.com/board/dcZJJmt8eCZj1jt3yjR3wz)。

## 結構

| 路徑 | 用途 |
|---|---|
| `src/kibo/` | 不依賴 ROS 的任務邏輯；整個目錄會進提交包，所以只放節點用得到的模組 |
| `src/kibo_lab/` | 本機實驗用：假機器人、假裁判、隨機場景、假設的分數表、參數掃描；不進提交包 |
| `tests/` | 單元測試（pytest） |
| `ros/` | ROS 接線層 `user_node.py` 與起跑訊號的保險 `start_watch.py`，要放進官方範本才能跑 |
| `docs/solution/` | 解法說明、spec、tickets、點子 |
| `krpc_user/` | 提交給模擬器的 catkin package（官方範本，launch 改成啟動我們的節點） |
| `docs/kibo/` | 規則摘要、API 速查、模擬器與提交流程 |
| `docs/agents/` | agent 協作流程（planner／worker／reviewer、交付、worktree） |
| `docs/adr/`、`GLOSSARY.md` | 決策紀錄與用語 |
| `scripts/` | `check.sh`（推送前的驗證）、`setup-sim.sh`、`sim.sh`、`sim_report.py`、`pack.sh`、`start-signal/`（起跑訊號的重現）、`sync-labels.sh` |
| `AGENTS.md`、`CLAUDE.md`、`.claude/`、`.codex/` | Claude Code 與 Codex 的指令與設定 |

## 開始

```bash
uv sync --locked          # 本機工具（ruff、pyright、pytest、vermin）
uv run pytest             # 純邏輯的單元測試
uv run python -m kibo_lab.simulate --runs 10   # 本機假機器人跑 10 場
```

要跑模擬器，先從 <https://jaxa.krpc.jp/download> 下載開發資源（不用登入），見 [docs/kibo/simulator.md](docs/kibo/simulator.md)。
模擬器內部的評分規則在 [simulator-internals.md](docs/kibo/simulator-internals.md)，移動要花幾秒在 [motion-model.md](docs/kibo/motion-model.md)。協作規則與完整驗證指令見 [AGENTS.md](AGENTS.md)。

流程文件複製自 `Yang-Home-99/agent-config`，之後獨立演進。
