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
    sync_user
    (cd "$sim_dir" && bash ./simulation.sh)
    echo "結果：$sim_dir/share/logs/latest/"
    ;;
  replay)
    (cd "$sim_dir" && bash ./replay.sh)
    ;;
  *)
    echo "用法：$0 build | run | replay" >&2
    exit 1
    ;;
esac
