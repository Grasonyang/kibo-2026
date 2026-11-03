# kibo-2026

第 7 屆 Kibo Robot Programming Challenge（Kibo-RPC）：為 ISS 上的自由飛行機器人 Int-Ball2 寫任務程式，在 5 分鐘內拜訪隨機配置的檢查點、讀 AR marker、抵達終點並回報。

- 資格賽：2027-01-21 到 02-17，**程式提交截止 2027-01-20 23:59（JST）**
- 語言：Python（執行環境 3.6.9、ROS 1 Melodic）。不用 Rust 的原因見 [ADR-0001](docs/adr/0001-python-for-ros-melodic.md)

## 先看這個

零基礎入口：[docs/solution/README.md](docs/solution/README.md)（比賽在玩什麼、怎麼解、程式怎麼讀、怎麼跑）。圖在 [FigJam](https://www.figma.com/board/dcZJJmt8eCZj1jt3yjR3wz)。

## 結構

| 路徑 | 用途 |
|---|---|
| `src/kibo/`、`tests/` | 不依賴 ROS 的任務邏輯、假機器人與單元測試 |
| `ros/` | ROS 接線層 `user_node.py`，要放進官方範本才能跑 |
| `docs/solution/` | 解法說明、spec、tickets、點子 |
| `krpc_user/` | 提交給模擬器的 catkin package（取得官方開發資源後匯入，尚未建立） |
| `docs/kibo/` | 規則摘要、API 速查、模擬器與提交流程 |
| `docs/agents/` | agent 協作流程（planner／worker／reviewer、交付、worktree） |
| `docs/adr/`、`GLOSSARY.md` | 決策紀錄與用語 |
| `scripts/` | `setup-sim.sh`、`sim.sh`、`pack.sh`、`sync-labels.sh` |
| `AGENTS.md`、`CLAUDE.md`、`.claude/`、`.codex/` | Claude Code 與 Codex 的指令與設定 |

## 開始

```bash
uv sync --locked          # 本機工具（ruff、pyright、pytest、vermin）
uv run pytest             # 純邏輯的單元測試
uv run python -m kibo.simulate --runs 10   # 本機假機器人跑 10 場
```

要跑模擬器，先從 <https://jaxa.krpc.jp/> 下載開發資源，見 [docs/kibo/simulator.md](docs/kibo/simulator.md)。協作規則與完整驗證指令見 [AGENTS.md](AGENTS.md)。

流程文件複製自 `Yang-Home-99/agent-config`，之後獨立演進。
