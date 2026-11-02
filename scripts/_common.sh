# 供其他腳本 source：共用路徑與檢查。
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sim_dir="$root/sim/krpc7th-simulator"
user_pkg="$sim_dir/users/catkin_ws/src/krpc_user"

require_sim() {
  [ -d "$sim_dir" ] || { echo "找不到 $sim_dir，先跑 scripts/setup-sim.sh <krpc7th-simulator.tar.gz>" >&2; exit 1; }
}

# 把我們的 krpc_user 與 src/kibo 同步進模擬器的 users/（模擬器端的 krpc_user 只讀，以本 repo 為準）。
sync_user() {
  require_sim
  [ -d "$root/krpc_user" ] || { echo "沒有 $root/krpc_user，先跑 scripts/setup-sim.sh 匯入官方範本" >&2; exit 1; }
  rsync -a --delete --exclude 'scripts/kibo' "$root/krpc_user/" "$user_pkg/"
  mkdir -p "$user_pkg/scripts"
  rsync -a --delete --exclude '__pycache__' "$root/src/kibo/" "$user_pkg/scripts/kibo/"
}
