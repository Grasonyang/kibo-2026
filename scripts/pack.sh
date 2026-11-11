#!/usr/bin/env bash
# 產生要上傳 Web 模擬器的提交包（手冊 3.2），輸出到 dist/（要換位置就設 KIBO_DIST_DIR）。
# 用法：scripts/pack.sh [名稱]   省略時用 YourSourceCode
set -euo pipefail
source "$(dirname "$0")/_common.sh"

name="${1:-YourSourceCode}"
out_dir="${KIBO_DIST_DIR:-$root/dist}"
sync_user
mkdir -p "$out_dir"
archive="$out_dir/$name.tar.gz"
# 官方的 users/packing.sh 只有一行：tar -zcvf <名稱>.tar.gz catkin_ws/src。這裡是同一個指令，
# 多排除 __pycache__：那是容器裡的 root 跑過之後留下的，主機刪不掉，也不該送去審查。
# 包裡有哪些我們的模組由 sync_user 決定（整個 src/kibo/），tests/test_flight_package.py 守著。
tar -C "$sim_dir/users" --exclude='__pycache__' --exclude='*.pyc' -zcf "$archive" catkin_ws/src
echo "已產生：$archive（版本 $build_stamp）"
case "$build_stamp" in
  *+dirty) echo "注意：工作目錄有未提交的改動，這一包對不回任何一個 commit。要提交的包請先 commit 再打。" >&2 ;;
esac
echo "其中我們的程式（krpc_user/scripts/）："
tar -tzf "$archive" | sed -n 's|^catkin_ws/src/krpc_user/scripts/\(.*[^/]\)$|  \1|p' | sort
