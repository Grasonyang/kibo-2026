# 競賽規則摘要

來源：7th Kibo-RPC Rulebook v1.1（2026-10-15）。各國資格賽可能有自己的評分，以當地 POC 與官網 <https://jaxa.krpc.jp/> 為準。

## 時程（資格賽）

| 事件 | 時間（JST） |
|---|---|
| 提問截止 | 2027-01-20 12:00 |
| 程式提交截止 | 2027-01-20 23:59 |
| 資格賽期間 | 2027-01-21 到 2027-02-17 |

提交前必須在 Web 模擬器的「Preliminary」跑到 `FINISHED`，再到 RESULTS 按 SUBMIT；`FAILED` 的程式不能提交。截止前可以 CANCEL 後重交。

## 任務流程

1. IB2 從 Dock Station 自動 undock，計時開始。
2. 取得各 CheckPoint 的位置與姿態（`/mission/get_checkpoints`）。
3. 用有效率的路線拜訪每個 CheckPoint。
4. 在每個 CheckPoint 對準 AR marker，維持條件 **1 秒**。
5. 拜訪完所有 CheckPoint，抵達 GoalPoint，送出任務完成回報。

## 前提

- 時限 **5 分鐘**，完成回報必須在時限內；超時則沒有完成回報的分數。
- CheckPoint 6 到 12 個（依難度），是以 AR marker 為原點、隨機角度與距離的球形區域。
- 模擬器有微重力模組作為干擾（僅模擬器）。
- 事先知道：起點、完成回報位置、CheckPoint 總數與範圍、AR marker 位置與 ID、GoalPoint。**不**事先知道：本次 CheckPoint 的實際位置與姿態、干擾模式。
- 資格賽每份程式自動跑 **10 次**（每次隨機條件不同），**取平均**排名。
- AR marker 固定資料見 `src/kibo/field.py`。

## 計分

CheckPoint 通過需同時滿足三項，各有 Lv1 到 Lv3 三級餘裕，**取最低一級**給分；任一項超出餘裕或不到 1 秒則該點 0 分：

1. 位置：IB2 在 CheckPoint 球內（`score_bands` 的半徑）。
2. 對中：AR marker 在相機畫面中心附近（`centering_bands`，視線與指向 marker 方向的夾角）。
3. 滾轉：繞相機視線軸的角度接近目標（`roll_bands`）。

```
Score = Pt_all × Mag_clear
Pt_all = Σ Pt_check（依 Lv）+ Pt_goal
```

`Mag_clear` 是剩餘時間倍率，**最大約 2 倍**，完成回報時剩越多越高。各 Lv 的點數與倍率曲線規則書沒有給。

手冊 4.3.1 的建議順序：先確保全部 CheckPoint 通過、到達 Goal，再去壓時間。

## 決賽（ISS）

- 只有各地代表隊參加；程式與原始碼要提交，JAXA 會先做安全審查，**常需修改**，時程要預留。
- 每隊只有**一次**執行，不能重跑或中止；IB2 卡住時才可能重跑，但若原因是參賽者的程式則不重跑。
- 時限同樣 5 分鐘；卡住、失去自身位置、或長時間不動，系統可能提前結束。
- 參賽者當天不能操作程式；由 JAXA 預先安裝，地面下達執行指令。
