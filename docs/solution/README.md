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
| 看時間 | 估計整條路要多久，加上安全餘裕，超過剩餘時間就刪點；終點永不刪 | `src/kibo/budget.py` |
| 移動 | 叫機器人飛到指定位置與姿態，每點最多嘗試 2 次 | `src/kibo/mission.py` |
| 自我檢查 | 用目前位置算三個條件各幾級，連續 5 次（涵蓋 1 秒）達標才算穩；沒穩就再靠近一次 | `src/kibo/judge.py` |
| 回報 | 告訴伺服器「我到了」，由伺服器給分 | `src/kibo/mission.py` |
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

為什麼要假機器人：沒有模擬器的電腦也能把整場任務跑完，看流程會不會卡、策略參數
怎麼調。它不是物理模擬（等速飛、到點有隨機誤差、偶爾失敗），分數只能**相對比較**。

讀程式的順序建議：`mission.py`（流程）→ `budget.py` → `planner.py` → `judge.py` →
`geometry.py`。每個檔案開頭都有白話說明。

## 4. 在自己電腦跑一場

```bash
uv sync --locked                                  # 第一次：裝工具
uv run pytest                                     # 98 個測試，約 0.5 秒
uv run python -m kibo.simulate --runs 10 --checkpoints 8        # 本機「資格賽」
uv run python -m kibo.simulate --runs 1 --checkpoints 6 -v      # 看一場的逐步 log
uv run python -m kibo.simulate --runs 5 --checkpoints 12 --fail 0.2 --noise 0.08   # 刁難它
uv run python -m kibo.tune --runs 20 --checkpoints 10                   # 四個規則世界的平均與最大後悔，有無相機各一表
uv run python -m kibo.tune --runs 20 --checkpoints 12 --speed 0.05      # 真速只有一半時，看哪個變體撐得住
uv run python -m kibo.simulate --runs 10 --checkpoints 8 --noise 0.08 --camera   # 開假相機
```

一場的 log 長這樣（`-v`），每行開頭是剩餘秒數：

```
[ 300.0s left] 6 checkpoints, goal #12
[ 300.0s left] route [1, 2, 3, 5, 10, 12] (~204s)      ← 排好順序，估計 204 秒
[ 278.6s left] move to #1 attempt 1: success
[ 277.6s left] at #1: dist=0.05m centering=1.6 roll=0.0 -> Lv3 (stable)   ← 自我檢查三項，連續達標
[ 276.6s left] checkpoint #1 accepted                   ← 伺服器收了
...
[ 144.1s left] move to #12 attempt 1: success
[ 143.1s left] at #12: dist=0.03m centering=4.9 roll=1.3 -> Lv3 (stable)
[ 142.1s left] checkpoint #12 accepted
[ 142.1s left] mission finished: True
```

沒穩的時候會多兩行：`-> Lv2 (unstable)` 之後再 `move`，然後 `refined: at #12: ... -> Lv3 (stable)`。


要跑**真的**模擬器，需要 JAXA 的開發資源包（隊伍帳號登入下載），步驟在
[docs/kibo/simulator.md](../kibo/simulator.md)。

## 5. 哪些數字是猜的，哪些結論站得住

這些都是「拿到模擬器就要校正」的假設，集中列出來免得被當成事實：

| 假設 | 在哪 | 怎麼校正 |
|---|---|---|
| IB2 速度 0.1 m/s、轉速 15°/s | `planner.Speeds` | 看 log 每段 `leg:` 的實際秒數對模型；程式會自動往慢修，但預設值要改 |
| 每點穩定 8 秒、終點保險 25 秒 | `budget.BudgetConfig` | 同上 |
| 速度校正的門檻：慢 25% 才校正（`calibrate_below_ratio=0.8`）、只用 ≥ 1 m 的腿（`calibrate_min_leg_m`）、累積 20 秒模型時間才動（`calibrate_min_predicted_sec`）、最多調慢 2 倍 | `mission.MissionConfig` | 看 log 的 `leg:` 與 `speed calibrated` 行；假機器人的 3 秒起停（`fake_robot.move_overhead_sec`）也是猜的 |
| Lv3/2/1 = 10/6/3 分、Goal 20 分、倍率線性 1 到 2 | `scoring.py` | Web 模擬器的結果 JSON；規則書引用的分數表不在 PDF 裡 |
| **Goal 分數要不要求通過全部 CheckPoint**（A／B） | `scoring.Scoring.goal_requires_all` | 探針：故意漏一點看 `goal.success` |
| **逾時會不會把已得分歸零**（T0／T1） | `scoring.Scoring.timeout_keeps_points` | 探針：故意逾時 |
| 對中用「相機位置」算（相機在機頭前 14 cm）；手冊 6.3.1 的字面是「from the vehicle」 | `judge.py`，開關 `MissionConfig.camera_offset_m` | 比較 log 的 Lv 與結果 JSON 的 level |
| 計時起點 = `/ib2_user/start` 到來的時刻（規則說是 Release 完成） | `mission.py` 的 `t0` | 比對結果 JSON 的 `duration_sec` |
| CheckPoint 離 marker 0.4 到 0.7 m、偏法線 ≤ 20°；一場 6 到 12 點都要去 | `scenarios.py` | `cheat_sheet.json`；手冊 4.3.1 有「N/A 不評分」的點 |
| ArUco 字典 `DICT_4X4_50` | `vision.py` | 範本或模擬器影像 |
| Goal 在 CheckPoint 清單裡、id 就是 marker 編號 | `checkpoints.py`（不在也會降級飛完） | `cheat_sheet.json` |

一個已經確定的事：手冊給的範例姿態，用我們的算法算出來「正對 marker、誤差 0.0°」，
所以座標與四元數的慣例是對的（`tests/test_geometry.py`）。

### 假模型跑出來的結論，哪些能信

假機器人不是物理，所以每個結論都要問「換一個規則世界、換一個真實速度，名次還一樣嗎」。
`python -m kibo.tune` 把四個規則世界（Goal 需不需要全點 × 逾時保不保留分數）並排印出來，
並算「最大後悔」（在最不利的世界裡比最好的變體差幾分）。

| 結論 | 跨世界、跨速度都成立？ | 說明 |
|---|---|---|
| **速度猜錯時，線上校正是最大的單一改善** | 是 | 真速只有一半（0.05）時，20 場、世界 B/T0、沒相機：8 點不校正 27 分、Goal 10/20 → 校正 75 分、20/20；12 點 57 分、14/20 → 89 分、19/20。`kibo.tune --speed 0.05` 的「不校正速度」在四個世界最大後悔 40 分，其餘 ≤ 7。速度猜對（0.1、0.2）時與不校正完全相同 |
| **刪點保 Goal 是最不會後悔的選擇** | 是 | `kibo.tune` 的「不刪點（只做對照）」變體：四世界裡只在「Goal 需全點且逾時保留分」小輸幾分，其餘大輸（12 點、真速 0.1 時逾時世界整場 0） |
| 相機修正有幫助 | **fake-sensitive** | 只在相對移動幾乎無誤差時成立；相對移動加 5 cm 雜訊，增益就消失。所以**預設關**（`camera_fix_max_m=0`），上機驗過座標再開 |
| 只求 Lv2 比追 Lv3 好 | **fake-sensitive** | 取決於真實的 Lv 分數比與到點誤差，兩者都沒公布 |
| 保險、穩定估值、趕時間門檻怎麼調 | **分不出來** | 差異 5–10 分，與資格賽 10 次平均的標準誤（單場 sd 12–17，標準誤約 4–5）同量級；拿到真資料前不調 |

一個值得知道的發現：相機在機頭前 14 cm，marker 只離 50 cm，所以**側向偏 15 cm 就會讓
對中掉到 Lv1**（若伺服器也用相機位置算）。位置要準，而且沿視線方向偏比側向偏好。

## 6. 還沒做的

- ROS 接線層沒跑過（沒有模擬器）。第一次跑要核對的事列在 [ros/README.md](../../ros/README.md)。
- 相機修正已接進流程但 ROS 端沒測過：主流程靠導航資料，只有「到了但不穩」時才用相機看 marker 修正幾公分（`src/kibo/vision.py`，合成影像測過）。假機器人可用 `--camera` 開假相機。
- 更多點子與取捨：[ideas.md](ideas.md)。規格：[spec.md](spec.md)。進度：[tickets.md](tickets.md)。第一輪的回顧：[retro.md](retro.md)。
- 想問主辦的十個問題在 [docs/kibo/questions-for-poc.md](../kibo/questions-for-poc.md)，答案能省掉上機的兩場探針。
- 第一版結案後開了一場 council（四位委員兩輪匿名互評，主席查證）：[notes/council/v1-review/synthesis.md](../../notes/council/v1-review/synthesis.md)，裁決 R1–R5 已實作（T14–T18，R6 是「停止」清單），待使用者確認。
