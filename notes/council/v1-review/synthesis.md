# Synthesis：v1-review council（2026-11-04）

主席：主 session。四位委員：A 規則律師、B 控制工程師、C 競賽策略者、D 魔鬼代言人。兩輪完整，匿名互評（甲=C、乙=A、丙=D、丁=B）。

## 互評結果（名次加總，越小越前）

| 委員 | 名次和 | 一句話 |
|---|---|---|
| C 競賽策略者 | 7 | 四世界 × 最大後悔把刪點問題變成可算的；實跑了替代策略並報告沒贏 |
| B 控制工程師 | 10 | 速度敏感度與「相機增益靠相對移動零誤差」有數字；主席重現 |
| A 規則律師 | 11 | 分數表不在 PDF、Goal 不在清單的歸零路徑、探針不能留在決賽程式 |
| D 魔鬼代言人 | 12 | 閘門單點故障、無 finally、規劃吃時鐘；第二輪自己撤回了兩條過度主張 |

四位都把自己排在後段，第二輪的修正都有具體撤回，互評可信。

## 共識（四份一致）

1. **速度是第一敏感參數**，相機與 Lv 目標都是次要（+10–15%，且依假模型）。真速 0.05 時 12 點 Goal 僅 10/20，規劃若知道真速可到 18/20、分數 38 → 85（主席重現）。
2. **刪點策略保留**（只刪到來得及、省最多秒先刪），**不採**「最後一刻才刪」「可回補」（C 實跑沒贏；主席重現四世界表：刪點只在 A/T1 小輸 2–6 分，其餘大勝）。要改的是**估計的準度**：用實測速度校正（只往慢的方向）、`move_timeout` 隨估計腿長放大。
3. **「不死、必 finish」是第一優先**：Goal 不在清單、count 不符、單點欄位缺漏、>11 中途點、任何例外，都不能讓 `mission_finish` 沒被呼叫。
4. **假裁判的規則假設要做成旗標**（Goal 需全點 A/B、逾時保留已得分 T0/T1），tune 要跨世界輸出；只有名次跨世界不變的結論才能寫進 README 第 5 節，其餘標「fake-sensitive」。
5. **第一次上機的 log 就是全部資料**：每段 move 秒數、nav stamp／age／status、`/ctl/status.type`、notify 回應 message、絕對時戳。探針旗標（跳一點、level 0 也通報、故意逾時）預設關閉，決賽程式剝除（規則書 4.2.4 只能跑一次）。
6. **停**：在假模型上調 margin／hurry／target_level；擴充 vision；ideas #3、#5；再畫圖與擴寫文件。

## 第二輪新盲點（採納）

- settle 可能數到同一則 nav 訊息（B）：只計 stamp 變新的樣本。
- `_call` 用牆鐘 `Event.wait`，其餘用 rospy 時間，sim time 下單位不一致（D）：改用 rospy 時間輪詢。
- 規劃吃任務時鐘（D）：本機 12 點最差 0.14 s／回合，TX2 可能 1 s；預先算成本矩陣。
- 手冊 4.3.1 有 N/A（不評分）的 CheckPoint（A）：parse 要容忍缺欄位，單點壞不整批壞。
- 計時終點是回報「開始」（A）：Goal 的 notify 重試會扣 t；Goal 的 notify 不要多等。
- 手冊 6.5「移動失敗不送到達通知」（A、B）：`visit` 改成沒有成功移動就不回報（校準模式可覆寫）。
- 可重複提交、只有 FINISHED 能交（C）：探針便宜，但期限前一定要有一份 FINISHED。

## 查證表（第一輪的見 verification.md；第二輪新增）

| 說法 | 結果 | 依據 |
|---|---|---|
| 手冊 4.3.1：CheckPoint 數量與位置依難度變，N/A 不評分（A） | 屬實 | manual.txt:774-775 |
| 手冊 4.3.1 Tip：先 Passed 與 Goal Reached，再 Time Bonus（A） | 屬實 | manual.txt:796-797 |
| 規則書 4.2.5：逾時程式被關閉、長時間不動可能提前結束（C） | 屬實（決賽章節） | rulebook.txt:586-594 |
| 手冊範例 count=8、goalpoint_id=12（A、C、D） | 屬實，但不證明 Goal 不在清單（id 即 marker 編號） | manual.txt:1646、1677 |
| 四世界下刪點是 minimax（C） | 屬實 | 主席重現（verification.md） |
| 規劃每回合數秒（D） | 部分屬實：本機 0.14 s，TX2 未測 | 主席量測 |
| 相機增益在相對移動 σ=5 cm 時消失（B） | 屬實（方向） | 主席重現 |
| `/use_sim_time`、shebang、nav 頻率、KEEP_POSE 是否抗擾、每日跑次配額 | 未驗證 | 上機核對清單 |

## 裁決（status: open，等使用者確認）

| # | 採納 | Ticket | 驗收 |
|---|---|---|---|
| R1 | 不死保底：parse 降級（Goal 不在清單→用最後一點當終點並 log；count 不符→以實際清單為準；單點欄位缺→跳過該點）；>11 中途點→改最近鄰排序不 raise；`run_mission` 用 try/finally 保證 `mission_finish`；`_on_start` 的例外也 finish | T14 | 手冊範例（count=8、goal=12）、缺 Goal、缺欄位、丟例外的 Robot、12 中途點：五個測試都 `finished_at` 非 None |
| R2 | 速度線上校正：每段移動成功後以「距離÷秒數」更新 `Speeds.linear`，只往慢校正、夾在預設的 0.5–1.0 倍；`move_timeout = max(60, 2×估計腿秒)`；成本矩陣預先算 | T15 | 真速 {0.05, 0.1, 0.2} × n {8, 12}：Goal 到達率不低於現行、與 oracle 速度版差 ≤10%、速度正確時損失 ≤3% |
| R3 | 規則世界旗標：`Scoring.goal_requires_all`、`timeout_keeps_points`；`kibo.tune` 輸出四世界的平均與最大後悔；README 第 5 節只留跨世界名次不變的結論 | T16 | tune 印四張表；README 的「啟示」逐條標 fake-sensitive 或移除 |
| R4 | 校準與飛行記錄：log 加每段秒數、nav stamp／age／status、`/ctl/status.type`、notify message、絕對時戳；`MissionConfig` 探針旗標 `notify_even_if_level0`、`skip_one_waypoint`、`deliberate_late`（預設關）；settle 只計新 stamp 的樣本；`visit` 沒成功移動就不回報；`_call` 改 rospy 時間輪詢 | T17 | 假機器人單場 log 能算出速度與 settle 秒數；重複樣本不算穩定的測試；各旗標跑通；ROS 端 vermin／ruff 過 |
| R5 | 上機劇本改寫（ros/README）：0 先交未改的官方範本取得 cheat_sheet.json 與結果 JSON；1 只收資料；2 校準模式一場；3 視刪點是否觸發才跑探針；每項寫「驗到什麼就改什麼」 | T18 | 文件 |
| R6 | 停止：假模型調參、vision 擴充、ideas #3/#5、圖與文件擴寫 | — | — |

不採納：「延遲刪點／最後一刻才刪」「可回補」（C 實跑沒贏、主席未重現正面結果）；拿掉自判閘門（手冊 6.3.1 要求先確認穩定）；`kibo.calib` log 往返還原（無資料時過度工程，B 自承）。

## 給使用者的選項

- 同意 R1–R6 → 把 Basic Memory 決策改 `accepted`。
- 不同意 R2 的「只往慢校正」→ 改成雙向校正（風險：第一段偏快會讓估計樂觀）。
- 不同意 R6 → 說明要保留哪一項。
