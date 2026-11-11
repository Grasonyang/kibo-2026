#!/usr/bin/env bash
# 重現「起跑訊號 /ib2_user/start 漏接」，並驗證 ros/start_watch.py 的保險。
# 兩個容器（主機名稱 krpc 與 krpc-user，和官方 docker-compose 一樣）用官方映像，不啟動模擬器本體；
# 一次約 5 秒。只需要 Docker 與 krpc/intball-simulator:latest 映像。
#
# 用法：scripts/start-signal/run.sh "<模式…>" <每個模式幾次>
#   模式見 sub.py：plain、watch、drop、delay:<秒>，用加號組合
# 例：  scripts/start-signal/run.sh "plain watch" 60             # 自然漏接率，有保險與沒有
#       scripts/start-signal/run.sh "delay:5 delay:5+watch" 20   # 通知晚 5 秒：沒保險一定漏，有保險收得到
#       scripts/start-signal/run.sh "delay:0.6+watch" 20         # 通知和保險同時到：仍然只起跑一次
# 每次印一行 JSON，最後印各模式的統計；有哪一次沒印出結果、或起跑超過一次，就以非 0 結束。
# 容器與網路的名稱是固定的：一次只能跑一個，開頭會先清掉上一次留下的。
set -euo pipefail
modes=${1:?用法：run.sh "<模式…>" <次數>}
count=${2:?用法：run.sh "<模式…>" <次數>}
repo=$(cd "$(dirname "$0")/../.." && pwd)
image=krpc/intball-simulator:latest
net=kibo-start-signal
out=""
cleanup() {
  docker rm -f "$net-krpc" "$net-krpc-user" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  [ -z "$out" ] || rm -f "$out"
}
cleanup # 上一次若被中斷，先清掉留下的容器
trap cleanup EXIT
out=$(mktemp)
docker network create "$net" >/dev/null
common=(--rm --network "$net" -e ROS_MASTER_URI=http://krpc:11311 -v "$repo":/repo:ro --entrypoint bash)
docker run -d "${common[@]}" --name "$net-krpc" --hostname krpc --network-alias krpc \
  -e ROS_HOSTNAME=krpc "$image" /repo/scripts/start-signal/master.sh >/dev/null
docker run "${common[@]}" --name "$net-krpc-user" --hostname krpc-user --network-alias krpc-user \
  -e ROS_HOSTNAME=krpc-user -e MODES="$modes" -e N="$count" "$image" \
  /repo/scripts/start-signal/user.sh | tee "$out"
python3 - "$out" "$count" $modes <<'PY'
import json
import sys

rows = [json.loads(line) for line in open(sys.argv[1]) if line.startswith("{")]
count, modes = int(sys.argv[2]), sys.argv[3:]
bad = False
for mode in modes:
    mine = [row for row in rows if row["mode"] == mode]
    missed = [row for row in mine if not row["got"]]
    late = [row for row in mine if row["master_update_sec"] is None or row["master_update_sec"] > 3.0]
    twice = [row for row in mine if row["starts"] > 1]
    print(
        "%-16s %3d 次，漏接 %d 次；起跑超過一次 %d 次；master 的通知超過 3 秒或沒到 %d 次；保險出手 %d 次"
        % (mode, len(mine), len(missed), len(twice), len(late), sum(row["connects"] for row in mine))
    )
    if len(mine) != count:
        print("  ↑ 應該有 %d 次：有幾次沒有印出結果，看上面的錯誤訊息" % count)
        bad = True
    bad = bad or bool(twice)
sys.exit(1 if bad else 0)
PY
