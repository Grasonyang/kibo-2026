# 委員 D 第二輪（丙是我第一輪）

## 1. 排名（證據站得住、對主席決策有用）
1. **甲**：唯一把候選策略實跑並報告「沒贏」的（最後一刻才刪 −7%~−80%、可回補持平）。ΔEV／minimax 是結構論證，不靠假點數。弱點是數字全在假模型，ROS 層只佔一條。
2. **乙**：指出一條能確定把 10 場歸零的路徑。手冊範例 count=8 卻 goalpoint_id=12（manual.txt:1646,1677），而 checkpoints.py:98-99 找不到 Goal 就 raise，mission.py:280-283 隨即收工。我核對屬實。Q2 沒數字、Q3 偏推測。
3. **丁**：缺陷具體（mission.py:299 刪了不復原、move_timeout 60 s 低於 73 s 長腿），2×2 表有用。但表「互有勝負」不產出決策，「晚刪」自承未跑，`kibo.calib` 往返在無資料時過度工程。
4. **丙（我）**：失敗路徑清單有用，Q1(1) 過度，Q2 延遲刪點沒有數字，還被甲的反例挑戰。

## 2. 修正自己
- 「自判閘門任一前提錯就整場零通知」過度。只有 stamp 為 0 或座標系大錯才全零。judge 的相機偏移錯只是部分降級（丁假模型：125.0→118.3，約 −5%）。Lv1 門檻寬（0.3 m／30°，manual.txt:1655-1671）。
- 「延遲刪點兩種解讀下都不差」撤回，沒有實跑，且甲有反例。能採納的只有「用實測速度修正估計」，四份都同意速度是第一敏感參數。
- 「10／12 點場景 80%／100% 在 t=0 刪點」來自我們猜的 scenarios、8 s、25 s，只證明估計偏悲觀，不證明常態。
- shebang 可能是 2.7：手冊只說 3.6.9（manual.txt:298），範本首行我沒看過，降為「`head -1 user_template.py`」的 30 秒檢查。
- 「mission.py:262 不看 moved 違反 6.5」降級。伺服器才是裁判（manual.txt:1721-1725），多通報最多浪費約 1 s，還是取得伺服器判定的便宜管道。

## 3. 四份都沒提的盲點
1. **規劃本身吃任務時鐘，且沒量過**。spec.md:42 寫「毫秒級」，唯一依據是 test_planner.py:46-51 的 <1 s。n=11 時 Held-Karp 約 n(n−1)2^(n−2)≈56k 次 cost 呼叫（planner.py:74-90）。budget.py:84-93 每刪一點重算，mission.py:289-301 每回合重算。累積數秒到十餘秒、慢 host 更久，對 25 s margin 不是零（未驗證）。檢驗：在 python:3.6 容器計時 n=11 的 `plan_within_budget`。便宜修法：先算一次 n×n 成本矩陣。
2. **上機的可觀測性只有 log 一條線**。Web 模擬器只回結果 JSON 與 rospy.loginfo（manual.txt:812-827），系統與感測資料不給。第一次上機 log 寫了什麼，就是你全部的資料。四份的第一小時各排 5–7 場實驗，每場 5 分鐘（rules.md:25）加啟動，大概超過 40 分鐘（啟動耗時未驗證）。實驗要併進旗標：一場同時「跳一點」＋「level 0 也通報一次」。
3. **「level 0 也通報一次」是零成本探針**。規則書 grep 無 penalty／deduct 字樣（未驗證有無隱含處罰，「Illegal」判準未定義，manual.txt:838）。
4. **模擬時鐘**。結果 JSON 時戳從 1970 起算（manual.txt:863-888），很可能是 sim time。`_call` 用牆鐘 `Event.wait`（user_node.py:285），其餘用 `rospy` 時間，RTF≠1 時逾時單位不一致（需查證 `/use_sim_time`）。
5. **過度工程**。fake→tune→參數是封閉迴圈。乙丙丁都要求再加保真度，但沒有資料時那只是敏感度掃描，不是預測，不該寫進 README 第 5 節當結論。

## 4. 建議主席採納的三條
1. **「不死、必 finish」硬化**（乙＋丙）。
   - 內容：解析降級（Goal 不在清單或 count 不符 → log 並照飛、仍 finish）；超過 11 個中途點時降級而非 raise；`run_mission` try/finally 保證 `mission_finish`。
   - 驗收：用手冊範例（count=8、goal=12）寫單測；丟例外的 Robot 斷言 `finished_at` 非 None；12 個中途點不例外；stub rospy／actionlib 把 `ros/user_node.py` 從 start 跑到 finish。
2. **校準與飛行記錄合一**（乙丙丁）。
   - 內容：log 每段 move 秒數、nav stamp／age、notify 回應 message、絕對時戳；MissionConfig 旗標 `notify_even_if_level0`、`skip_one`、`late`。
   - 驗收：fake 下單場 log 能算出速度、settle 秒數、nav age；各旗標跑通。
3. **只修速度估計，不改刪點策略**（甲＋丁的小缺陷）。
   - 內容：速度只往慢校正、夾在 0.5–1 倍；`move_timeout=max(60, 2×估計腿)`。不採「最後一刻刪」「可回補」。
   - 驗收：甲的設定（真速 0.05–0.15、n=8/12、種子 40 場）Goal 到達 ≥95%，速度對時損失 ≤3%，最大後悔不劣於現行。

## 值得記錄
- 手冊範例 count=8 vs goalpoint_id=12 與 checkpoints.py:98-99 的 raise 構成確定性歸零風險。
- 規劃計算時間吃任務時鐘，「毫秒級」只有 <1 s 測試佐證。
- Web 模擬器只給結果 JSON 與 user log，log 欄位設計等於資料採集設計。
- 延遲刪點在甲的實測裡沒贏；「用實測速度修估計」才是四份共識。
