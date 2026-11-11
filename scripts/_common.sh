# 供其他腳本 source：共用路徑與檢查。
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 模擬器只解壓一份，放在主 checkout 的 sim/，所有 worktree 共用（Docker image 與 share/logs 也共用）。
# 要換位置就設 KIBO_SIM_ROOT。
main_root="$(git -C "$root" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')"
sim_root="${KIBO_SIM_ROOT:-${main_root:-$root}/sim}"
sim_dir="$sim_root/krpc7th-simulator"
user_pkg="$sim_dir/users/catkin_ws/src/krpc_user"

require_sim() {
  [ -d "$sim_dir" ] || { echo "找不到 $sim_dir，先跑 scripts/setup-sim.sh <krpc7th-simulator.tar.gz>" >&2; exit 1; }
}

# 把我們的 krpc_user、ros/ 與 src/kibo 同步進模擬器的 users/（模擬器端的 krpc_user 只讀，以本 repo 為準）。
# 提交包就是這個目錄打包的，所以 src/kibo/ 裡只放節點用得到的模組；本機實驗用的在 src/kibo_lab/，不送。
sync_user() {
  require_sim
  [ -d "$root/krpc_user" ] || { echo "沒有 $root/krpc_user，先跑 scripts/setup-sim.sh 匯入官方範本" >&2; exit 1; }
  # __pycache__ 是容器裡的 root 寫的，主機這邊刪不掉；留著無妨（Python 會照原始檔的時間重編）
  rsync -a --delete --exclude 'scripts/kibo' --exclude '__pycache__' "$root/krpc_user/" "$user_pkg/"
  mkdir -p "$user_pkg/scripts"
  rsync -a --exclude 'README.md' "$root/ros/" "$user_pkg/scripts/"
  rsync -a --delete --exclude '__pycache__' "$root/src/kibo/" "$user_pkg/scripts/kibo/"
  # 記下同步的是哪一版：commit 的短雜湊，有未提交的改動就加 +dirty。節點啟動時印出來，
  # scripts/sim_report.py 顯示在報表上（格式見 src/kibo/buildstamp.py）。
  build_stamp="$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  if [ -n "$(git -C "$root" status --porcelain 2>/dev/null)" ]; then
    build_stamp="$build_stamp+dirty"
  fi
  printf '%s\n' "$build_stamp" > "$user_pkg/scripts/build_stamp.txt"
}
