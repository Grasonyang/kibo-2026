#!/bin/bash
# 容器內、節點那一側：每個模式跑 $N 次，每次都是新的行程（和節點啟動一樣）。
# sub.py 的錯誤訊息留在標準錯誤，外層的 run.sh 會顯示；少印一行 JSON 會被 run.sh 當成失敗。
source /opt/ros/melodic/setup.bash
source /home/intball/catkin_ws/devel/setup.bash
for _ in $(seq 1 120); do rosparam list >/dev/null 2>&1 && break; sleep 0.5; done
for mode in $MODES; do
  for _ in $(seq 1 "$N"); do
    # 等上一次的發佈者（保留 3 秒）消失，否則新的節點一訂閱就收到舊的訊號
    for _ in $(seq 1 40); do
      rostopic info /ib2_user/start 2>/dev/null | grep -q '^ \* /rostopic' || break
      sleep 0.3
    done
    /usr/bin/python3 /repo/scripts/start-signal/sub.py "$mode"
  done
done
