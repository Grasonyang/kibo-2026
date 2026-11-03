# 委員 D 第一輪（魔鬼代言人／軟體審計）

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
