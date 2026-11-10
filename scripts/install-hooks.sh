#!/usr/bin/env bash
# 讓這個 clone（含它所有的 worktree）使用 .githooks/ 裡的 hook。只改這個 clone 的 git 設定。
# 用法：scripts/install-hooks.sh          啟用
#       scripts/install-hooks.sh --remove 還原成 git 預設
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  "")
    git config core.hooksPath .githooks
    echo "已啟用：推送前會跑 scripts/check.sh（git push --no-verify 可臨時跳過）。"
    ;;
  --remove)
    git config --unset core.hooksPath || true
    echo "已還原成 git 預設的 hook 路徑。"
    ;;
  *)
    echo "用法：$0 [--remove]" >&2
    exit 1
    ;;
esac
