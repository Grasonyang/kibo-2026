# 模擬器與提交流程

來源：Programming Manual 1.0 第 2 到 4 章。

## 兩種模擬器

| | Web 模擬器 | 本機模擬器 |
|---|---|---|
| 用途 | 提交前檢查、共同環境評估 | 開發與除錯 |
| 位置 | JAXA 伺服器 | 本機 Docker |
| 架構 | **ARM64**（接近實機 Jetson TX2） | 通常 x86_64；本機 gx10 是 aarch64 |
| 帳號 | 向所在國家／地區的 POC 申請 | 不需要 |

本機結果不保證等於 Web 或實機（架構、速度、可用函式庫會差），**最終以 Web 模擬器為準**。

## 取得開發資源

1. 到 <https://jaxa.krpc.jp/download> 下載 `KRPC7 Simulator Resources`（`krpc7th-simulator.tar.gz`，7.5 MB，**不用登入**）。
2. `scripts/setup-sim.sh <路徑>`：解壓到**主 checkout** 的 `sim/`（不進版控，所有 worktree 共用；要換位置設 `KIBO_SIM_ROOT`）。`krpc_user/` 已在版控裡，不會被覆蓋。
3. `scripts/sim.sh build` 建 Docker image。

解壓後只有 `users/catkin_ws/src/krpc_user/` 可以改；`krpc_api_server`、`krpc_ib2_msgs`、`docker/`、`rootfs/`、`rviz/`、`share/`、`build.sh`、`simulation.sh`、`replay.sh`、`docker-compose*.yaml`、`users/bootstrap/`、`users/packing.sh` 都不改。
官方另外要求：不改 package 名稱、不改 launch 檔名（`users/README.md`）。

## `krpc_user/` 怎麼組起來

| 來源（本 repo） | 同步到模擬器的 | 說明 |
|---|---|---|
| `krpc_user/` | `users/catkin_ws/src/krpc_user/` | 官方範本。我們只改了兩處：`launch/krpc_user.launch` 的 `team_user_script` 預設值改成 `user_node.py`，`CMakeLists.txt` 的安裝清單加上它 |
| `ros/user_node.py` | `…/krpc_user/scripts/user_node.py` | ROS 接線層 |
| `src/kibo/` | `…/krpc_user/scripts/kibo/` | 任務邏輯；節點從自己旁邊 import |

`scripts/sim.sh run` 與 `scripts/pack.sh` 每次都先同步，所以**以本 repo 為準**，不要直接改 `sim/` 裡的檔案。
也因此 `krpc_user/` 不能單獨拿去建置：它的 `CMakeLists.txt` 列了 `scripts/user_node.py`，那個檔案要同步之後才在。
`krpc_user/scripts/user_template.py` 是官方範例，原樣留著對照，不執行。

## 日常指令

```bash
scripts/sim.sh build                 # 建 Docker image（aarch64 自動加 --arm64；第一次要從原始碼編 OpenCV，很久）
scripts/sim.sh run                   # 同步後跑一場；畫面在 http://localhost:8080（埠被占用就設 KIBO_SIM_PORT）
LEVELS=veryhard scripts/sim.sh run   # 難度：easy 6 點、normal 8（預設）、hard 10、veryhard 12
scripts/sim.sh replay                # 重播上一場（rosbag）
scripts/pack.sh                      # 同步後打包成 dist/*.tar.gz，上傳 Web 模擬器
```

`run` 用的是官方 `simulation.sh` 的同兩個 `docker compose` 指令，多疊一份 `scripts/compose.local.yaml`，
把沒有密碼的畫面（noVNC）只綁在 `127.0.0.1:8080`（官方預設是對外的 80 埠）。埠用 `KIBO_SIM_PORT` 換。

每場的結果在 `sim/krpc7th-simulator/share/logs/<時間戳>/`，`latest/` 是最近一場的複本：
`cheat_sheet.json`（該場 CheckPoint）、`judge_module_logs/result.json`（各點 level、Goal 成敗、起訖時間）、
`user_programs_logs/user_program_output.log`（我們節點的輸出）、`simulation.bag`。

本機沒有 5 分鐘時限：完成回報後立刻結束，否則 10 分鐘看門狗（`execution_time=10m`）。分數也不在本機算。
模擬器內部的規則（評分、場景產生、啟動順序）整理在 [simulator-internals.md](simulator-internals.md)。

本機需求：Ubuntu 20.04 以上、4 核（建議 6）、8 GB（建議 16）、20 GB 空間（建議 40）。

## Web 模擬器

My Page → SIMULATION → 上傳 `.tar.gz`，選 Simulator Level（Easy／Normal／Hard／Very Hard）與版本，START SIMULATION。結果頁有分數、倍率、通過數、是否到 Goal，可下載 JSON 結果與使用者 log，也可用 SIMULATOR VIEWER 重播。要拿 sensor 或通訊資料只能用 rosbag（Web 不提供）。

## 尚未驗證

- `scripts/pack.sh` 假設 `packing.sh` 產出 `*.tar.gz` 在 `users/` 底下（看過 `packing.sh`，是這樣；還沒實際上傳過）。
- 提交包會包含 `krpc_user/scripts/kibo/`；Web 模擬器的建置流程是否與本機的 `build-user.sh` 相同，要上傳一次才知道。
