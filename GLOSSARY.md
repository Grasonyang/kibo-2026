# Glossary

用語依 Rulebook v1.1 附錄與 Programming Manual 1.0。

| 用語 | 定義 |
|---|---|
| **Kibo-RPC** | Kibo Robot Programming Challenge，JAXA 主辦、在 ISS 上用機器人的程式競賽。本專案是第 7 屆 |
| **Kibo（JEM）** | ISS 上的日本實驗艙 |
| **Int-Ball2（IB2）** | 比賽用的自由飛行機器人；資格賽在模擬器，決賽是 ISS 上的實機（Jetson TX2，ARM64） |
| **Dock Station** | IB2 的基地與起點，座標系原點。undock 完成時開始計時 |
| **StartPoint／GoalPoint** | 任務起點（目前即 Dock Station）／通過所有 CheckPoint 後到達並做完成回報的點 |
| **AR marker** | 用來辨識相對位置與姿態、並作為 CheckPoint 原點的標記。Kibo 內共 12 個，ArUco 4x4，ID 1 到 12，邊長 0.02 m |
| **CheckPoint** | 以 AR marker 為基準、以球形區域定義的通過點，有三級餘裕（Lv1 到 Lv3）。每次執行位置隨機，6 到 12 個 |
| **Lv1／Lv2／Lv3** | 通過判定的等級，Lv3 最嚴格、分數最高。位置、對中、滾轉三項取最低一級 |
| **對中（centering）** | 相機視線與「IB2 指向 AR marker 的方向」的夾角，要求 marker 在畫面中心附近 |
| **滾轉（roll）** | 繞相機視線軸的旋轉角，要接近 CheckPoint 指定的目標姿態 |
| **Mission Start／Finish** | 任務開始（undock 完成）／任務時限結束或開始送完成回報；Finish 之後的動作不計分 |
| **時限（time limit）** | 5 分鐘 |
| **Mission Completion Report** | 抵達 GoalPoint 後呼叫 `/event/mission_finished` |
| **Pt_check／Pt_goal／Pt_all** | CheckPoint 得分（依 Lv）／到達 Goal 得分／兩者總和 |
| **Mag_clear** | 依剩餘時間決定的倍率，最大約 2 倍 |
| **Score** | `Pt_all × Mag_clear` |
| **微重力模組（microgravity module）** | 模擬器的干擾要素，隨機產生擾動，僅模擬器有 |
| **Preliminary（資格賽）** | 各國分區賽，程式在 Web 模擬器自動跑 10 次取平均 |
| **POC** | 各國家／地區的聯絡窗口，負責 Web 模擬器帳號 |
| **Web／本機模擬器** | JAXA 伺服器上的（ARM64）／本機 Docker 裡的 |
| **`krpc_user`** | 參賽者實作的 catkin package，是唯一可改的官方目錄 |
| **`iss_body`／`body`** | 絕對座標系（ISS 基準）／IB2 本體座標系 |
