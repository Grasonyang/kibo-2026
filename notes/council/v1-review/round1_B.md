## 委員 B（自由飛行機器人控制工程師）第一輪

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
