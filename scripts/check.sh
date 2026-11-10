#!/usr/bin/env bash
# 一次跑完 AGENTS.md 的「驗證指令」，任何一步失敗就停。推送前跑這個。
# 用法：scripts/check.sh
# 不含本機模擬器（一場七分鐘）：動到會進 krpc_user/ 的程式時另外跑 scripts/sim.sh run。
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n== %s\n' "$1"; }

step "安裝"
uv sync --locked
step "格式"
uv run ruff format --check .
step "靜態檢查"
uv run ruff check . && uv run pyright && uv run vermin --target=3.6- --no-tips --violations src ros
step "測試"
uv run pytest
printf '\n全部通過。\n'
