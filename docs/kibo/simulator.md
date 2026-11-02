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

1. 到 <https://jaxa.krpc.jp/> 的 Download 頁下載 `KRPC7 Simulator Resources`（`krpc7th-simulator.tar.gz`）。
2. `scripts/setup-sim.sh <路徑>`：解壓到 `sim/`（不進版控），並在 `krpc_user/` 不存在時把官方範本匯入成 `krpc_user/`。
3. 檢視匯入的 `krpc_user/` 後 commit。之後 `krpc_user/` 以本 repo 為準，`scripts/sim.sh`／`pack.sh` 會用 rsync 同步進 `sim/`。

解壓後只有 `users/catkin_ws/src/krpc_user/` 可以改；`krpc_api_server`、`krpc_ib2_msgs`、`docker/`、`rootfs/`、`rviz/`、`share/`、`build.sh`、`simulation.sh`、`replay.sh`、`docker-compose*.yaml`、`users/bootstrap/`、`users/packing.sh` 都不改。

## 日常指令

```bash
scripts/sim.sh build     # 建 Docker image（約 6 GB；aarch64 自動加 --arm64）
scripts/sim.sh run       # 同步 krpc_user 後跑一次；開 http://localhost 看畫面
scripts/sim.sh replay    # 重播上一次（rosbag）
scripts/pack.sh          # 同步後打包成 dist/*.tar.gz，上傳 Web 模擬器
```

結果在 `sim/krpc7th-simulator/share/logs/latest/`：`cheat_sheet.json`（該次 CheckPoint 配置）、`simulation.bag`、`judge_module_logs/`（評分）、`user_programs_logs/`（我們程式的輸出）。

本機需求：Ubuntu 20.04 以上、4 核（建議 6）、8 GB（建議 16）、20 GB 空間（建議 40）。Docker 用法 `docker run hello-world` 先確認；埠 80 被占用時改 `docker-compose.yaml`。

## Web 模擬器

My Page → SIMULATION → 上傳 `.tar.gz`，選 Simulator Level（Easy／Normal／Hard／Very Hard）與版本，START SIMULATION。結果頁有分數、倍率、通過數、是否到 Goal，可下載 JSON 結果與使用者 log，也可用 SIMULATOR VIEWER 重播。要拿 sensor 或通訊資料只能用 rosbag（Web 不提供）。

## 尚未驗證

以下是依手冊寫的，**還沒拿到 tar 實測**，第一次跑時回來修正：

- `scripts/_common.sh` 把 `src/kibo/` 同步到 `krpc_user/scripts/kibo/`，假設 catkin 執行時腳本旁的 `kibo/` 在 `sys.path` 上；若 `boot-ib2.sh` 是從安裝後的位置執行，這個假設可能不成立。
- `scripts/pack.sh` 假設 `packing.sh` 產出 `*.tar.gz` 在 `users/` 底下。
- `scripts/sim.sh build` 在 aarch64 加 `--arm64`：手冊說這是用 QEMU 模擬 arm64 的選項，同時又說「CPU 是 arm64 就加」，兩句在原生 arm64 主機上是否一致，要看實際建置行為。
