# 想問主辦／POC 的問題

提問截止 **2027-01-20 12:00（JST）**（規則書 2.1）。這些問題只有隊伍能問。送出後把回覆（或「無回覆」）記在這裡。

2026-11-10 更新：官方模擬器的原始碼回答了其中幾題（依據見 [simulator-internals.md](simulator-internals.md)）。
**還要問的是 1、2、3、7、8、11、12**；4、6 已有答案，5、9、10 先自己在本機量。

| # | 問題 | 為什麼 | 現況 |
|---|---|---|---|
| 1 | Pt_goal（到達 GoalPoint 的分數）是否要求**所有** CheckPoint 都通過？若中途漏了一點但到達 Goal 並完成回報，Goal 分數還給嗎？ | 規則書附錄 #20 字面是「passes all CheckPoints」；模擬器 cheat sheet 的欄位也叫 `all_checkpoints_bonus`。但本機評分模組不算分 | **要問**。沒答案時當作「要求全點」 |
| 2 | 若**沒在時限內**完成回報，已通過的 CheckPoint 分數是否保留？倍率 Mag_clear 怎麼算？ | 規則書 2.2.3 只說「沒有完成回報的分」；本機模擬器沒有 5 分鐘時限 | **要問** |
| 3 | 各 Lv 的點數、Pt_goal 與 Mag_clear 對剩餘時間的公式（規則書附錄 #16、#21 的 score calculation table）在哪裡？ | 規則書與模擬器壓縮檔裡都沒有 | **要問** |
| 4 | CheckPoint 的「對中」以哪裡為原點？ | | 已知：**機體中心**（`judge.py` 的 `_evaluate_centering_and_roll`） |
| 5 | 計時起點是 Release 完成、還是 `mission_start` 被呼叫的時刻？ | 規則書附錄 #7 vs 評分模組記的是 `mission_start` | 本機先量；只需向主辦確認伺服器用哪個 |
| 6 | `get_checkpoints` 是否一定包含 Goal？有沒有不評分的點？ | | 已知：一定包含（marker 12），沒有不評分的點 |
| 7 | 資格賽的 10 次自動執行用哪個 Simulator Level（easy 6 點／normal 8／hard 10／veryhard 12）？ | 決定時間夠不夠、策略怎麼調 | **要問** |
| 8 | Web 模擬器每天／每隊的執行次數有沒有上限？ | 本機能跑了，但最終以 Web 為準 | **要問** |
| 9 | AR marker 的 ArUco 字典？影像 encoding？ | | 本機先量 |
| 10 | `/sensor_fusion/navigation` 的 `header.stamp` 是否填值？ | | 本機先量 |
| 11 | **Goal 點能不能先通過？** 本機評分模組接受「先通過 Goal 點（marker 12），巡完其他點後在別處送完成回報」，Goal 仍算到達。這樣合規嗎？ | 規則書 2.2.4 寫完成回報要在抵達 GoalPoint 時送出。合規的話可以省掉回程 | **要問**。沒答案時 Goal 排最後 |
| 12 | Web 模擬器與正式評分用的評分模組，和下載包裡的 `judge.py` 是同一份嗎？（特別是：每點只判第一次通知、完成回報時用當下姿態補判 Goal） | 我們的自判是照那份寫的 | **要問** |

## 回覆紀錄

（尚未送出）
