# 開發流程

以 Matt skills 的流程為基準，盡可能照做。各步驟用哪個 skill 見 [skill-routing.md](./skill-routing.md)；每步開始前先宣告使用的 skill。

## 主流程：想法到上線

### 0. 前置
用模板建立的專案已經帶有 `setup-matt-pocock-skills` 的設定（GitHub Issues、標準 triage 標籤、single-context 的 `GLOSSARY.md` 加 ADR），不需要重跑。只有要換 issue tracker 時才再用。新專案建好後執行 `scripts/sync-labels.sh` 建立標籤。

### 1. 釐清
`grill-with-docs`（有 repo）或 `grill-me`（無 repo）。需要時帶出 `domain-modeling`，用語與決策寫進 `GLOSSARY.md` 和 ADR。
需求有疑問就問，不要自己假設。

### 2. 分支：能否純靠對話定案？
- 能：往下。
- 不能（要看 UI、驗證狀態或商業邏輯）：`handoff` 出去，用 `prototype` 做一次性程式回答問題，再 `handoff` 把結論帶回。

### 3. 分支：是否需要多個 session 才做得完？
- **是**：`to-spec` 把對話整理成 spec，再用 `to-tickets` 拆成 tickets（每張標明 blocking edges）。然後二選一：
  - `implement`，一張 ticket 一輪，每張之間清掉 context。
  - `implement-spec`，整份 spec 一次跑，多個 agent 平行，最後在整合分支上做一次 `code-review`。
- **否**：直接在同一個 context 用 `implement`。

### 4. 實作與審查
- 以 `tdd` 一次一個垂直切片（紅、綠、重構）。型別檢查與單檔測試常跑，完整測試在最後跑一次。
- 各語言的驗證指令與環境見 [dev-env.md](./dev-env.md)。
- ticket、交付報告、審查報告的格式，以及 worktree、branch、PR 約定，見 [delivery.md](./delivery.md)；每個改動都開新 worktree，開好後先跑「安裝」。
- 結束前 `code-review`（Standards + Spec 兩軸）。
- 需要 PR 時用 `pr` 寫內容：最小的視覺化摘要、前後證據、單向門或雙向門與影響範圍。

### 5. 回顧
`retro`：在同一個 session 回頭看，建議改善 agent 環境（導覽、自動檢查、coding standards、steering files），不是改程式碼。

## 角色分工

三個標準角色定義在 [roles.md](./roles.md)，Claude 與 Codex 通用：

| 階段 | 角色 |
|---|---|
| 1 釐清、2 分支、3 spec 與 tickets | planner |
| 4 實作 | worker（一張 ticket 一個，指定 worktree） |
| 4 審查 | reviewer（Standards、Spec 兩軸各一，全新 context） |
| 5 回顧、合併決定 | 協調者（主 session） |

小任務可以由協調者自己做，不必硬拆角色；但要拆時就照這張表，不另創角色。

## 入口與支線

| 起點 | 做法 |
|---|---|
| 外部進來的 bug、需求 | `triage`，產出 agent-ready issues，之後交給 `implement` |
| 難查的 bug | `diagnosing-bugs`；修完在同 session 跑 `retro`，找不到好 seam 時轉 `improve-codebase-architecture` |
| 大到一個 session 裝不下 | `wayfinder`；地圖收斂後回主流程的 `to-spec`，不要直接 `implement` |
| 需要查證資料 | `research`，成果帶回 `grill-with-docs` |
| 定期保養 | `improve-codebase-architecture`，選一個候選後回主流程 `grill-with-docs` |

## Context 衛生

- 步驟 1 到 3（到 `to-tickets` 為止）盡量留在同一個 context，不要中途 compact 或 clear。
- 每個 `implement` 從乾淨的 context 開始，只靠 ticket。
- 接近聰明區上限（約 150k tokens）時，在最近的階段邊界 `/compact`，不要硬撐。
- 階段邊界的選擇：先考慮繼續，其次 `/clear`，再來 `handoff`（只在換 harness、換目錄、交給別人、或中途分岔時）、subagent，預設才是 `/compact`。

## 紀律

- 不跳階段：沒有 spec 就不 `to-tickets`，沒有 ticket 或 spec 就不 `implement`，除非使用者明說。
- 不確定走哪條路時，用 `ask-matt`，或直接問使用者。
- 階段之間的轉換要說出來，讓使用者有機會喊停。
