# 從零開始看懂這份解法

這份文件假設你沒有機器人、ROS 或比賽背景。看完你會知道：比賽在玩什麼、我們打算怎麼贏、
程式碼怎麼分、怎麼在自己電腦上跑一場、還有哪些事沒做。

圖都在這個 FigJam 板：<https://www.figma.com/board/dcZJJmt8eCZj1jt3yjR3wz>（比賽流程、程式架構、任務狀態機、評分邏輯）。板上有兩張狀態機圖，以標題帶「審查後更新」的那張為準。

## 1. 比賽在玩什麼

國際太空站（ISS）的日本實驗艙「Kibo」裡有一顆會飛的球形機器人 **Int-Ball2**（IB2）。
比賽是：**寫一支程式，讓 IB2 在 5 分鐘內自己飛去幾個指定地點、用相機對準牆上的小方塊圖案
（AR marker）、最後飛到終點回報。** 資格賽在 JAXA 的模擬器上跑，決賽是太空站上的真機。

名詞（完整版在 [GLOSSARY.md](../../GLOSSARY.md)）：

- **AR marker**：2 公分的黑白方塊圖案，艙內固定 12 個，位置事先知道。
- **CheckPoint**：以某個 marker 為基準、**每次隨機**產生的一個「該站的位置」加「該朝的方向」。
  一場有 6 到 12 個。程式開始時可以跟伺服器要這份清單。
- **GoalPoint**：最後一個 CheckPoint，到了之後要送「完成回報」，計時才停。

怎麼算分（圖「CheckPoint 評分邏輯」）：到一個 CheckPoint 時，伺服器看三件事：
**位置**夠不夠近、相機有沒有**對中** marker、繞視線軸的**滾轉**對不對。每件事有三級餘裕
（Lv3 最嚴、分最高），三件事**取最低的那一級**給分，任一件超出就 0 分，而且要維持 1 秒。
全部加起來，再**乘上剩餘時間的倍率**（最多 2 倍）。

兩個重要後果：
1. 終點（Goal）的分數與倍率是乘在**全部**分數上的，**來不及到終點比少去一個點慘得多**。
2. 程式會被自動跑 **10 次**取平均，每次 CheckPoint 位置都不同，所以要的是**每次都穩**。

## 2. 我們怎麼解（一句話）

> 先算出最省時間的拜訪順序；每到一點就停下來、自己先檢查三個條件都達標才回報；
> 隨時盯著剩餘時間，來不及就放棄最不划算的點，確保一定到終點。

對應到圖「比賽流程」與「任務狀態機」。分解：

| 步驟 | 做什麼 | 程式在哪 |
|---|---|---|
| 讀清單 | 跟伺服器要 CheckPoint，解析成程式用的結構 | `src/kibo/checkpoints.py` |
| 排順序 | 從起點出發、每點各去一次、終點收尾，總時間最短。點數最多 12，用精確解 | `src/kibo/planner.py` |
| 估時間 | 一次移動要幾秒：先平移再轉向，短程主要花在加減速，照控制器原始碼算 | `src/kibo/motion.py` |
| 看時間 | 估計整條路要多久，加上保險，超過剩餘時間就改去「時間內能去最多點」的一組；終點永不刪 | `src/kibo/budget.py` |
| 移動 | 叫機器人飛到指定位置與姿態，每點最多嘗試 2 次 | `src/kibo/mission.py` |
| 自我檢查 | 照官方評分的算式算三個條件各幾級（`judge.py`）；在容差內連續待滿 1 秒才算穩（`settle.py`） | `src/kibo/judge.py`、`src/kibo/settle.py` |
| 回報 | 告訴伺服器「我到了」。每個點官方只判第一次，所以沒把握不送 | `src/kibo/mission.py` |
| 收尾 | 到終點、回報完成 | `src/kibo/mission.py` |

## 3. 程式碼怎麼分（圖「程式架構」）

兩層，中間一個介面：

- **任務邏輯層 `src/kibo/`**：純 Python，不碰 ROS。上面那張表的所有決策都在這。
  可以在任何電腦用 `pytest` 測。
- **ROS 接線層 `ros/user_node.py`**：ROS 是機器人的「作業系統」；這層把 ROS 的訊息翻譯成
  任務邏輯看得懂的東西，自己不做決定。只能在 JAXA 的模擬器裡跑。
- **`Robot` 介面**（`src/kibo/mission.py`）：任務邏輯需要機器人做的事，八個必要方法
  （現在幾點、我在哪、飛去那裡、睡一下、任務開始、要清單、回報通過、回報完成）加兩個選用的（有沒有人叫停、寫 log）。
  ROS 版實作一次，**假機器人**（`src/kibo/fake_robot.py`）再實作一次。

為什麼要假機器人：不開模擬器（一場要七分鐘）也能把整場任務跑完，看流程會不會卡、策略參數
怎麼調。它不是物理模擬：移動秒數用同一個時間模型算、到點有隨機誤差、偶爾失敗，裁判照官方規則。
分數只能**相對比較**（各等級幾分、時間倍率怎麼算都還沒公布）。

讀程式的順序建議：`mission.py`（流程）→ `settle.py`（何時算到了）→ `judge.py`（官方怎麼判）→
`budget.py` → `planner.py` → `motion.py`（飛一段要幾秒）→ `geometry.py`。每個檔案開頭都有白話說明。
ROS 那一側另外有三個不碰 ROS 的小模組：`navlog.py`（導航紀錄）、`ctl_result.py`（移動結果的對照）、
`buslinks.py`（起跑前確認評分模組連上了）。

## 4. 在自己電腦跑一場

```bash
uv sync --locked                                  # 第一次：裝工具
uv run pytest                                     # 全部測試，約 2 秒
uv run python -m kibo.simulate --runs 10 --checkpoints 8        # 假機器人的「資格賽」
uv run python -m kibo.simulate --runs 1 --checkpoints 6 -v      # 看一場的逐步 log
uv run python -m kibo.simulate --runs 5 --checkpoints 12 --fail 0.2 --noise 0.08   # 刁難它
uv run python -m kibo.simulate --runs 10 --checkpoints 12 --slowdown 2             # 機器人比模型慢一倍
uv run python -m kibo.tune --runs 20 --checkpoints 10           # 幾種參數在四個規則世界的平均與最大後悔
```

一場的 log 長這樣（`-v`），每行開頭是時鐘與剩餘秒數：

```
[t=0.0  300.0s left] 6 checkpoints, goal #12
[t=0.0  300.0s left] route [10, 5, 3, 2, 1, 12] (~198s)          ← 排好順序，估計 198 秒
[t=51.5  248.5s left] move to #10 attempt 1: success
[t=51.5  248.5s left] leg: 5.72m 145deg in 51.5s (model 51.5s)   ← 這段腿的實際秒數對模型
[t=52.5  247.5s left] at #10: dist=0.02m centering=1.7 roll=0.3 -> Lv3 (stable)   ← 自判三項，連續達標
[t=52.8  247.2s left] checkpoint #10 accepted                    ← 通知送出（accepted 不代表通過）
[t=52.8  247.2s left] route [5, 3, 2, 1, 12] (~146s)             ← 每到一點重新規劃
```

沒穩的時候會多兩行：`-> Lv2 (unstable)` 之後再 `move`，然後 `refined: at #12: ... -> Lv3 (stable)`。

要跑**真的**模擬器：開發資源在官網 Download 頁，不用登入。步驟在 [docs/kibo/simulator.md](../kibo/simulator.md)，
跑完用 `uv run python scripts/sim_report.py` 看每場的官方評分。

## 5. 哪些已經確定，哪些還是猜的

2026-11-10 起我們有官方模擬器，下面分三類。出處與實測數字在
[simulator-internals.md](../kibo/simulator-internals.md) 與 [motion-model.md](../kibo/motion-model.md)。

### 已經確定（讀官方原始碼，並在本機模擬器跑過）

| 事實 | 在哪 |
|---|---|
| 到點判定的三個算式：距離、對中（從**機體中心**量）、滾轉（對機體到 marker 的軸做 twist 分解）。自判與官方幾乎每一點都同級 | `judge.py`，測試有官方函式算出的黃金值 |
| 每個 CheckPoint 只判第一次通知；通知回 accepted 不代表通過；完成回報時 Goal 會用當下姿態補判 | `fake_robot.py` 的假裁判照這個做 |
| CheckPoint 離 marker 固定 0.5 m、偏航 ±20°／俯仰 ±15°、滾轉 ±180°；Goal 固定是 marker 12；難度只決定點數 6／8／10／12 | `scenarios.py`、`field.py` |
| 一次移動要幾秒：先平移再轉向、bang-bang、加速度依機體方向。每段腿預測誤差約 1 秒 | `motion.py` |
| 到點精度約 1 cm、1°。瓶頸是時間：12 點全去約要 340 秒 | 模擬器記錄 |
| 起跑太快，評分模組會漏掉任務開始，整場沒有成績 | `ros/user_node.py` 的起跑保護 |
| Goal 的滾轉讀數會把小誤差放大約 7 倍 | `settle.py` 的八成緩衝 |

### 還不知道（分數在伺服器端算，要問主辦或上 Web 模擬器）

| 問題 | 我們現在怎麼做 | 影響 |
|---|---|---|
| 各等級幾分、Goal 幾分、時間倍率的公式（規則書只說最多 2 倍） | 假分數用 Lv3/2/1 = 10/6/3、Goal 20、倍率線性 1 到 2（`scoring.py`） | 倍率若很陡，繞路太遠的點可能不值得去；公式公布前一律「去最多點」 |
| **Goal 分數要不要求通過全部 CheckPoint**（A／B） | 兩種都算（`scoring.Scoring.goal_requires_all`）。欄位名與規則書都傾向「要」 | 決定來不及時值不值得刪點 |
| **逾時會不會把已得分歸零**（T0／T1） | 當作會：保險 15 秒，Goal 永不刪 | 決定保險留多少 |
| Web 模擬器的擾動（微重力模組）有多大 | 本機沒有這個模組，沒測過 | 到點精度與時間都可能變差 |
| 5 分鐘從哪裡起算 | 我們從起跑訊號算，比評分模組的起點早，偏保守 | 最多少用 10 秒 |
| 資格賽用哪個難度 | 四個難度都測 | hard、veryhard 去不完，平均約 9 點 |

問題清單與現況在 [questions-for-poc.md](../kibo/questions-for-poc.md)。

### 假機器人跑出來的結論，哪些能信

每個結論都要問「換一個規則世界、換一個真實速度，名次還一樣嗎」。`python -m kibo.tune` 把四個規則世界
（Goal 需不需要全點 × 逾時保不保留分數）並排印出來，並算「最大後悔」。

| 結論 | 站得住嗎 | 說明 |
|---|---|---|
| 機器人整體比模型慢時，線上校正是最大的單一改善 | 是 | 慢一倍、不校正，多半到不了 Goal；校正後幾乎都到（`tests/test_speed_calibration.py`）。模型準時校正完全不動 |
| 刪點保 Goal 最不會後悔 | 是 | 「不刪點」只在「Goal 需全點且逾時保留分」的世界小贏 |
| 相機修正有幫助 | **不成立（目前）** | 模擬器裡導航誤差只有 1 cm，而相機換算的深度與導航差約 15 cm。預設關，只記錄不動作 |
| 保險、趕時間門檻怎麼調 | **看規則** | 保險 15 → 10 秒，veryhard 平均多 0.24 點；代價取決於逾時的規則與擾動，都還不知道 |

## 6. 還沒做的

- **Web 模擬器**沒上過（需要隊伍帳號）。第一次上去要核對的事列在 [ros/README.md](../../ros/README.md)。
- 相機只用來記錄（每點一行「相機看到的 marker 位置對導航的預期位置」），沒有拿來修正位置。
- 更多點子與取捨：[ideas.md](ideas.md)。規格：[spec.md](spec.md)。進度：[tickets.md](tickets.md)。第一輪的回顧：[retro.md](retro.md)。
- 想問主辦的問題在 [docs/kibo/questions-for-poc.md](../kibo/questions-for-poc.md)。
- 第一版結案後開了一場 council（四位委員兩輪匿名互評，主席查證）：[notes/council/v1-review/synthesis.md](../../notes/council/v1-review/synthesis.md)，裁決 R1–R5 已實作（T14–T18，R6 是「停止」清單），待使用者確認。
