# 回顧（2026-11-04 自主 session）

照 `docs/agents/workflow.md` 第 5 步：回頭看這一輪，建議改善 agent 的環境，不是改程式。

## 做對的

- **先用手冊範例驗證座標慣例再寫任何東西**：一個 0.0° 的檢查，省掉之後所有四元數方向的猜測。
- **`Robot` 介面把 ROS 隔開**：沒有模擬器也能把整場跑完、能用子類別注入 11 種失敗情境、能做參數掃描。
- **兩軸 reviewer 分開跑**：Standards 抓到 `ServiceProxy` 沒逾時這種只看 ROS API 才知道的事；Spec 抓到「規則書字面上 Goal 分要求通過全部點」這種只看規則才知道的事。兩份報告幾乎沒有重疊。
- **把猜的數字集中成一張表**（README 第 5 節）：之後拿到模擬器照表校正，不用翻程式。

## 踩到的

- `ruff --fix` 會把只在 `# type:` 註解裡用到的 import 當成未使用刪掉，然後 pyright 才報錯。**結論：3.6 專案一律用變數註記（PEP 526），不用 type comment。** 已全部改掉。
- 測試用「兩點等距」的例子會平手，順序不唯一；用 Held-Karp 的測試資料要確保最佳解唯一。
- 合成 ArUco 影像：`rvec=0` 是從背面看 marker，要繞 X 轉 180°。偵測失敗先試翻轉影像，立刻能分辨是鏡像還是太小。
- `# noqa: BLE001` 這類沒啟用的規則碼無效，只是噪音；ruff 只開了 E、F、I、B。
- `uv run python -m kibo.simulate` 在 `package = false` 時找不到模組；改成 hatchling 可安裝套件就好。

## 建議改環境

1. `docs/agents/dev-env.md`：加一句「3.6 專案不用 type comment，用變數註記」。（本 session 已加在 retro，待使用者決定是否進 dev-env。）
2. reviewer 的 brief 格式值得固定：範圍、軸、專案約束摘要、要特別看的 API、輸出格式。這次兩個 brief 都有效，可以抽成 `docs/agents/review-brief.md` 範本。
3. 假機器人這種「可注入失敗的 fake」在其他機器人／硬體專案也適用，可以寫進 `docs/agents/workflow.md` 的「分支 2：不能純靠對話定案」當作 prototype 的一種。

## 沒做到的

- 沒有模擬器，ROS 接線層與相機訂閱完全沒跑過；本 session 的「完整」只到純 Python 層。
- 沒開 GitHub issue、沒 push：因為 repo 公開與否還沒決定。tickets 都在 `docs/solution/tickets.md`。
- FigJam 板上留了一張過時的狀態機圖（工具不能刪節點），README 已註明以新的為準。
