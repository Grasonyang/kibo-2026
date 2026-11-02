# Game API 速查

來源：Programming Manual 1.0（2026-10-05）第 6 章，Python 版。執行環境 ROS 1 Melodic、Python 3.6.9。完整範本是 `krpc_user/scripts/user_template.py`（匯入後可讀）。

## 必留的三件事

範本裡標了 `DO NOT REMOVE`，拿掉會讓任務不能開始或停不下來：

| 介面 | 內容 |
|---|---|
| `/ib2_user/start`（Topic，`platform_msgs/UserLogic`） | 必須訂閱；任務流程的起點。callback 要擋重複啟動 |
| `/ib2_user/stop`（Service，`StopProcessingUserNode`） | 必須提供；收到時先 cancel 所有執行中的 Action 再回應 `SUCCESS`，沒回應則範本的停止流程無法完成 |
| `/ib2_user/ready`（Parameter） | 初始化完成時 `rospy.set_param('/ib2_user/ready', True)`；沒設之前不會發 start |

## 任務事件

| 名稱 | 型別 | 用途 |
|---|---|---|
| `/mission/get_checkpoints` | Service `CheckPoints` | 取得 CheckPoint 定義，回傳 JSON 字串在 `message` |
| `/event/mission_start` | Service `MissionStart` | 通知任務開始 |
| `/event/checkpoint_passed` | Action `CheckpointPassed`（goal: `checkpoint_id`） | 請伺服器判定該點是否通過 |
| `/event/mission_finished` | Service `MissionFinished` | 到 Goal 後的完成回報 |

重點：

- **移動成功不等於通過。** 要先確認位置、對中、滾轉三項都滿足且已穩定，再送 `checkpoint_passed`；等級由伺服器判定。
- `get_checkpoints` 的 JSON：`checkpoint_count`、`checkpoints[]`（`checkpoint_id`、`position`、`marker_pose`、`score_bands`、`attitude.quaternion`、`attitude.centering_bands`、`attitude.roll_bands`）、`goalpoint_id`。bands 是 `{radius|angle, level}`，Lv3 最嚴格。
- Mission Finish 之後的動作不計分。

## 移動與感測

| 名稱 | 型別 | 用途 |
|---|---|---|
| `/ctl/command` | Action `CtlCommand`（goal: `target` PoseStamped、`type`） | 絕對移動 `MOVE_TO_ABSOLUTE_TARGET`（frame `iss_body`）、相對移動 `MOVE_TO_RELATIVE_TARGET`（frame `body`）、`STOP_MOVING` |
| `/ctl/wrench` | Topic `geometry_msgs/WrenchStamped` | 直接施力與力矩，較順但要自己管到位與停止；與 `/ctl/command` 混用可能出現非預期狀態 |
| `/ctl/status` | Topic `CtlStatus` | 控制狀態；從 `MOVE_TO_*` 變成 `KEEP_POSE` 或 `STOP_MOVING` 可用來判斷移動結束或中斷 |
| `/sensor_fusion/navigation` | Topic `Navigation` | 自身位置、姿態、速度、加速度 |
| `/camera_main/image_raw` | Topic `sensor_msgs/Image` | 主相機影像 |
| `/camera_main/camera_info` | Topic `sensor_msgs/CameraInfo` | 內部參數 `K`、`D`；收到第一則之前是 `None` |

`CtlCommand` 結果：`TERMINATE_SUCCESS=0`、`ABORTED=1`、`TIME_OUT=2`、`INVALID_NAV=3`、`INVALID_CMD=4`。重新規劃或停止用 `cancel_goal()`，確認 Action 結束後才送下一個目標。

## AR marker 辨識

OpenCV 3.3.1 的 ArUco；字典 **4x4**；ID 1 到 12；邊長 **0.02 m**（用公尺，不是像素）；相機內參用 `CameraInfo.K`、`D`，縮放或裁切影像要同步修正。`estimatePoseSingleMarkers` 回傳 marker 到相機座標系的轉換；相機座標系 X 右、Y 下、Z 前，要轉成 `iss_body` 需用相機安裝姿態另外換算。相機裝在 IB2 正前方 x = 0.14 m，光軸與機頭同向。

## 錯誤處理（手冊 6.5）

| 情況 | 做法 |
|---|---|
| Service 不可用 | `wait_for_service()` 設逾時，超過就結束 |
| Action server 不可用 | `wait_for_server()`，不啟動執行 |
| 移動失敗 | 不送到達通知，log 記錄原因 |
| Action 逾時 | `cancel_goal()` 並確認已停止 |
| `checkpoint_passed` 失敗 | 記錄 message，不無限重送 |
| 相機資料沒來 | 逾時後 log 並跳過依賴相機的處理 |
| 收到 `/ib2_user/stop` | cancel 所有執行中的 Action，安全結束後再回應 |

另：所有迴圈要有次數與時間上限、多個離開條件；ROS Action 都要設計逾時、取消與 shutdown 時的行為（手冊 5.1、6.1）。
