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
| **對中（centering）** | 機體 +X 軸與「機體中心指向 AR marker」的夾角（官方評分從機體中心量，不是相機） |
| **滾轉（roll）** | 實際姿態與目標姿態各自對「機體中心指向 AR marker」軸做 twist 分解，兩者的差。Goal（marker 12）的讀數會放大小誤差 |
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
| **自判** | 我們自己照官方算式算出的等級，用來決定何時送通過通知。真正給分的是評分模組 |
| **到點穩定（settle）** | 在容差內連續待滿 1 秒：連續達標的導航樣本至少 5 筆、頭尾相隔至少 1 秒（`src/kibo/settle.py`） |
| **尾段（tail）** | 移動的 action 回報成功之前那一小段導航紀錄。夠格就直接算到點穩定，不用再等 1 秒 |
| **導航紀錄（NavLog）** | 節點收到的導航資料，降到 20 Hz 留最近約 3 秒（`src/kibo/navlog.py`） |
| **餘裕（slack）** | 這一點還能多花的秒數：剩餘時間扣掉後面路線還要的秒數（後面還有移動時含收尾保留）。小於 5 秒才接受比 Lv3 低的等級；到點後的等待與修正只花餘裕 |
| **保險（margin）** | 規劃時從 300 秒裡保留不用的秒數（預設 15 秒） |
| **收尾保留** | 時限前一定留給收尾的秒數：等待最晚等到時限前 3 秒，移動的逾時最晚到時限前 8 秒（多的 5 秒給取消）。保險是規劃時的打算，會被等待用掉；收尾保留是執行時的硬上限 |
| **移動時間模型** | 照控制器原始碼算一次移動要幾秒：先平移再轉向、bang-bang、加速度依機體方向（`src/kibo/motion.py`） |
| **節奏（Speeds）** | 移動時間模型乘上「實際比模型慢幾倍」；任務中若實測偏慢會把倍數調高 |
| **評分模組（judge）** | 官方模擬器裡判定各點等級與 Goal 的程式（`judge.py`）。只輸出等級，分數在伺服器端算 |
| **起跑保護** | 送任務開始之前，先確認事件 topic 的訂閱者都已連上，否則開始事件會遺失、整場沒有成績 |
