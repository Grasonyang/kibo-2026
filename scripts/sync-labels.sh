#!/usr/bin/env bash
# 把 .github/labels.tsv 同步到 GitHub repo（已存在的標籤會被更新）。
# 用法：scripts/sync-labels.sh [owner/repo]   省略時使用目前目錄的 repo
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
repo_args=()
[ $# -ge 1 ] && repo_args=(-R "$1")

while IFS=$'\t' read -r name color desc; do
  [ -z "$name" ] && continue
  gh label create "$name" --color "$color" --description "$desc" --force "${repo_args[@]}" >/dev/null
  echo "label: $name"
done < "$root/.github/labels.tsv"
