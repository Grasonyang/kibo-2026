## A（規則律師）第二輪

### 1. 排名（證據是否站得住 × 對主席決策是否有用）
1. **甲**：把 Q2 化成「四世界（A/B×T0/T1）× 最大後悔」，並實跑四種替代策略。數字全來自猜的分數常數，它自己有註明。它引的 rulebook.txt:735-737 是我漏掉的。
2. **丁**：唯一做出 H1/H2×速度對照表（結果互有勝負），並給出 oracle 對照的驗收。指出 mission.py:299 刪點不復原、move_timeout 低於長腿。完整對沖策略尚未跑。
3. **丙**：代碼事實可逐條驗（mission.py:262 閘門、run_mission 無 finally），對第一次上機最實用。Q2、Q3 只有論述，shebang 標「需查證」。
4. **乙（我）**：規則結構有用（分數表缺漏、R1/R2/R3）。完全沒有量化，「先擠後刪」只是論證、沒被模擬，且有三處過度（見 2）。

### 2. 修正
- **「Goal 不在清單」不該排第一。**
  - 文字沒有證明 Goal 不在清單。manual.txt:878 的 `goal checkpoint previously passed` 反而暗示 Goal 本身是 checkpoint。
  - manual.txt:1646/1677 的 count=8、id=12 只是節錄範例，id 未必連續。manual.txt:774 說 CP 數量與位置依難度而異，也有 N/A。
  - 正確說法是「機率低、一旦發生整場歸零、修復最便宜」。
- **「對中以相機為原點」不能放在「站得住」。**
  - manual.txt:1693-1697 的位置與對中都寫 vehicle。相機在機頭前 0.14 m（manual.txt:1213-1217）。
  - rulebook 圖 2.3.2-1 只是概念圖。這一項是未決問題，不是站得住的決策。
- **「逾時整場 0 是假裁判的產物」太肯定，甲的「字面是 T1」也過頭。**
  - #8（rulebook.txt:735-737）只說 Finish 之後的動作無效，不否定之前的 Pt_check。
  - 但 Mag_clear 由回報時的剩餘時間決定（#14、#17、2.3.1:402-407）。沒回報時倍率未定義，T0 無法由文字排除。
- 「兩邊都不是最差」只是論證。甲試過「只在樂觀估計也來不及才刪」，在 n=12 的 T0 世界輸 20%~50%。要以 2×2 掃描為準。

### 3. 盲點（字面為據）
1. **CP 數量與 N/A。** manual.txt:774-775：數量與位置隨難度變，N/A 的點「不評分」。
   - 若 get_checkpoints 含 N/A 點，訪問它們純屬浪費（未驗證）。
   - parse 是嚴格的（checkpoints.py:93-99），任一不合就整批作廢。
   - 預賽 10 場用哪級（manual.txt:679-737）不明，n=8/12 是猜的。
2. **計時終點是回報「開始」那刻。** rulebook.txt:735-737。
   - Goal 的 checkpoint_passed 必須在 mission_finished 之前。
   - Goal 的 notify 重試所花的時間，會直接扣 t（#14）。
3. **官方優先序。** manual.txt:796-797：先 CheckPoints Passed 與 Goal Reached，再 Time Bonus。支持「保 Goal」，但兩者分列，仍決定不了 R1/R2/R3。
4. **自判閘門是手冊規定的設計。** manual.txt:1723-1725 要求確認穩定後才送；6.5（manual.txt:2324-2326）要求移動失敗不送。
   - 丙說的單點故障成立，但解法是「校準」，不是拿掉閘門。
   - mission.py:262 不看 `moved`，與 6.5 不一致。
5. **探針不能留在決賽程式。** rulebook.txt:577-594：決賽只能跑一次，卡住或長時間不動會被系統判結束，另有 JAXA 審查（AGENTS.md）。
   - 故意漏點、故意逾時的旗標只能留在資格賽用的分支，預設關閉並剝除。
6. **假機器人的擾動設計。** rulebook.txt:350-357 的圖：10 場有 3 種隨機條件，擾動型態只有 A、A、B。圖的文字有亂碼，標「未驗證」。

### 4. 建議主席採納的 3 條
1. **保底：parse 降級加 try/finally 保證 mission_finish**（乙、丙、丁都提到）。
   - 來源：mission.py:273-310、checkpoints.py:98-99。
   - 驗收：單測涵蓋「Goal 不在清單」「count≠len」「單點欄位缺漏」「Robot 任一方法丟例外」。四種情況下 `mission_finish` 都被呼叫，且 `finished_at` 非 None。
2. **規則世界旗標（A/B×T0/T1）加 `kibo.tune` 最大後悔表，上機用兩場探針定案**（甲、乙、丁）。
   - 來源：fake_robot.py:162-163、scoring.py。
   - 驗收：tune 對四世界輸出平均與最大後悔；只有名次跨世界不變的結論才進 README 第 5 節。
   - 上機：漏一個中途點看 `goal.success`、`reason`；過 k 點後逾時看 CP 分與 Time Bonus。
3. **速度實測校正（夾 0.5–2×）加 move_timeout=max(60, 2×估計腿)，刪點改晚刪、可還原**（甲、丁收斂）。
   - 來源：mission.py:85、mission.py:299、budget.py:24-26。
   - 驗收：丁的格子 {0.05, 0.1, 0.2}×{H1, H2}×{late 0, 1} 中，分數不輸 oracle 速度版超過 10%，Goal 率不低於它；速度正確時損失 ≤3%（甲）。

另有零成本的一步：上機先交未改的官方範本，讀 `cheat_sheet.json`（manual.txt:524）。可核對 Goal 是否在清單、N/A 點、CP 數量，四份回答都需要這份資料。

### 值得記錄
- manual.txt:774：CP 數量與位置隨難度變，含 N/A（不評分）。n=8/12 與「全部都訪」都是假設。
- 「逾時＝0」的 T0/T1 無法由規則文字決定：#8 只作廢 Finish 之後的動作，但沒回報時 Mag_clear 未定義。
- 計時終點是回報開始（#8）；Goal 的 notify 必在 mission_finished 之前，其耗時扣 t。
- 對中原點的文字（manual.txt:1693-1697 寫 vehicle）與概念圖（NavCam）衝突，屬未決。
- 決賽只能跑一次（rulebook.txt:577-594）：實驗探針只能在資格賽模擬器做，不能留在決賽程式。
