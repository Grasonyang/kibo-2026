#!/usr/bin/env bash
# 解壓官方開發資源到 sim/，並在 krpc_user/ 還不存在時匯入官方範本。
# 用法：scripts/setup-sim.sh <krpc7th-simulator.tar.gz>
# 壓縮檔從 https://jaxa.krpc.jp/ 的 Download 頁取得（手冊 2.5）。
set -euo pipefail
source "$(dirname "$0")/_common.sh"

[ $# -eq 1 ] || { echo "用法：$0 <krpc7th-simulator.tar.gz>" >&2; exit 1; }
mkdir -p "$sim_root"
tar -xf "$1" -C "$sim_root"
require_sim

if [ -d "$root/krpc_user" ]; then
  echo "krpc_user/ 已存在，不覆蓋。"
else
  cp -r "$user_pkg" "$root/krpc_user"
  echo "已匯入官方範本到 krpc_user/，請檢視後再 commit。"
fi
