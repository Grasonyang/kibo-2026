# 官方模擬器的內部規則（讀原始碼得到的）

來源：`krpc7th-simulator.tar.gz`（官網 Download 頁「KRPC7 Simulator Resources」，2026-10-05 版，
sha256 `7e0e1ef9…b9f46a`）。下面每一條都標了檔案與行號，路徑相對於解壓後的 `krpc7th-simulator/`。
這些是**本機模擬器**的行為；Web 模擬器與正式評分是否完全相同，見最後一節。

## 評分模組 `rootfs/krpc/judge_module/judge.py`

| # | 事實 | 出處 |
|---|---|---|
| J1 | 判定用的姿態來自 `/sensor_fusion/navigation`（`data.pose.pose`），不是 Gazebo 真值 | `pose_callback`，667 行；訂閱在 1031 行 |
| J2 | 評分模組的姿態最多每 0.2 秒更新一次：callback 裡有 `rospy.Rate(5).sleep()`，佇列長度 1 | 728、1031 行 |
| J3 | 距離：機體中心到 CheckPoint `position` | `evaluate_checkpoint_navigation`，433 行起 |
| J4 | 對中：機體 +X 軸與「**機體中心**指向 marker」的夾角。原點不是相機 | `_evaluate_centering_and_roll`，394 行 |
| J5 | 滾轉：實際姿態與目標姿態各自對「機體中心指向 marker」軸做 twist 分解，取差的絕對值 | 383、394 行 |
| J6 | 等級取距離、對中、滾轉三者最低；任一項 0 就整點 0 | 482 行 |
| J7 | **每個 CheckPoint 只判第一次通知**，沒過也記錄，之後的通知只印 `already processed` | `judge_checkpoint_passed`，843–858 行 |
| J8 | 通過通知沒有「維持 1 秒」的檢查，是通知當下的一次取樣。規則書 2.2.3 仍寫要在餘裕內停 1 秒，我們照規則書做 | 843 行起 |
| J9 | 完成回報時的 Goal：Goal 點先前通過 → 直接成功（`goal checkpoint previously passed`）；否則用**當下姿態**對 Goal 點再判一次，通過的話 Goal 點也補記為通過 | `judge_finish`，886–915 行 |
| J10 | 完成回報之後的通知一律忽略；開始之前的也忽略 | 844–849 行 |
| J11 | 評分模組**不算分數、不看時限**。輸出只有 `Illegal` 與 `JudgeReport`（各點 level、Goal 成敗、開始與結束時間） | `build_result_output`，626 行 |
| J12 | 設了環境變數 `SCORE_API_URL` 時，結束時把同一份輸出 POST 出去；分數與時間倍率應該是那一端算的 | 21、985 行 |
| J13 | 判定結果會發到 latched topic `/krpc/judge/checkpoint_result`（含 `selected_band`） | 70 行、`publish_checkpoint_result` |

J4、J5 的數值已經做成測試的黃金值（`tests/test_judge.py` 的 `OFFICIAL_GOLDEN`）。
J5 的後果：視線沒對準時滾轉會被放大。例：機體自己滾 25°、側偏 12 cm（視線歪 13.5°），官方量到約 32°，整點 0 分。

## API 伺服器 `users/catkin_ws/src/krpc_api_server/scripts/krpc_api_node.py`

| # | 事實 | 出處 |
|---|---|---|
| A1 | `checkpoint_passed` 的 result 永遠是 `success=True, message="accepted"`；它只是把事件轉發到 `/gs/data`，**不代表通過** | 105、202 行 |
| A2 | `get_checkpoints` 回的是 cheat sheet 的原樣：`checkpoint_count`、`checkpoints[]`（`checkpoint_id`、`position`、`marker_pose`、`score_bands`、`attitude`）、`goalpoint_id` | `cheat_sheet_loader.py` 的 `checkpoint_payload` |
| A3 | Goal 點一定在清單裡，沒有「不評分的 N/A 點」這種資料 | 同上；產生器見 G5 |

## 場景產生器 `rootfs/krpc/random_env_generator/generate_objects.py`

| # | 事實 | 出處 |
|---|---|---|
| G1 | 12 個 marker 的位置與姿態是固定的，寫在 `files/input/area_config.json`；marker 局部 +Z 是法線 | `area_config.json` |
| G2 | CheckPoint 離 marker **固定 0.5 m**；方向是法線偏航 ±20°、俯仰 ±15°（均勻） | 27–31、328–345 行 |
| G3 | 落在安全區外就重抽，最多 50 次；再不行用正前方，最後夾進安全區。安全區是 `[0.2, -0.8, 0.0]` 到 `[7.0, 0.85, 1.68]` | 46、357 行；`area_config.json` 的 `SafeArea` |
| G4 | 目標姿態：機頭正對 marker，繞視線滾 **±180°**（均勻） | 32–33 行、`sample_checkpoint_attitude_quaternion` |
| G5 | Goal 固定是 marker 12（Dock 旁的 Bay0 面板），一定選入 | 48、393 行 |
| G6 | 難度只決定點數（含 Goal）：easy 6、normal 8、hard 10、veryhard 12；其餘 marker 隨機抽 | 52–56 行 |
| G7 | 位置餘裕 0.1／0.2／0.3 m，對中與滾轉餘裕 10／20／30° | `area_config.json` 的 `score_bands`；36–40 行 |
| G8 | cheat sheet 的 Goal 只有 `checkpoint_id` 與 `all_checkpoints_bonus: 0` | 477–480 行 |

G3 的後果：marker 12 在 z=−0.10，安全區 z≥0，所以 Goal 點只會落在 z 0 到 0.03 這一小條。
G2 加上 J4：保持伺服器給的姿態時，側向偏 8.8 cm 對中就掉到 Lv2（位置要到 10 cm 才掉），所以**側向誤差比前後誤差貴**。

## 執行流程 `rootfs/run.sh`、`docker-compose.yaml`、`users/bootstrap/boot-ib2.sh`

| # | 事實 | 出處 |
|---|---|---|
| R1 | 本機沒有 5 分鐘時限，只有看門狗：預設 10 分鐘（環境變數 `execution_time`），或完成回報後立刻結束 | `docker-compose.yaml` 22 行；`run.sh` 356 行起 |
| R2 | 難度用環境變數 `LEVELS`（easy／normal／hard／veryhard），預設 normal | `docker-compose.yaml` 25 行；`run.sh` 197 行 |
| R3 | 啟動順序：等 `/krpc/ready` → `roslaunch krpc_user krpc_user.launch` → 我們設 `/ib2_user/ready` → 模擬器發 `/ib2_user/start` | `boot-ib2.sh`；`run.sh` 的 `go` |
| R4 | 結束時呼叫 `/ib2_user/stop`，再 `rosnode kill /krpc_user`；擷取 log 也只認節點名 `/krpc_user` | `run.sh` 的 `kill_user`、`extract_user_program_output_log` |
| R5 | 使用者程式用 `catkin_make` 建在 devel space；提交包是 `tar -zcvf <名稱>.tar.gz catkin_ws/src`（三個 package 都在裡面） | `users/catkin_ws/bootstrap/build-user.sh`、`users/packing.sh` |
| R6 | 導航誤差很小：位置平均約 2 mm、標準差不到 1 mm，延遲 0.1 s | `docker/ros_overlay/src/platform_sim/simulation/ib2_gazebo/sim/sim.yaml` 的 `nav_parameter` |
| R7 | 映像裡有 OpenCV 3.3.1（含 ArUco）、numpy、scipy、scikit-learn；範本的 shebang 是 `#!/usr/bin/python3` | `docker/Dockerfile.krpc-base`；`krpc_user/scripts/user_template.py` |

## 實際跑出來才知道的（2026-11-10，本機）

| # | 事實 | 證據 |
|---|---|---|
| E1 | **起跑太快，評分模組會漏掉「任務開始」，整場事件都被丟掉。** `krpc_api_node` 把事件轉發到沒有 latch 的 `/gs/data`，評分模組要先連上才收得到；它和使用者節點同時啟動 | 場次 `20261110122717` 與 `20261110130057`：`judge.log` 每筆都是 `… event received before mission start`，沒有 `result.json`。前者是 API 節點啟動後 1.33 秒就呼叫 `mission_start`；隔 1.15 秒的另一場卻沒事，所以是機率性的。後者是飛行記錄與狀態顯示兩個節點先連上、評分模組還沒 |
| E2 | 官方範本沒遇到 E1，是因為同一個容器裡的名稱查詢會卡 5 秒（E3），剛好把它擋住 | 同上；範本的流程與我們相同 |
| E3 | 映像的 glibc 2.27 同時送 A 與 AAAA 查詢，Docker 內建 DNS 會丟一個回應，**每個執行緒**頭幾次查詢各卡 5 秒 | 12 個新容器各查 5 次：12 個都有一次卡 5 秒；設 `RES_OPTIONS=single-request` 後 0 次 |
| E4 | `/sensor_fusion/navigation` 約 200 Hz，`header.stamp` 有值，比現在晚約 0.11 秒，frame 是 `iss_body`；`use_sim_time` 為真 | 節點的 `[survey]` 與尾段紀錄（64 筆只跨 0.33 秒） |
| E5 | 影像 800x800、`rgb8`；`camera_info` 的焦距 476.7、主點 (400.5, 400.5)、沒有畸變 | `[survey]` |
| E6 | `DICT_4X4_50` 偵測得到 marker（9 點裡 6 點看到）。用邊長 2 cm、相機在機頭前 0.14 m 換算，側向與導航一致，但**深度比導航多約 15 cm** | 每點的 `marker #n seen at body ...` |
| E7 | 規則書附錄 #22 的 Microgravity module 不在下載包裡：`ENABLE_GRAVITY_MODULE` 只出現在 `docker-compose.yaml`，沒有任何程式讀它 | 對整個下載包與映像 `grep` |
| E8 | **官方的滾轉量測在 Goal（marker 12）是病態的。** twist 角是 `2·atan2(q_vec·axis, q_w)`；機體朝世界 −X 看時姿態接近「繞垂直軸轉 180°」，分子分母都接近 0 | 模型：1.5° 的指向誤差加 6 mm 位置誤差、機體完全沒滾，marker 12 的讀數最大 16°，其他 marker 最大 2°（`tests/test_judge.py` 有對應測試）。實測：Goal 回報當下的讀數常在 5–9°，到位後會先衝到 13–18° 再降回來 |
| E9 | 評分模組用的姿態比我們看到的舊（J2），所以自判與官方可能差一級 | 場次 `20261110131242`（hard）：Goal 自判 Lv2（滾轉 19.5°，機體還在轉），官方給 Lv1。其餘 60 幾個點自判與官方一致 |
| E10 | 模擬器自己偶爾啟動失敗，機器人整場不受控 | 場次 `20261110130057`：`system.log` 有 `Sensors failed to initialize when loading model[ib2] … Plugins for the model will not be loaded`，機器人從 Dock 漂到 z=1.85 m |
| E11 | **起跑訊號 `/ib2_user/start` 只保留 3 秒，master 的通知晚了就收不到，節點整場不動。** `run.sh` 的 `go` 用 `rostopic pub --once` 送；master 通知訂閱者「有新的發佈者」偶爾要 5 秒多（E3 的名稱查詢延遲發生在 master 那一側，我們管不到）。節點自己輪詢 master、沒連上就主動去連（`ros/start_watch.py`）。蓋得到「通知晚到或沒到」與「問發佈者怎麼連時卡住」；蓋不到「已經問到、TCP 連線卻卡住」。節點啟動超過 1 小時才起跑時保險已經結束 | 場次 `20261110204911`（hard）：節點 ready 後 600 秒都沒有 `start`，記錄裡沒有 `topic[/ib2_user/start] adding connection`。`scripts/start-signal/run.sh`（兩個容器、不啟動模擬器本體）：無保險 60 次漏接 3 次，三次通知都在 5.4 到 6.3 秒才到；有保險 60 次漏接 0 次；把通知丟掉時無保險 4/4 漏接、有保險 4/4 收到 |

我們的對策：
- E1 → 起跑前先等 `/event/mission_start` 服務出現，再問 master 誰發、誰訂 `/gs/data`，並問發佈者它的連線；
  **登記的訂閱者全部連上**才送任務開始。不認節點名字，牆鐘上限 10 秒，沒有人發佈這個 topic（例如實機）就不等。
  程式在 `ros/user_node.py` 的 `_wait_for_event_listeners`，判讀規則在 `src/kibo/buslinks.py`。
- E3 → 節點開頭設 `RES_OPTIONS=single-request`。
- E6 → 相機修正維持關閉；每點只記一行相機與導航的比對（`MissionConfig.camera.log_marker`）。
- E8、E9 → 這一點還有餘裕時，先等距離、對中、滾轉都在 Lv3 上限的八成以內才回報，最多多等 3 秒
  （`MissionConfig.settle.notify_margin`、`settle.strict_sec`）。「有沒有餘裕」看的是剩餘時間扣掉後面路線還要的秒數
  （`_Run.slack`），不是剩餘時間的絕對值：到 Goal 時剩 26 秒其實很充裕。
- E10 → 無法從我們這邊避免。`scripts/sim_report.py` 會把這種場次標成「無成績」，統計時要排除。

## 對 `questions-for-poc.md` 的影響

| 題 | 本機模擬器的答案 | 還要不要問 |
|---|---|---|
| 1 Goal 分是否要求全點通過 | 評分模組只回報 Goal 是否到達，不算分（J11）。欄位名叫 `all_checkpoints_bonus`（G8），與規則書附錄 #20「passes all CheckPoints」一致，**傾向要求全點** | 要：分數在伺服器端算 |
| 2 逾時是否保留分數 | 本機不看時限（R1、J11） | 要 |
| 3 計分表 | 不在壓縮檔裡（J11、J12） | 要 |
| 4 對中的原點 | 機體中心（J4） | 不用 |
| 5 計時起點 | 評分模組記的是收到 `mission_start` 的時刻（`judge_start`）；`duration_sec` 是它到完成回報的差 | 只需確認伺服器用的是這個 |
| 6 Goal 是否在清單、有無 N/A 點 | 一定在，沒有 N/A（A3、G5） | 不用 |
| 7 資格賽用哪個難度 | 四個難度都存在（G6），用哪個沒寫 | 要 |
| 8 Web 模擬器次數上限 | 不在壓縮檔裡 | 要 |
| 9 ArUco 字典與影像 encoding | 待本機跑一場看 `[survey]` | 先自己量 |
| 10 nav stamp 與 status | 待本機跑一場看 `[survey]` | 先自己量 |

## 新冒出來、只有主辦能回答的問題

- **Goal 能不能先過？** 本機評分模組接受「先通過 Goal 點、最後在別處完成回報」（J9）。但規則書 2.2.4 寫
  「完成回報必須在抵達 GoalPoint 時送出」，附錄 #12 把 GoalPoint 定義成「通過所有 CheckPoint 之後移動到的點」。
  我們照規則書做（Goal 排最後）；不照做能省掉回程，但有被判違規的風險。
- **`/krpc/judge/checkpoint_result` 能不能訂閱？** 它會告訴程式每點拿到幾級（J13）。實機上沒有這個 topic，
  我們不訂閱、不依賴。

## 還不知道的

Web 模擬器與正式評分是否用同一份 `judge.py`；各 Lv 的點數、Goal 分、時間倍率公式；5 分鐘時限在哪裡執行。
