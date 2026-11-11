#!/bin/bash
# 容器內、模擬器那一側：roscore，然後照官方 run.sh 的 go()：
# 等 /ib2_user/ready 變成 true，送一次 `rostopic pub --once /ib2_user/start`（只保留 3 秒）。
# 每個等待都有次數上限；外層的 run.sh 結束時會把這個容器整個移除。
source /opt/ros/melodic/setup.bash
source /home/intball/catkin_ws/devel/setup.bash
roscore >/dev/null 2>&1 &
for _ in $(seq 1 120); do rosparam list >/dev/null 2>&1 && break; sleep 0.5; done
for _ in $(seq 1 100000); do
  for _ in $(seq 1 600); do
    [ "$(rosparam get /ib2_user/ready 2>&1)" == "true" ] && break
    sleep 1
  done
  rostopic pub --once /ib2_user/start platform_msgs/UserLogic "id: 0" >/dev/null 2>&1 &
  for _ in $(seq 1 200); do
    [ "$(rosparam get /ib2_user/ready 2>&1)" == "true" ] || break
    sleep 0.3
  done
done
