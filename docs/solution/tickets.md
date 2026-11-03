# Tickets

由 `docs/solution/spec.md` 拆出。因為還沒決定要不要 push 到 GitHub，先放這裡，不開 GitHub issue；每張做完在這裡打勾並寫 commit。

| # | Ticket | 驗收 | 狀態 |
|---|---|---|---|
| T1 | 幾何工具：四元數旋轉、視線方向、夾角、`look_at`、滾轉誤差 | 手算數字的測試通過；手冊 6.3.1 範例的姿態確實對準 marker | done |
| T2 | 解析 `get_checkpoints` JSON 成具名結構，bands 由嚴到寬 | 用手冊的回應範例測 | done |
| T3 | 到點判定 `judge`：三項指標與 Lv | 邊界值測試；手冊範例在 Lv3 | done |
| T4 | 路線規劃（Held-Karp），以 Goal 收尾 | 小例子的最佳順序；12 點在 1 秒內 | done |
| T5 | 時間預算：leg 估時、來不及時依價值刪點、Goal 不刪 | 刻意設計來不及的案例 | done |
| T6 | 任務狀態機 + `Robot` 介面 + 假機器人，整場跑完並算估計分數 | 假機器人全程通過；注入失敗時不卡死、重試有上限 | done |
| T7 | ROS 接線層（照官方範本結構） | 本機只能過 vermin 與 ruff；實測等模擬器 | done（未實測） |
| T8 | 零基礎文件 + Figma 圖 | `docs/solution/` 從比賽講起；圖有連結 | done |
| T9 | 點子清單與取捨 | `docs/solution/ideas.md` | done |
| T10 | reviewer 審查（Standards、Spec 各一）與修正 | 審查報告無 blocker | done：無 blocker；3+4 個 major 全修，minor/nit 修完；補 13 個測試 |
| T11 | 相機模組 `vision.py`（偵測、solvePnP、座標換算、修正量），合成影像測試 | 位置誤差 < 1 cm；3.x 與 4.7+ API 都支援 | done（接線未做） |
| T12 | 參數掃描 `kibo.tune` 與視差開關 `camera_offset_m` | 印出平均與最低分；開關有測試 | done（T16 後改成四世界平均、最大後悔、最低、sd） |
| T13 | 相機修正接進流程：`Robot.marker_in_body`、`move_relative`，假相機，ROS 端影像訂閱 | 假相機下 15 cm 偏移一次修回 Lv3；超過 0.3 m 退回絕對移動 | done（ROS 端未測） |

## 第二階段（council v1-review 裁決，`notes/council/v1-review/synthesis.md`）

| # | Ticket | 驗收 | 狀態 |
|---|---|---|---|
| T14 | R1 不死保底：parse 降級、>11 中途點不 raise、成本矩陣、`run_mission` 保證 finish、ROS 例外也 finish | 手冊範例（count=8、goal=12）、缺 Goal、缺欄位、丟例外的 Robot、12 中途點：都 `finished_at` 非 None | done |
| T15 | R2 速度線上校正（只往慢、夾 0.5–1.0）、`move_timeout = max(60, 2×估計腿)` | 真速 {0.05, 0.1, 0.2} × n {8, 12}：Goal 率不低於現行、與 oracle 差 ≤10%、速度正確時損失 ≤3% | done（矩陣：Goal 率全 ≥ 現行、與 oracle 差 ≤ 4.3%、速度對時零損失） |
| T16 | R3 規則世界旗標與 tune 的四世界／最大後悔表；README 第 5 節只留跨世界穩定的結論 | tune 印四世界；README 啟示逐條標 fake-sensitive 或移除 | done |
| T17 | R4 校準與飛行記錄：log 欄位、探針旗標（預設關）、settle 只計新 stamp、沒成功移動不回報、ROS `_call` 用 rospy 時間 | 單場 log 能算速度與 settle 秒數；重複樣本不算穩定；旗標跑通 | done（ROS 端未測） |
| T18 | R5 上機劇本改寫 ros/README | 文件 | done |
