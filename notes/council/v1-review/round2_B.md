## 委員 B 第二輪（我第一輪對應「丁」）

### 1. 排名
1. **甲**：四世界（A/B × T0/T1）加 ΔEV 公式，把 Q2 變成可算的最大後悔問題。它也列出試過沒贏的替代案（最後一刻刪、雙閾值、可回補），主席可以直接用。點數常數是猜的，作者已自承只看方向。
2. **丙**：指出第一場最可能整場報廢的單點故障。mission.py:262 的自判閘門串三個未驗證前提，run_mission（mission.py:273-310）沒有 finally，每一項都附便宜的檢驗。「預設參數下 10 點場景 80% 在 t=0 刪點」可重現，但仍是假模型的產物。
3. **乙**：全程以規則書字面為據。RB 附錄 #16/#21 引用的 score table 不在 PDF，所以 Lv 點數與倍率沒有公布，這點最有價值。Goal 不在清單的洞（checkpoints.py:98-99）也抓得準。動力學與感測較少。
4. **丁（我）**：速度敏感度與「相機增益依賴相對移動零誤差」有數字。但全部來自與 planner 共用 `leg_seconds` 的假機器人（fake_robot.py:84），Q2 沒跑完對沖，且有下列過度措辭。

### 2. 我要修正的措辭
- **「手冊較像機體中心」過度。** manual.txt:1695-1696 的「camera's line of sight 與 direction from the vehicle to the marker」並列，乙指出 RB 圖 2.3.2-1 畫的是 NavCam，兩邊證據互相矛盾。應改成「未定，兩種都要能切換」。「側偏 6.3 cm 即 10°」只在相機距 0.36 m 且 Lv3=10° 時成立。bands 其實由 response 解析（checkpoints.py:79-81；範例 10/20/30，manual.txt:1655-1671），不是常數。
- **「½·a_d·Δt²」假設自由漂移。** KEEP_POSE 是控制狀態（manual.txt:1936、1856），是否主動抗擾 `未驗證`。若是閉迴路，殘餘應是「彈簧阻尼加隨機脈衝」，偏差有界。t² 模型會高估殘餘，使 hurry、settle 的結論偏保守。
- **「晚刪、可還原」要收窄。** 甲試過最後一刻才刪，結果 −7%~−80%，部分反證我的說法。我只該主張「用實測速度重算後再刪」。
- **「oracle 上界 +25~30」只是敏感度。** 0.05 與 0.2 是我挑的端點，不代表真實速度範圍。
- **「增益消失」要降級。** 我加的 σ=5 cm 是任意值，只能說結論不可轉移，不能說相機無用。

### 3. 四份都沒提的盲點
- **settle 可能數到重複樣本。** `pose()` 回快取的最新 nav，沒有序號（user_node.py:96-106），settle 每 0.25 s 取一次（mission.py:187-197）。若 nav 發布頻率低於 4 Hz（`未驗證`），5 個「連續達標」可能是同一則訊息。對策：只計 header.stamp 變新的樣本，並加 |twist|（manual.txt:1781）。
- **`Navigation.status` 完全沒用到。** manual.txt:1783 只宣告型別，沒有定義。但 Result 有 TERMINATE_INVALID_NAV（manual.txt:1804），表示伺服器有 nav 有效性概念。第一場先 log 它。
- **微重力是每場隨機且「僅模擬器」。** 見 rulebook.txt:178-200 與 351-357，10 場分 A/B 兩種擾動條件。所以不能用單場校準。擾動也可能作用在飛行中，影響腿時間與 TIMEOUT，不只到點後。`/ctl/status` 有 DISTURBED=2 與 KEEPING_POSE_BY_COLLISION=11（manual.txt:1935-1937），第一場要記錄。
- **planner 沒有每腿固定起停時間。** planner.py:40-45 只有距離除以速度加角度除以角速度，fake 卻有 `move_overhead_sec=3`（fake_robot.py:23）。整體速度比例錯不改變路線排序，固定起停成本會改變排序和刪點節省量（budget.py:63）。
- **直線規劃假設無障礙。** 我只在規則書搜尋 obstacle/keep-out 沒找到，沒查手冊，`未驗證`。碰撞狀態 11 存在，長腿出現 TERMINATE_ABORTED 時要查。
- **mission.py:262 不看 `moved`**，而手冊 6.5 寫「移動失敗不送到達通知」（manual.txt:2324-2326）。這比較是 JAXA 安全審查問題，不是分數問題。

### 4. 對裁決的建議（3 條）
1. **保底與降級**（乙＋丙）。Goal 不在清單時降級為記 log、跑完全部點、仍 finish；run_mission 加 try/finally 與逐點 try/except。
   - 驗收：兩個單測。Robot 子類丟例外，或 goal 不在清單，`finished_at` 都非 None。
2. **速度×規則世界的後悔表**（甲＋我）。真速 {0.05, 0.1, 0.2} × A/B × T0/T1，比較「現行」與「實測速度重算（只往慢校正）」兩種策略。
   - 驗收：後者的 Goal 到達率不低於現行，最大後悔不大於現行。
   - 結論只有四格名次不變才進 README 第 5 節。
3. **校準與記錄模式**（丙＋丁）。log nav stamp/age/status、每段秒數、`/ctl/status.type`。settle 只計新 stamp 的樣本並加 twist。
   - 驗收：fake 單場 log 能算出速度、nav 延遲、重複樣本比例；新增「重複樣本不算穩定」單測。

### 值得記錄
- KEEP_POSE 是否主動抗擾決定殘餘模型是「有界振盪」還是「t² 漂移」，首場要驗。
- 微重力每場隨機（A/B），不能單場校準。
- `Navigation.status` 在手冊裡沒有定義，也沒被讀取。
- 整體速度比例錯不改路線排序，固定起停時間才會。
