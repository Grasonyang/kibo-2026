## A（規則律師）第一輪

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
