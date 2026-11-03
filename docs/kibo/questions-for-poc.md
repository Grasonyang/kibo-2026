# 想問主辦／POC 的問題

提問截止 **2027-01-20 12:00（JST）**（規則書 2.1）。這些問題的答案能省掉上機第一小時的兩場探針，而且只有隊伍能問。
每題附「為什麼要問」與「沒答案時我們怎麼辦」。送出後把回覆（或「無回覆」）記在這裡。

| # | 問題 | 為什麼 | 沒答案時 |
|---|---|---|---|
| 1 | Pt_goal（到達 GoalPoint 的分數）是否要求**所有** CheckPoint 都通過？若中途漏了一點但到達 Goal 並完成回報，Goal 分數還給嗎？ | 規則書附錄 #20 字面是「passes all CheckPoints」，但手冊 4.3.2 的結果 JSON 把 Goal Reached 與 CheckPoints Passed 分列 | 探針：故意漏一點看 `goal.success` |
| 2 | 若**沒在時限內**完成回報，已通過的 CheckPoint 分數是否保留？倍率 Mag_clear 怎麼算？ | 規則書 2.2.3 只說「沒有完成回報的分」；附錄 #8 只作廢 Finish 之後的動作 | 探針：故意逾時 |
| 3 | 各 Lv 的點數與 Mag_clear 對剩餘時間的公式（規則書附錄 #16、#21 提到的 score calculation table）在哪裡可以看到？ | v1.1 PDF 裡沒有這張表 | 從幾場不同完成時間的結果 JSON 反推 |
| 4 | CheckPoint 的「對中」是以 IB2 機體中心還是相機位置（機頭前 0.14 m）為原點算角度？ | 手冊 6.3.1 寫「from the vehicle」，規則書圖 2.3.2-1 畫的是 NavCam | 比對我們 log 的 Lv 與結果 JSON 的 level，切換 `camera_offset_m` |
| 5 | 計時起點是 Release 完成、還是 `/ib2_user/start` 發出的時刻？兩者差多少？ | 規則書附錄 #7 vs 手冊 6.3.4 | 比對結果 JSON 的 `duration_sec` 與我們的 elapsed |
| 6 | `get_checkpoints` 回傳的清單是否**一定**包含 `goalpoint_id` 那一點？會不會有「N/A（不評分）」的點也在清單裡？ | 手冊 4.3.1 提到 N/A；我們的程式對兩者都有降級，但想知道正常情況 | 第 0 場看 `cheat_sheet.json` |
| 7 | 資格賽的 10 次自動執行用哪個 Simulator Level？CheckPoint 數量範圍？ | 手冊 4.2.2 的 Level 選項與規則書 2.2.2 的 6–12 個 | 兩種極端都測 |
| 8 | Web 模擬器每天／每隊的執行次數有沒有上限？ | 決定能做幾場探針與校準 | 省著用 |
| 9 | AR marker 用的 ArUco 字典是 `DICT_4X4_50` 嗎？影像 encoding 是 mono8 還是 bgr8？ | 手冊 5.13.1 只說 4x4 | 第 1 場 survey log |
| 10 | `/sensor_fusion/navigation` 的 `header.stamp` 是否填值？`Navigation.status` 的定義？ | 我們用 stamp 判斷資料新鮮度與去重 | 第 1 場 survey log；stamp 為 0 就改用接收時間 |

## 回覆紀錄

（尚未送出）
