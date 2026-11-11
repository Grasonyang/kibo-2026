# ROS 接線層

這裡的檔案由 `scripts/sim.sh run`／`scripts/pack.sh` 同步進官方範本的 `krpc_user/scripts/` 才能執行。
本機沒有 ROS，但 `pyright` 會檢查這個目錄（找不到 `rospy` 不算錯，呼叫了沒定義的方法會錯）。

| 檔案 | 用途 |
|---|---|
| `start_watch.py` | 起跑訊號的保險：有人在發 `/ib2_user/start` 而我們沒連上時自己去連（[simulator-internals.md](../docs/kibo/simulator-internals.md) 的 E11）。`user_node.py` 在 ready 之後開一個 daemon thread 跑它 |
| `user_node.py` | ROS 節點：`RosRobot` 實作 `kibo.mission.Robot`（含選用的相機修正 `marker_in_body`、`move_relative`），`UserNode` 保留官方要求的 start／stop／ready 三個介面 |

怎麼組進官方範本、怎麼跑，見 [docs/kibo/simulator.md](../docs/kibo/simulator.md)。

## 已在本機模擬器驗證（2026-11-10）

- 節點啟動、收到 `/ib2_user/start`、整場飛完並完成回報；normal 8 點全 Lv3。
- `use_sim_time` 為真；`/sensor_fusion/navigation` 的 `header.stamp` 有值（比現在晚約 0.11 秒），frame 是 `iss_body`，約 200 Hz。
- 影像 `/camera_main/image_raw` 是 800x800、`rgb8`。
- `/ctl/command` 從 STAND_BY（剛起跑）直接送 `MOVE_TO_ABSOLUTE_TARGET` 可以，不用先 RELEASE。
- 自判等級與官方 `result.json` 幾乎都一致。唯一的例外：一場 hard 的 Goal 自判 Lv2、官方 Lv1（機體還在轉就回報；原因與修正見 [simulator-internals.md](../docs/kibo/simulator-internals.md) 的 E8、E9）。
- 起跑時服務呼叫卡 5 秒的問題與修法（`RES_OPTIONS=single-request`）寫在 `user_node.py` 開頭。
- **起跑前要等事件 topic 的訂閱者都連上**（`_wait_for_event_listeners`），否則「任務開始」會遺失、整場沒有成績。
  每次改動後都要看 `judge_module_logs/result.json`（或跑 `scripts/sim_report.py`），不能只看節點自己的 log。
- **起跑訊號本身也會漏**（2026-11-11）：發佈者只存在 3 秒，master 的通知晚了節點就整場不動。`start_watch.py` 是保險；動到起跑流程時用 `scripts/start-signal/run.sh "plain watch" 60` 重新量（一次約 5 秒，不用啟動模擬器本體）。
- 相機偵測得到 marker（`DICT_4X4_50`），但深度與導航差約 15 cm，相機修正維持關閉。

還沒驗證：相機修正（預設關）、`/ib2_user/stop` 的中途停止、Web 模擬器。

下面的劇本是拿到模擬器之前寫的；第 0、1 場要查的事大多已經由原始碼與首飛回答
（[simulator-internals.md](../docs/kibo/simulator-internals.md)），留著是為了第一次上 **Web 模擬器**時照著核對。

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
- `at #n: ... -> Lv? nav_age=`：我們的 Lv 對 JSON `checkpoint_detail.level`。本機模擬器幾乎每點同級；Web 模擬器若恆較低，代表那邊的導航或擾動不同，先看 `marker #n seen` 那一行相機與導航差多少。
- `duration_sec` 對 log 的 elapsed：差 > 3 s → t0 要往前推或 `margin_sec` 加大。
- `goal.reason`、`Time Bonus`、各 Lv 的分數：校正 `scoring.py` 的常數。
- 有沒有被「長時間不動」提前結束（規則書 4.2.5）：有的話 `settle_timeout_sec` 要縮。

### 第 3、4 場：只在刪點會觸發、而且第 0 場與 POC 都沒給答案時才做的探針

第 2 場若從沒出現 `dropping`，或第 0 場的 `goal.reason` 已經說明了 Goal 規則，這兩場可以省。探針旗標預設關，用 ROS 私有參數開（`_probe_skip_one_waypoint:=true`、`_probe_deliberate_late_after:=2`、`_probe_notify_even_if_level0:=true`），log 會印 `PROBE FLAGS ON`；**決賽程式不得開啟**（規則書 4.2.4 只能跑一次），提交前確認 launch 檔沒有帶這些參數。
- `skip_one_waypoint=True`：看 `goal.success` 與 Goal Score → 定 A（需全點）或 B（只需 Goal 點）。
- `deliberate_late_after=2`：看已過的點分數是否保留、Time Bonus 多少 → 定 T0 或 T1。
- `notify_even_if_level0=True`：自判 0 分也回報，拿伺服器判定校準 `judge`。
定了世界就把 `kibo_lab.tune` 對應那一欄當主要依據。

### 其他要核對的

- `/ctl/command` 的 result 型別名稱（手冊寫 `CtlCommandResult`）與 `TERMINATE_*` 常數。
- 相機：`/camera_main/image_raw` 的 encoding（`_to_gray` 只支援 mono8／bgr8／rgb8／bgra8／rgba8）、`DICT_4X4_50` 是否偵測得到、`MOVE_TO_RELATIVE_TARGET` 的 `body` frame 與機體座標系（X 前 Y 左 Z 上）是否一致。
- 服務呼叫逾時（`_call` 用 rospy 時間輪詢）：逾時後任務能繼續、節點能正常結束。
- KEEP_POSE 是否主動抗擾：決定假機器人的殘餘運動該怎麼補。
