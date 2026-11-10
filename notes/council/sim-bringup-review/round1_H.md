# H（魔鬼代言人）第一輪

預設立場：本機的好結果不會轉移到 Web 與實機。下面逐題找理由。

## 1. 結果說明什麼
- **站得住**：對 `judge.py` 的算式（J3–J7）與程式的自判一致，黃金值有測，且本機 60 多個點自判與官方同級（`docs/kibo/simulator-internals.md:25,76`）。控制器的行為也站得住：先平移再轉向、bang-bang 剖面（`docs/kibo/motion-model.md:12-13`）。
- **只在本機成立**：
  - 20 場全是零擾動（E7，`simulator-internals.md:74`）、無 5 分鐘時限（R1，`simulator-internals.md:56`）。「完成 246–276 s」沒被任何時限考驗過。
  - 時間模型是用 `ctl.yaml` 反推控制器，再拿同一個控制器驗證。預測誤差 ±0.5 s 只證明「我讀得懂這份程式」，不證明 Web 或實機相同（`motion-model.md:81-102`）。
  - 修正是看了失敗場次才加的，最終版程式只有約 3 場（192640、193336、194105；`motion-model.md:99-102`）。「hard 9/10、全 Lv3」是調參後的訓練表現，不是留出測試。
  - 到點精度 1 cm 來自導航誤差 2 mm（R6，`simulator-internals.md:61`）；真實感測器噪音未知。
- **最大的未驗證點**：E6 顯示 9 點只有 6 點看得到 marker（`simulator-internals.md:73`）。本機的評分只用導航（J1），但規則書 2.3.1 寫的是「認得 AR marker 且 marker 在相機中央 1 秒」（`/home/grason/Documents/kibo-2026/docs/reference/rulebook.txt:385-388`）。伺服器若真的看相機，約三分之一的點會因為看不到 marker 而不算。

## 2. 為本機最佳化的做法
- **起跑保護**
  - 風險：它是「失敗時放行」。找不到發佈者就不等（`ros/user_node.py:264-266`）。Web 若經 `SCORE_API_URL` 或別的路徑，E1 同樣會發生，而且偵測不到。反過來，多一個一直連不上的訂閱者就白耗 10 s，而 t0 已起算（`src/kibo/mission.py:171`），十場都耗。
  - 驗：Web 第一場 grep `event listeners connected after` 與起跑到 `mission_start` 的間隔。
- **尾段自判**
  - 風險：每點省約 1 s（`motion-model.md:134`），正好是規則書要的「停 1 秒」（`rulebook.txt:424`）。有擾動時，軌跡在界內擦過再漂出，自判會放行。
  - 驗：Web 結果的各點 level 對自判。
- **八成緩衝**
  - 風險：`slack = remaining − reserved`（`mission.py:214-219`），而 `reserved` 不含 `margin_sec`（`src/kibo/budget.py:88` 才加）。所以保險的 15 s 會先被每點最多 3 s 的嚴格等待花掉。有擾動時八成很難達到，每點都吃滿 3 s，十二點約 36 s。
  - 驗：本機把 `ctl.yaml` 推力調低 20% 跑 hard，看被刪幾點。
- **保險 15 s**
  - 風險：不能降到 10。「300 場平均多 0.24 點」（`motion-model.md:112-117`）是同一個模型自己算的。
  - 驗：先看 Web 實際完成時間分佈。
- **照抄 `ctl.yaml`**
  - 風險：實機參數不同（`motion-model.md:139`）。校正有 1.25 倍死區（`mission.py:277`），慢 20% 不會被校正，約 250 s 的飛行會多 50 s，遠超過 15 s。逐點重規劃只擋得住剩餘段落。
  - 驗：同上，降低推力跑一場。
- **`RES_OPTIONS`**：風險低，`setdefault` 無害。副作用是拿掉官方範本偶然的 5 s 屏障（E2），之後只靠起跑保護擋。
- **Goal 排最後**：保守，與 2.2.4 一致，風險低。

## 3. 規則與審查
- **2.2.3**：我們靠導航、不看 marker（見 1）。對 JAXA 安全審查不是問題，對 Web 伺服器是問題（上面已列）。
- **2.2.4**：`run_mission` 在例外或 `no checkpoints` 時，人在別處也送 `mission_finish`（`mission.py:473-476`）。字面上「抵達 Goal 才報」被違反，雖然是為了保倍率。
- **手冊 6.5**：「Service 不可用就結束」（`/home/grason/Documents/kibo-2026/docs/reference/manual.txt:2316`）。我們 `wait_for_service` 逾時只 `return`，仍照樣 `mission_start`（`user_node.py:250-253`、`mission.py:462`）。
- **探針旗標（審查最容易挑到）**：`deliberate_late_after` 刻意等到逾時（`mission.py:441-446`），`skip_one_waypoint`、`notify_even_if_level0` 都在，且能用 ROS 參數開（`user_node.py:528-530`）。`sync_user` 把整個 `src/kibo/`（含 `fake_robot`、`tune`）同步進提交包（`scripts/_common.sh:21`）。決賽前要移除或編譯期關掉。
- **時鐘**：迴圈與睡眠用 `rospy.get_time`，使用的是模擬時鐘（E4）。模擬時鐘停住時 `rospy.sleep` 會停住；是否有牆鐘後備，需查證。

## 4. 上 Web 前還值得做的（最多三件）
1. **用乾淨解壓測 `scripts/pack.sh` 的產物**：在乾淨的模擬器 catkin 建得起來、跑得完一場。驗收：這場有 `result.json`。不做的代價：Web 若 FAILED 就不能提交（`rulebook.txt:493-505`）。
2. **擾動壓力測**：在 `compose.local.yaml` 把推力或導航噪音調差，驗收 Goal 一定在 300 s 內完成回報、校正會觸發。不做的代價：第一小時才發現 Goal 被擠掉。這是測安全路徑，不是為了調參。
3. **決賽版剝離**：移除探針與假機器人。驗收：`vermin`／pytest 照過、提交包不含 `fake_robot` 與 `tune`。

之後該停，不要在本機繼續調分。

## 5. 使用者回來最該先決定
- 先決定 **Web 前幾場的用途**。次數上限未知（questions #8），探針場（刻意逾時、漏點）會燒掉寶貴場次。建議先跑一場正常基線，拿到 FINISHED 就先提交一份（規則書 3.1 允許重送）。
- **今天就送 POC 提問**（#1、2、3、7、8、12、13、14）。截止與提交同日（`docs/kibo/questions-for-poc.md:3`），回覆需要時間，Web 第一小時要靠答案判讀。
- #6（15 或 10）依 Web 結果決定，不先改。

## 值得記錄
1. 本機驗證的循環性：時間模型由 `ctl.yaml` 反推，再由同一個控制器驗證。「預測準」不等於 Web／實機準。
2. 起跑保護失敗時放行（找不到發佈者就不等），在 Web 若走不同路徑，E1 風險無法偵測。
3. `slack` 不含 `margin_sec`，所以保險秒數會被嚴格等待先花掉；要靠降低推力的壓力測才看得到。
