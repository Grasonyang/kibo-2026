# 第一輪回答（匿名）

四份回答，順序已打亂、身分已去除。題號同 brief。

---

# 回答 甲


方法：以 Bash 唯讀跑假機器人（記憶體內 monkeypatch `mission.plan_within_budget`，未寫檔）。設定：位置誤差 0.05、失敗率 10%、種子 100+i、每格 40 場、真實速度 0.06/0.08/0.10/0.14（規劃假設 0.10）、n=8/12。分數常數（Lv3/2/1=10/6/3、Goal=20、倍率線性 1→2，`scoring.py:34-39`）全是猜的，只看方向。定義四個世界：Goal 規則 A（Pt_goal 需全部 CP 通過）/B（只需 Goal 點通過）× 逾時規則 T0（逾時整場 0 分，現行假機器人 `fake_robot.py:162-163`）/T1（逾時前 CP 分保留）。

## 1. 檢討
站得住：Goal 當 CP 並 notify（`mission.py:303-305`），手冊結果 JSON 的 `goal checkpoint previously passed`（manual.txt:878）比附錄 #20（rulebook.txt:771）更像 B；Held-Karp 比最近鄰省 13–26 s（n=6→12，模擬）。
最可能被推翻：
1. 時間常數（`planner.py:18-21`、`budget.py:24-26`）。真實 0.05 m/s 時 n=10 的 Goal 到達 10/30（0.10 時 30/30），平均約 20 對 105，是整份設計最大的槓桿（3–5 倍），遠大於相機 +15%。檢驗：模擬器 log 第一段 move 的秒數。
2. 「逾時＝0 分」。規則書只說逾時沒有「完成回報」的分（rulebook.txt:317），Mission Finish 後的動作無效（:735-737），字面是 T1。這是「寧可早刪」的主要理由。檢驗：故意超時一場。
3. 相機 +15%、只求 Lv2 +10% 來自假機器人到點後靜止、高斯誤差（`fake_robot.py:98-105`），真機有殘餘振盪時未必成立。檢驗：到點後記 5 秒位置。

## 2. 刪點避險
真的來不及時：令 p≈單點分（8–10）、g=Goal 分、S=已得分、e≈1–1.5（不刪能多拿的點數）、π=P(B)、τ=P(T0)。
ΔEV(刪−不刪) ≈ π·g + τ·S − e·p。g=20、S≈80 時，π=0 也只需 τ>10–20% 就為正。最壞後悔：刪 ≤ e·p（約 1 CP，約 10%）；不刪 ≥ g−e·p 或 S（最高約 100%）。模擬 n=12/0.10：A/T1 −1.0、B/T1 +21.6、T0 兩格 +87／+110。minimax 選刪。
其實不用刪時：誤刪成本 d·p（A 世界再加 g）。n=8/0.10 現行 89.6 對不刪 100.3（A/T1，−11%），B 持平；因為 `settle_sec=8` 悲觀。
建議：不改成不刪。保留現行「刪省最多秒、只刪到來得及」，把力氣放在讓「來不及」判得準：(a) 速度只往慢的方向線上校正；(b) `kibo.tune` 改輸出四世界×策略的最大後悔表。我試過、都沒贏的替代：最後一刻才刪（−7%~−80%）；只在樂觀估計也來不及才刪（n=8 A 世界 +11%，但 n=12 的 T0 世界 −20%~−50%）；被刪點可回補（持平）。粗版線上校正在規劃速度偏樂觀 1.7 倍時 +1%~+50%（T0 世界較大），速度對時 −2%~−12%，要先修偏差才可用。

## 3. 假機器人三項
1. 速度隨機化：每場速度抽 0.04–0.15、每段乘 lognormal σ≈0.25（現行單一速度，`fake_robot.py:22`）。兩行。改變：margin／settle／刪點門檻的最佳值（現行 tune 只在單一速度成立）。
2. 到點後殘餘振盪與漂移：位置＝目標＋A·e^(−t/τ)·cos＋OU 漂移（A 3–5 cm、τ≈3 s），用 `self.t` 算進 `pose()`／`notify_checkpoint`。改變：5 次連續穩定夠不夠、相機修正與 Lv2/Lv3 的效益。
3. 判分世界旗標：`goal_requires_all`、`timeout_keeps_points`、倍率形狀（線性／階梯）。十行。改變：第 2 題的整個結論；優先級最高。

## 4. 下一階段三件事
1. 第 3 項旗標＋最大後悔表。驗收：tune 對四世界輸出平均、最低、最大後悔；測試固定現行策略的最大後悔最小。
2. 只往慢校正的線上時間校正。驗收：真實 0.05–0.15、n=8/12，Goal 到達 ≥95%，速度對時損失 ≤3%。
3. 第一次上機不掛：只有 `FINISHED` 能提交（rulebook.txt:495），ROS 層沒跑過；失敗機率乘 100% 分數，大過任何調參。驗收：stub rospy／actionlib 把 `ros/user_node.py` 從 start 跑到 finish（與另一位委員重疊）。
停：再調 `hurry_sec`／margin／`target_level`（點數表是猜的，差異小於 10 次平均的標準誤，每場標準差 13–17 → 約 4–5%）；相機加功能；ideas #3／#5。

## 5. 上機第一小時
0–10 分：範本空跑到 FINISHED，記 n、goalpoint_id。
10–25：跑我們的節點一次。log 取每段 move 秒數（速度、起停）；JSON 取各 Lv 分數、Goal Score、Time Bonus 對 `duration_sec`、t0 偏差。改程式：速度偏離 >25% 改 `Speeds`；`duration_sec` 與 log 差 >3 s 調 t0／margin；notify 被拒 >10% 查 `camera_offset_m`。
25–45：兩場故意失敗：(a) 跳過中途點直奔 Goal，看 `goal.success`（定 A/B）；(b) 過 3 點後 sleep 超時，看 CP 分與 Time Bonus（定 T0/T1）。依結果改刪點門檻。
45–60：記到點後 5 秒位置補假機器人；同程式跑兩次比對 CP 清單，看 10 次條件是否固定（`未驗證`；固定也不可把清單寫死）。

## 值得記錄
- 四世界（A/B × T0/T1）：刪點在「真的來不及」時是 minimax，誤刪才是風險；結論取決於 π、τ，上機可各用一場測出。
- 假機器人 `score()` 逾時給 0（`fake_robot.py:162-163`）比規則書字面嚴，會讓所有保守參數看起來更好。
- 時間常數錯 2 倍的影響（3–5 倍）遠大於相機／Lv 目標（10–15%）；在假點數下 1 秒≈0.3 分、Lv3 CP≈40 秒。
- 試過沒贏：最後一刻才刪、雙閾值、可回補；粗版線上校正有偏差。
- 資格賽 10 次平均的標準誤約 4–5%，小於它的調參不可分辨。

---

# 回答 乙


RB＝rulebook.txt，MN＝manual.txt。

### 1. 檢討
站得住：任意順序（RB 2.2.3 步驟2a）故 Held-Karp 可用；送 checkpoint_passed 前自檢（MN 6.3.1）；對中以相機為原點（RB 圖2.3.2-1 的紅虛線連到標示 NavCam 的 IB2，但那是概念圖、證據弱；MN 6.3.1 文字寫「from the vehicle」，mission.py:96 的開關要留）。
最可能被推翻前三：
1. **Goal 必在 checkpoints 內。** checkpoints.py:98-99 不在就 raise，重試 3 次後 mission.py:280-283 直接 finish，10 場全 0。MN 6.3.1 範例 count=8 卻 goalpoint_id=12；RB 2.2.2#4⑥ 稱 Goal 是「固定值」，附錄#12 說位置在「game specification」（本 repo 沒有此文件，#4② RoundingCompletionPoint 同）。README:19「Goal＝最後一個 CheckPoint」是推論。檢驗：加「goal 不在清單」單測，改降級（log、跑完全部點、仍 finish）。
2. **假裁判把規則世界寫死。** scoring.py:27-31、fake_robot.py:160-164 假設 Pt_goal 不需其他點，且逾時整場 0。規則字面只說逾時「沒有完成回報分」（RB 2.2.3 步驟3），沒說 Pt_check 作廢；Lv 點數與倍率公式在 RB 附錄#16/#21 引用的 score calculation table，v1.1 PDF 裡沒有（查過 2.3 頁與內嵌圖清單）。ideas.md:53「低估穩定時間→整場 0 分」是假裁判的產物。檢驗：scoring 加兩個開關，同批場景重跑 tune。
3. **自檢閘門。** mission.py:262 自檢 Lv=0 就不回報；judge 原點若錯（見上矛盾），會放掉伺服器會給分的點。README:116「側偏 15 cm 掉 Lv1」只在相機原點模型成立。檢驗：第一次模擬器比 log 的 Lv 與 JSON level。
過度推論：spec.md:7、tune.py:5 把「穩定／最低分」當目標，但 RB 2.2.5 取 10 場平均就是要抹平運氣，目標是期望值，最低分只該當 bug 偵測。README:27「Goal 乘在全部分數上」不準：Pt_goal 是加進 Pt_all 再乘倍率（附錄#21），Goal 不是倍率。

### 2. 刪點避險
字面三讀：R1 每點都 scored 才有 Pt_goal；R2 每點都訪過；R3 只要 Goal 點通過且時限內回報。支持 R3：MN 4.3.2 JSON `goal.reason="goal checkpoint previously passed"`、MN 4.3.1 把 Goal Reached 與 CheckPoints Passed 分列。支持 R1/R2：RB 附錄#20、#12、2.2.1(5)「visited all」。reason 只是成功分支字串，排除不了 R1。
策略「先擠後刪、延後決定」：
a. 預算不足先降每點成本（目標降 Lv2/1、settle 估值降到約 5 取樣＋notify 1 s、略過 refine），仍裝不下才刪，一次刪最少。R1/R2 下每刪一點多丟 Pt_goal；R3 下降級只損 Lv 差，兩邊都不是最差。
b. 不在 t=0 憑猜的 0.1 m/s 刪點（mission.py:293、budget.py:87）；用前幾段實測時間校正速度再決定。
c. 擠壓幅度上限用 2×2（R1｜R3 × 逾時歸 0｜保留 Pt_check）掃描定，取最大遺憾最小者；Lv 點數比未公布，要掃比例。

### 3. 假機器人補三項
1. 擾動與到點後殘餘：RB 2.2.2#3/#5②、MN 6.3.2 有 DISTURBED；fake_robot.py:104 之後 true_pose 不再變，nav＝真值＋5 mm（:76-80）。最便宜：sleep() 內對 true_pose 加每場隨機脈衝＋回復彈簧，nav 另加固定偏差。改變：settle 取樣數與 8 s 估值、Lv3 值不值得追、相機修正在 fake 的優勢（它由真值造）。
2. 1 秒連續窗：RB 2.2.3 步驟2b、2.3.2 由伺服器持續判；fake_robot.py:134-137 是瞬時判再加 1 s。最便宜：notify 內以 0.25 s 取樣 1 s 窗、取最低級、任一樣本出界即 False。改變：notify_attempts、連續 5 次夠不夠。
3. 規則與時鐘開關：goal 前提、逾時倍率、clock_offset_sec（0–15 s，t0 比伺服器晚）、goal 不在清單。改變：margin_sec=25 與刪點結論。

### 4. 下一階段
1. parse 降級（1-1）。驗收：新單測 run_mission 仍跑完並 finish。
2. scoring 2×2 開關＋tune 四張表。驗收：列出四世界排名皆穩的變體，寫進 ideas.md。
3. 把第一小時實驗做成 MissionConfig 旗標（skip_one_waypoint、no_goal_notify、slow_move），log 帶絕對時戳。驗收：fake 下各旗標跑通、log 可對 JSON。
停：不再調 margin/hurry 等假參數；不擴 vision；決賽審查待資格賽後。

### 5. 第一小時
0. 先跑原範本到 FINISHED，看 JSON 全貌；記 Simulator Level 選項（MN 4.2.2，預賽 10 場用哪級未知）與「Illegal」（MN 4.3.2，判準未定義）。
1. 跑我們的程式（小場）：核 goalpoint_id 是否在清單、id 是否＝marker id、count。不符→改 parse。
2. 核 t0：mission.start/duration_sec 對 log elapsed（RB 三種說法：2.2.2#1 undock、附錄#7 Release 完成、/start 到來）。差>5 s→t0 前推。
3. 核判定：log 的 Lv 對 checkpoint_detail.level；不一致→試 camera_offset_m=(0,0,0)。
4. 實驗 A：跳過一個中途點，讀 goal.success／reason 與 Goal Score；再一場不通報任何點取 reason 字串→分 R1/R2/R3，改 budget 策略。
5. 實驗 B：故意逾時，看分數是否仍含 Pt_check；三場不同完成時間反推 Time Bonus 曲線。

### 值得記錄
- RB 附錄#16/#21 引用的 score calculation table 不在 v1.1 PDF（2.3 頁已看圖、附錄頁無內嵌圖）：Lv 點數、倍率公式、無回報倍率皆未公布。
- MN 4.3.2 JSON：goal 時間戳＝finish，reason「goal checkpoint previously passed」；僅成功分支，不能當 R3 定論。
- 對中原點證據矛盾：RB 圖2.3.2-1 畫 NavCam（概念圖），MN 6.3.1 文字寫 vehicle。
- RB #4②、#12、#13 的 RoundingCompletionPoint／game specification 本 repo 沒有。
- fake 把「Goal 不需其他點＋逾時歸 0」寫死，tune 結論須標註此前提。

---

# 回答 丙

# 某委員 第一輪（魔鬼代言人／軟體審計）

## 1. 最可能被推翻的前三項
**(1) 自判閘門是單點故障。** `notified = settled.level > 0 and self.notify(cp)`（mission.py:262）。level>0 同時需要三個未驗證前提：Navigation 的 header.stamp 有值且與 `rospy.Time.now()` 同時鐘（user_node.py:101-103；ros/README.md:21 自承）；nav 座標系等於 CheckPoint 座標系（手冊 6.3.2 只說 command 用 iss_body）；judge 的相機視差與滾轉定義。任一為錯就整場零通知，log 仍看似正常，測試還把「無導航不通知」當期望（test_mission_edge_cases.py:83-88）。另，手冊 6.5 寫「移動失敗不送到達通知」，mission.py:262 卻不看 `moved`。
檢驗：log 印 stamp、age、nav 位置；t0 時 nav 應約為 START_POSE (0.2,0,0)（rulebook 2.2.2-3）。

**(2) 沒有保底的 mission_finish。** run_mission 無 try/finally（mission.py:273-310），`_on_start` 只 log 例外（user_node.py:346-347），任何例外都丟掉 Goal 與倍率。具體洞：`_to_gray` 在 try 之外（user_node.py:168 對 171-175），影像長度不符或 cv2 import 失敗（226-227）會在第一次「不穩定」殺掉任務；中途點>11 時 `plan_route` 丟 ValueError（planner.py:164）；goal 不在 checkpoints[] 內時 parse 失敗三次就收工（checkpoints.py:98-99、mission.py:280-283），手冊範例沒證明 goal 在列表內（manual.txt:878 僅間接支持）。
檢驗：丟例外的 Robot 子類，斷言 `finished_at` 非 None；先讀 cheat_sheet.json（manual 2.5.2）。

**(3) 速度與逾時失配。** `move_timeout_sec=60`（mission.py:85）對規劃速度 0.1 m/s（planner.py:119）；marker 橫跨 x=0~7.2 m（field.py:310-321），5.9 m 一段約 59 s 加轉向，實速略低就 TIMEOUT、半途 cancel、再試又 60 s。fake 的 timeout 原地不動（fake_robot.py:91-93），實機不會。
檢驗：第一場印每段距離、秒數、結果。

另：`#!/usr/bin/env python`（user_node.py:1）在 Melodic 可能是 2.7（需查證），而 kibo 用 3.6 註記語法，會 SyntaxError、不設 ready、start 不發（api.md:13；manual 6.3.4）。pytest 從未在 3.6 跑過（pyproject.toml requires-python>=3.8）。

## 2. 刪點避險
證據：以團隊的 scenarios 與預設 BudgetConfig 重跑 `plan_within_budget`（我本機跑，非檔案內容，可重現）：10 點時 80%、12 點時 100% 在 t=0 就刪點（平均 2.1 個），依據是猜的 8 s 穩定、0.1 m/s、25 s 保險（budget.py:24-25,85-93）。刪點是高難度的常態。rulebook.txt:771-772（#20）與 745（#12）像在描述正常流程；結果 JSON 的 goal.reason 只提 goal checkpoint（manual.txt:878）。兩者都排除不了嚴格解讀，點數未公布（rules.md:45），離線算不出期望值。
策略：**延遲刪點**。t=0 不刪；每次選下一點前檢查「到該點＋穩定＋該點到 Goal ≤ 剩餘−margin」，不成立才跳過，優先跳繞路最大者；速度用實測滾動平均取代 0.1 常數。寬鬆解讀下與現行相近；嚴格解讀下保住「全數通過」的機會，而非系統性放棄 Pt_goal。風險是估計樂觀使 Goal 失守，用 margin 與「剩餘<1.3×到 Goal 估計就轉向 Goal」兜住。

## 3. 假機器人最該補的三項
**(1) 導航不等於真值。** `pose()` 回 true_pose＋5 mm 抖動（fake_robot.py:75-80），假裁判用 true_pose（:136），自判與裁判同源。補固定偏差、慢漂移、0.5 s 延遲（約 10 行）。改變：相機修正 +40% 的結論（ideas.md:196-210）與 settle 的鑑別力。
**(2) 到點後的殘餘運動。** move_to 設一次 true_pose 就永遠靜止（:97-105），settle 的 5 樣本與 8 s 估計無從檢驗。補 `pose_at(t)`：衰減振盪加微重力隨機衝量。改變：settle_sec、settle_samples、追 Lv3 值不值。
**(3) 不對稱雜訊與速度失配。** 絕對移動有 σ，相對移動全準（:115-120），相機優勢由構造決定；tune 預設速度 0.1 等於規劃速度（tune.py:299），規劃永遠正確。補：相對移動比例雜訊、每場速度乘 U(0.5,1.5)、timeout 停半途。改變：有無相機排名、move_timeout、max_move_attempts。
註：沒有資料的補強仍是猜，第一場 rosbag 後再擬合。

## 4. 下一階段三件事
1. **接線層煙霧測試**：stub 假 rospy／actionlib，測 `_run_action`（永不完成、REJECTED、cancel 才回）、`_call`（不回應的 proxy）、畸形影像。驗收：timeout／cancel／stop 路徑各有測試；python:3.6 容器可匯入（需查證）。
2. **保底 finish 與校準模式**：加 try/finally 與逐點 try/except；`calibrate=True` 時移動成功即通知一次並記錄回應與自判 Lv。驗收：例外 Robot、BlindRobot 兩個測試。
3. **補 log 欄位**（手冊 5.3）：nav stamp／age、目標對實際向量、每段秒數。驗收：單場 log 可算出速度、nav 延遲、settle 時間。

**該停**：用假常數（scoring.py）與假分布（scenarios.py）繼續調 tune；擴充 vision（約 119 行加 ROS 約 70 行，只在不穩定分支用到，建議 baseline 通過前不訂閱影像）；ideas #2、#3、#5；FigJam 與文件擴寫。
**虛假安全感**：假裁判與自判共用 `judge`（fake_robot.py:136、mission.py:193）；test_judge.py:35-39 的「側偏 15 cm＝Lv1」出自視差假設（機體中心算則約 16.7°＝Lv2）；test_mission.py:49-50 把真速度餵給規劃器；`marker_in_body` 與 mission 共用 `expected_marker_in_body`（fake_robot.py:111-113、mission.py:240），座標錯誤互相抵消。

## 5. 第一小時
1. 0-5 分：讀範本 shebang 並照抄；`diff` import；先交**未改的官方範本**一次，取得結果 JSON 格式與 cheat_sheet.json（核對 goal 是否在列表、點數、距離與傾角分布）。
2. 5-20 分：校準模式跑一場，依序驗：(a) ready／start、無 import 錯；(b) nav 對 START_POSE，不符先修座標，stamp 為 0 就改用接收時間；(c) 單段 v<0.08 m/s 就調 timeout；(d) 通知回應對 JSON level，不符試 `camera_offset_m=(0,0,0)`；(e) duration_sec 對我們的 elapsed，差>5 s 調 t0／margin。
3. 20-60 分：故意漏一個中途點跑一場，看 goal.success 定案寬鬆或嚴格；Time Bonus 反推倍率形狀。

## 值得記錄
1. 自判閘門串三個未驗證前提，任一為錯整場零通知；校準模式是最便宜的保險。
2. 預設參數下 10／12 點場景 80%／100% 在 t=0 刪點；延遲刪點在兩種解讀下都不差。
3. 評估表的「啟示」建立在 nav＝真值、相對移動無雜訊、規劃速度＝實速三個構造性假設上。
4. run_mission 無 finally，任何例外都丟 Goal；shebang 與 3.6 實跑未驗證。
5. START_POSE 與 cheat_sheet.json 可不花額度核對座標系與 Goal 結構。

---

# 回答 丁


## 1. 檢討
站得住：Robot seam、手冊範例驗座標慣例（README.md:113）、迴圈與重試有上限、不碰 wrench。最可能被推翻的前三：

1. **時間模型**（0.1 m/s、15°/s、平移轉動相加、settle 8 s、margin 25 s；planner.py:19-20,45、budget.py:24-25）。假機器人移動時間用同一個 `leg_seconds`（fake_robot.py:84），預算只被自己驗證。本機 20 場（規劃速度固定 0.1）：真速 0.05、12 點時 Goal 僅 10/20；真速 0.2 仍白刪 2 點，因 mission.py:299 刪了不復原。move_timeout 60 s（mission.py:85）也低於最長腿（marker 11 到 12 約 7.3 m，field.py:40-41，需 73 s）。檢驗：首次上機比對每段 move 秒數與 `route ~N s`。
2. **自我判定等於伺服器判定**。judge 用相機位置算對中（judge.py:27,82），手冊 6.3.1 卻寫「direction from the vehicle to the AR marker」（manual.txt:1696），較像機體中心。假機器人的 nav 就是真值加 5 mm 抖動（fake_robot.py:75-80），nav 偏差沒測到。以相機距 marker 0.36 m 計，側向偏 6.3 cm 就到 10°（Lv3 邊界），比位置球 10 cm 更緊。本機注入錯配（30 場、5 cm）：伺服器用機體、我們用相機平均 118.3，雙方皆機體 125.0。檢驗：逐點對照 log 的 Lv 與結果 JSON 的 level。
3. **「相機修正是最大改善」（ideas.md:53-55）是假模型產物**：`move_relative` 零誤差（fake_robot.py:115-120），`move_to` 每次重抽誤差（:104）。我替相對移動加誤差重跑 30 場：無相機 112.4；σ=0、2 cm、5 cm 分別 129.0、123.6、111.1，σ 與絕對移動同量級時增益消失。「只求 Lv2 較佳」同理。檢驗：現在即可重跑；上機比較 refine 前後 Lv。

以上本機數字皆出自假模型（20 到 30 場），只作方向證據；反證：換種子與分數常數重跑。

## 2. 刪點避險
無論 H1（Goal 只需到達）或 H2（需通過全部），沒在時限內回報都拿不到 Pt_goal（rulebook.txt:317-318、#20）；#12 也寫「after passing all CheckPoints」（:745），H2 字面證據不只一處。風險因此不在「刪不刪」，而在**依錯的速度提前刪**。本機 2×2（n=10、20 場、5 cm、10% 失敗；分數常數是佔位值，只看方向）：

| 真速 | 刪點 H1/H2 | 不刪 H1/H2 |
|---|---|---|
| 0.1 | 103.5/80.9 | 94.9/94.9 |
| 0.07 | 78.3/63.3 | 60.2/60.2 |
| 0.05 | 46.9/39.5 | 48.2/48.2 |

互有勝負。建議「晚刪、可還原、用實測速度」：(a) 每回合用全部未訪點重算；(b) 第一段後以實測速度（距離 ÷ 秒數扣 overhead）更新 Speeds，夾在 0.5 到 2 倍；(c) 估計仍來不及才一次刪一點。上界證據（規劃速度設成真速）：真速 0.05 時 H1 46.9 升 72.5（n=10）、57.8 升 88.7（n=12）；真速 0.2 時 H2 105 升 130。完整對沖策略我尚未跑。

## 3. 假機器人最該補的三項（外加一項免費）
0. **逾時零分**（fake_robot.py:162-163）：規則 2.2.3 只說完成回報不給分。它讓「不刪」在本機顯得災難（真速 0.05 時 0.0，保留已過點分則 48.2）。改成參數：late 倍率 ∈ {0,1}。改變 Q2 結論與 tune 的「穩定估 4s 危險」。
1. **到點後動力學與微重力**：現在到點後凍結（:104），notify 只判單一瞬間（:132-137）。補：位置 = 目標 + 衰減振盪 + ½·a_d·Δt²，a_d 每場抽樣，掃 0、1e-3、5e-3 m/s²（量級需查證）；notify 檢查最近 1 s 全部樣本；settle 也看 Navigation.twist（manual.txt:1781）。改變 settle_sec、settle_samples、Lv2 對 Lv3、hurry_sec。
2. **nav 不等於真值、相機不完美**：nav = 真值 + 慢漂偏差（1 到 3 cm，需查證）+ 延遲，伺服器判真值；偵測率隨距離視角下降（marker 僅 2 cm，manual 5.13.1）；相對移動加與絕對移動同量級的誤差。改變相機修正值不值得、stable 是否可信。
3. **運動時間與完成語意**：fake 與 planner 解耦；梯形速度（短腿由加速度主導）、平移旋轉並行；result 比停穩早晚 0 到 3 s（對照 `/ctl/status` 到 KEEP_POSE，manual.txt:1936）；TIMEOUT 留下中途位置（現為原地不動，:91-93）。改變 Speeds、move_timeout、settle 與 margin。

## 4. 下一階段與該停的事
1. **策略穩健化**：第 2 點 (a)(b)(c)、move_timeout = max(60, 2×估計腿)、late 與 Goal 規則參數化。驗收：{真速 0.05、0.1、0.2}×{H1,H2}×{late 0,1} 表中，分數不輸 oracle 速度版超過 10%，Goal 率不低於它。
2. **假機器人補第 3 點 0 到 3 項最小版**，`kibo.tune` 輸出跨 ≥ 4 組假設的名次表。驗收：只有名次不變的結論進 README 第 5 節，其餘標 fake-sensitive。
3. **飛行記錄器與校準腳本**：RosRobot 記 nav、`/ctl/status`、各 action 的 send 到 result 秒數、checkpoint_passed 的 message、camera_info；`kibo.calib` 把 log 轉成 FakeRobotConfig。驗收：用 FakeRobot 的 log 往返，參數還原誤差 < 10%。

**該停**：手調 margin、hurry、settle（103.5 對 114.2 小於假設不確定度）；擴充 vision.py；ideas #3、#5、wrench；文件與圖。

## 5. 上機第一小時
- **0 到 10 分**：官方範本原樣跑，讀 `cheat_sheet.json` 與結果 JSON。Goal 是否在 checkpoints 內（checkpoints.py:98-99 不符即 ValueError，走 "no checkpoints" 整場 0 分，mission.py:280-283）；count 含不含 Goal；距離、傾角、滾轉分布對 scenarios.py:38-51 的猜測是否成立。
- **10 到 25 分**：只收資料不飛：nav 頻率、frame_id、`header.stamp` 是否有值（user_node.py:101，空值使 pose() 永遠 None）、靜止 twist、`/ctl/status` 序列（RELEASE 何時結束）、camera_info、image encoding 與 fps、是否模擬時間；有無影像訂閱的 nav 回呼間隔差（user_node.py:80 未設 queue_size，負載需查證）。stamp 空則拿掉新鮮度檢查；start 早於 RELEASE 結束則等狀態再起算 t0。
- **25 到 40 分**：真程式跑一次，逐項核：(a) move 秒數與估計差 > 30% 改 Speeds 或梯形；(b) TERMINATE_SUCCESS 與 KEEP_POSE、|v| 有落差，settle 改等狀態；(c) 我們的 Lv 與 level 錯配 > 10% 改 camera_offset_m，伺服器恆較低代表 nav 偏差，相機修正升為主線；(d) `duration_sec` 與 elapsed 差 > 3 s 改 t0 或 margin；(e) 偵測率 < 80% 或 solvePnP 與 nav 推算差 > 3 cm 即停用 camera_fix。
- **40 到 60 分**：兩次探針：少去一點看 `goal.success`（H1/H2）；過一點後空等到逾時看 late 規則與 Time Bonus。三個以上不同完成時間才擬合得出 Mag_clear。

## 值得記錄
1. 相機「最大改善」只在相對移動零誤差時成立（σ=5 cm 增益消失）；tune 結論須跨假設驗證才算數。
2. fake 的「逾時=0」是假設（規則 2.2.3 只說完成回報不給分），它造成「必須刪點」的印象。
3. 手冊 6.3.1 的 centering 是「from the vehicle」，與 judge.py 的相機位置假設相反，首次上機核對。
4. 規劃速度是第一敏感參數：真速 0.05 時 12 點 Goal 僅 10/20；速度校準的 oracle 上界約 +25 到 +30 分。
5. 刪掉的點不復原（mission.py:299）、60 s move_timeout 低於長腿，是上機前可修的小缺陷。
