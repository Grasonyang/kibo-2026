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

## 第一次在模擬器：劇本（council v1-review R5）

每場 5 分鐘加啟動，第一小時大概只有 5 到 7 場，所以順序與「驗到什麼就改什麼」要先寫好。
Web 模擬器只回結果 JSON 與我們的 log（手冊 4.3.2），**log 寫了什麼就是全部的資料**。

### 第 −1 場（不用模擬器）：先問 POC

`docs/kibo/questions-for-poc.md` 的十個問題，答案能直接省掉第 3、4 場探針。提問截止 2027-01-20 12:00。

### 第 0 場：未改的官方範本

目的：拿到 `cheat_sheet.json` 與結果 JSON 的全貌，不花我們的程式。範本只走第一個點就完成回報（手冊 6.4.3），所以結果 JSON 的 `goal.success`／`goal.reason` 很可能**免費回答**「Goal 分數是否要求全部通過」。
核對：`goalpoint_id` 是否在 `checkpoints[]` 裡、`checkpoint_count` 含不含 Goal、id 是否等於 marker 編號、
有沒有 N/A 的點（手冊 4.3.1）、距離與傾角分布對 `scenarios.py` 的猜測（0.4–0.7 m、≤ 20°）、
範本的 shebang 與 `python` 版本（照抄到 `user_node.py`）、Simulator Level 有哪些、每日跑次配額。

### 第 1 場：只收資料，不飛

節點每場開始都會先印 `[survey]`（nav 頻率與 stamp、status、frame、`/use_sim_time`、`camera_info.K`、影像 encoding、`/ctl/status`），
另外 `/ctl/status` 每次狀態改變都記一行（RELEASE 何時結束、有沒有 DISTURBED）。
要純收資料不飛，啟動時給 ROS 參數 `_survey_only:=true`：節點會 mission_start、印 survey、立刻 mission_finish。
改程式：stamp 為 0 → `pose()` 改用接收時間；start 比 RELEASE 結束早 → t0 等狀態再起算；`use_sim_time` 為真 → 核對 `_call` 的逾時行為。

### 第 2 場：正常跑一場（校準）

設定：速度校正開（預設；速度猜對時零影響，起停時間被算進去反而讓預算誠實）、**相機修正關**（預設 `camera_fix_max_m=0`；ROS 端座標未驗證，開著會把每個不穩的點多一次移動，混淆 log）、探針全關。
逐項核對 log 與結果 JSON：
- 每段 `leg: Xm in Ys (model Zs)`：實際比模型慢超過 25% 會自動校正；慢超過 2 倍就要改 `Speeds` 預設值。
- `at #n: ... -> Lv? nav_age=`：我們的 Lv 對 JSON `checkpoint_detail.level`。伺服器恆較低 → 試 `camera_offset_m=(0,0,0)`；仍較低代表 nav 有偏差，相機修正升為主線。
- `duration_sec` 對 log 的 elapsed：差 > 3 s → t0 要往前推或 `margin_sec` 加大。
- `goal.reason`、`Time Bonus`、各 Lv 的分數：校正 `scoring.py` 的常數。
- 有沒有被「長時間不動」提前結束（規則書 4.2.5）：有的話 `settle_timeout_sec` 要縮。

### 第 3、4 場：只在刪點會觸發、而且第 0 場與 POC 都沒給答案時才做的探針

第 2 場若從沒出現 `dropping`，或第 0 場的 `goal.reason` 已經說明了 Goal 規則，這兩場可以省。探針旗標預設關，用 ROS 私有參數開（`_probe_skip_one_waypoint:=true`、`_probe_deliberate_late_after:=2`、`_probe_notify_even_if_level0:=true`），log 會印 `PROBE FLAGS ON`；**決賽程式不得開啟**（規則書 4.2.4 只能跑一次），提交前確認 launch 檔沒有帶這些參數。
- `skip_one_waypoint=True`：看 `goal.success` 與 Goal Score → 定 A（需全點）或 B（只需 Goal 點）。
- `deliberate_late_after=2`：看已過的點分數是否保留、Time Bonus 多少 → 定 T0 或 T1。
- `notify_even_if_level0=True`：自判 0 分也回報，拿伺服器判定校準 `judge`。
定了世界就把 `kibo.tune` 對應那一欄當主要依據。

### 其他要核對的

- `/ctl/command` 的 result 型別名稱（手冊寫 `CtlCommandResult`）與 `TERMINATE_*` 常數。
- 相機：`/camera_main/image_raw` 的 encoding（`_to_gray` 只支援 mono8／bgr8／rgb8／bgra8／rgba8）、`DICT_4X4_50` 是否偵測得到、`MOVE_TO_RELATIVE_TARGET` 的 `body` frame 與機體座標系（X 前 Y 左 Z 上）是否一致。
- 服務呼叫逾時（`_call` 用 rospy 時間輪詢）：逾時後任務能繼續、節點能正常結束。
- KEEP_POSE 是否主動抗擾：決定假機器人的殘餘運動該怎麼補。
