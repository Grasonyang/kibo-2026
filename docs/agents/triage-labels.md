# Triage Labels

Matt skills 的五個標準 triage 角色，與本 repo 的標籤字串完全相同，不另外改名。

| Matt 的角色 | 本 repo 的標籤 | 意思 |
|---|---|---|
| `needs-triage` | `needs-triage` | 維護者需要評估 |
| `needs-info` | `needs-info` | 等待回報者補充資訊 |
| `ready-for-agent` | `ready-for-agent` | 規格完整，可交給 agent 獨立完成 |
| `ready-for-human` | `ready-for-human` | 需要人來實作 |
| `wontfix` | `wontfix` | 不處理 |

skill 提到某個角色（例如「套用 AFK-ready 標籤」）時，用上表對應的字串。

## 其他標籤

完整清單在 `.github/labels.tsv`，用 `scripts/sync-labels.sh` 同步到 repo。

| 標籤 | 用途 |
|---|---|
| `wayfinder:map`、`wayfinder:research`、`wayfinder:prototype`、`wayfinder:grilling`、`wayfinder:task` | `wayfinder` 的地圖與決策 ticket（名稱由 skill 規定，不能改） |
| `kind:task`、`kind:bug`、`kind:feature`、`kind:spec`、`kind:decision`、`kind:research`、`kind:chore` | Issue 類別（個人帳號沒有 Issue type） |
| `one-way-door` | 單向門的 PR，合併前需使用者確認 |
