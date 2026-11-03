# ROS 接線層

這裡的檔案要放進官方範本的 catkin package 才能執行；本機沒有 ROS，只能過 `ruff` 與 `vermin`。

| 檔案 | 用途 |
|---|---|
| `user_node.py` | ROS 節點：`RosRobot` 實作 `kibo.mission.Robot`（含選用的相機修正 `marker_in_body`、`move_relative`），`UserNode` 保留官方要求的 start／stop／ready 三個介面 |

## 接進官方範本（拿到 `krpc7th-simulator.tar.gz` 後）

1. `scripts/setup-sim.sh <tar>` 解壓並把 `users/catkin_ws/src/krpc_user/` 匯入成本 repo 的 `krpc_user/`。
2. 看 `krpc_user/launch/` 或 `CMakeLists.txt` 裡啟動的是哪個腳本（手冊說範本是 `scripts/user_template.py`）。兩種做法擇一：
   - 把 launch 檔改成啟動 `user_node.py`；或
   - 保留檔名，把 `user_template.py` 的內容換成 `user_node.py`。
3. `scripts/sim.sh run` 會把 `ros/` 同步到 `krpc_user/scripts/`、把 `src/kibo/` 同步到 `krpc_user/scripts/kibo/`，所以 `from kibo...` 找得到（前提：ROS 以腳本所在目錄執行；若不是，要在 `user_node.py` 開頭把該目錄加進 `sys.path`）。
4. 確認 `package.xml` 有 `rospy`、`actionlib`、`ib2_msgs`、`krpc_ib2_msgs`、`platform_msgs`、`geometry_msgs` 的依賴（範本應該已經有）。

## 第一次在模擬器要核對的事

- `/ctl/command` 的 result 型別名稱（手冊寫 `CtlCommandResult`）與 `TERMINATE_*` 常數。
- `Navigation.pose.header.stamp` 是否有值；沒有的話 `pose()` 會因為「太舊」永遠回 None，要改成不檢查新鮮度。
- `judge.py` 的相機位置假設：伺服器判對中是用機體中心還是相機？看 Web 結果 JSON 的 level 與我們 log 的 Lv 是否一致。
- `Speeds`（規劃用的速度）與實際移動時間；用 log 裡每段 move 的秒數校正。
- 計時起點：我們的 t0 是 `/ib2_user/start` 到來的時刻。比對結果 JSON 的 `mission.start`、`duration_sec` 與 log 的 elapsed；若伺服器起算得更早，調大 `MissionConfig` 的保險或把 t0 往前推。
- 刪點後 Goal 是否仍給分：故意只去一半的點，看結果 JSON 的 `goal.success` 與 Goal Score。
- 服務呼叫用 daemon thread 加 `Event.wait` 做逾時（`_call`）；確認逾時後任務能繼續、節點能正常結束。
- 相機：`/camera_main/image_raw` 的 encoding（`_to_gray` 只支援 mono8／bgr8／rgb8／bgra8／rgba8）、`camera_info.K` 是否與影像解析度一致、`DICT_4X4_50` 是否偵測得到 marker、`MOVE_TO_RELATIVE_TARGET` 的 `body` frame 與我們的機體座標系（X 前 Y 左 Z 上）是否一致。
