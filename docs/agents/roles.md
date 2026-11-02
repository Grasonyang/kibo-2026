# Agent 角色

Claude 與 Codex 都用同一組三個標準角色：**planner**、**worker**、**reviewer**。名稱、職責、權限在兩邊一致；差異只在模型與設定檔格式。

主 session（使用者直接對話的那個）是**協調者**，不算第四個角色：它決定何時叫哪個角色、整合結果、與使用者溝通。

| 角色 | 一句話 | 能寫什麼 | 對應階段 |
|---|---|---|---|
| planner | 釐清需求、寫決策與規格、拆 tickets | 只寫規劃文件（`GLOSSARY.md`、ADR、spec、tickets），不動產品程式碼 | workflow 1 到 3 |
| worker | 在指定 worktree 完成一張 ticket | 程式、測試、文件 | workflow 4 |
| reviewer | 在全新 context 獨立審查，回報問題 | 唯讀，不修改檔案 | workflow 4 的審查 |

## planner

- **輸入**：使用者的想法、現有程式碼與 `GLOSSARY.md`、ADR。
- **輸出**：決策紀錄、spec、tickets（含 blocking edges）。
- **常用 skill**：`grill-with-docs`、`domain-modeling`、`to-spec`、`to-tickets`、`wayfinder`、`research`。
- **邊界**：發現需要改產品程式碼時，寫成 ticket 交給 worker，不自己動手。需求有疑問先問，不假設。

## worker

- **輸入**：一張 ticket（或一份 spec 中的一個切片）與指定的 worktree。
- **輸出**：通過測試的程式碼、必要的文件、交付證據（跑了什麼、結果如何）、commit。
- **常用 skill**：`implement`、`tdd`、`diagnosing-bugs`、`pr`。
- **邊界**：一次只做一張 ticket，不擴張範圍；ticket 有疑問就回報，不自行改 spec。完成前不自己宣稱審查通過，審查交給 reviewer。

## reviewer

- **輸入**：明確的 `base..HEAD` 範圍，以及要審的軸：**Standards**（符合專案 coding standards 與常見 smell）或 **Spec**（忠實實作來源 issue 或 spec）。
- **輸出**：具體問題清單（檔案、行、原因、建議），沒問題就明說沒有。
- **常用 skill**：`code-review`。
- **邊界**：唯讀；全新 context，不沿用 worker 的對話，避免被其推理帶偏。Standards 與 Spec 兩軸各開一個 reviewer 平行跑，互不污染。

## 協作規則

1. planner 產出 tickets，worker 領單做，reviewer 審，協調者決定是否合併。
2. worker 與 reviewer 之間只透過 diff、ticket、證據溝通，不共享 context。
3. 巢狀深度最多 2 層：協調者叫角色，角色不再叫角色，除非是 `implement-spec` 這類 skill 明文要求。
4. 同時進行的角色數量上限 2（對應 Codex 的 `max_threads = 2`）。Claude 沒有對應設定，由協調者自行遵守。
5. 每個角色開工前，先宣告用了哪些 skill（見 [skill-routing.md](./skill-routing.md)）。
6. 交接用 [delivery.md](./delivery.md) 規定的格式（ticket、交付報告、審查報告），升級規則也在那裡。
7. 一律以 Git root 解析文件路徑；回覆使用繁體中文，給結果、證據與未決項目，不重述整份規格。

## 模型與額度

| 角色 | Codex（`.codex/agents/*.toml`） | Claude（`.claude/agents/*.md`） |
|---|---|---|
| planner | `gpt-6.1-sol`、medium、workspace-write | `opus`，可寫檔 |
| worker | `gpt-6-luna`、max、workspace-write | `sonnet`，可寫檔 |
| reviewer | `gpt-6-luna`、high、read-only | `sonnet`，工具限讀取與 git |

- Codex 預設的 subagent 是 `gpt-6-luna`、`xhigh`；日常主模型是 `gpt-6.1-sol`、medium。
- Claude 這欄是比照 Codex 的分工訂的：planner 用較強的模型，worker 與 reviewer 用 subagent 級模型。要調整時改 `.claude/agents/*.md` 的 `model`，並同步這張表。
- Claude 的 reasoning effort 沿用 session 設定，agent 檔不另指定。
- 「唯讀」在 Codex 由 `sandbox_mode` 強制；在 Claude 只能靠工具清單加指令約束（reviewer 需要 Bash 跑 `git diff`，技術上仍可寫），因此 reviewer 的指令明文禁止修改。

## 新增或修改角色

三個角色是標準，不隨專案增減。要改職責或權限時：

1. 先改本文件。
2. 同步 `.codex/agents/<role>.toml` 與 `.claude/agents/<role>.md`。
3. 兩邊 `developer_instructions` 與 agent 本文的職責描述要一致。
