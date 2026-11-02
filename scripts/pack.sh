#!/usr/bin/env bash
# 產生要上傳 Web 模擬器的提交包（手冊 3.2），輸出到 dist/。
# 用法：scripts/pack.sh [名稱]   省略時用 YourSourceCode
set -euo pipefail
source "$(dirname "$0")/_common.sh"

name="${1:-YourSourceCode}"
sync_user
marker="$(mktemp)"
(cd "$sim_dir/users" && ./packing.sh "$name")
mkdir -p "$root/dist"
found="$(find "$sim_dir/users" -maxdepth 2 -name '*.tar.gz' -newer "$marker" | head -n1)"
rm -f "$marker"
[ -n "$found" ] || { echo "packing.sh 沒有產出新的 .tar.gz，請看上面的輸出" >&2; exit 1; }
cp "$found" "$root/dist/"
echo "已產生：$root/dist/$(basename "$found")"
