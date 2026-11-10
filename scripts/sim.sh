#!/usr/bin/env bash
# 本機模擬器的包裝（手冊 4.4）。
# 用法：scripts/sim.sh build | run | replay
set -euo pipefail
source "$(dirname "$0")/_common.sh"
require_sim

case "${1:-}" in
  build)
    # aarch64 主機要加 --arm64（手冊 4.4.3）。
    flags=()
    [ "$(uname -m)" = "aarch64" ] && flags=(--arm64)
    (cd "$sim_dir" && bash ./build.sh "${flags[@]}")
    ;;
  run)
    # 與官方 simulation.sh 相同的兩個指令，只是多疊一份本機設定（畫面只綁 127.0.0.1）。
    # 難度用環境變數：LEVELS=easy|normal|hard|veryhard（預設 normal）。
    sync_user
    compose=(docker compose -f docker-compose.yaml -f "$root/scripts/compose.local.yaml")
    status=0
    (cd "$sim_dir" && "${compose[@]}" up --abort-on-container-exit --exit-code-from krpc) || status=$?
    (cd "$sim_dir" && "${compose[@]}" down)
    echo "結果：$sim_dir/share/logs/latest/（畫面 http://localhost:${KIBO_SIM_PORT:-8080}）"
    exit "$status"
    ;;
  replay)
    (cd "$sim_dir" && bash ./replay.sh)
    ;;
  *)
    echo "用法：$0 build | run | replay" >&2
    exit 1
    ;;
esac
