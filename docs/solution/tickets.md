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
