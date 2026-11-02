# Skills 路由

哪個情境該載入哪個 skill、從哪裡讀、怎麼宣告。流程順序見 [workflow.md](./workflow.md)。

## 來源解析

流程技能一律指 Matt 原版（org fork：`Yang-Home-99/matt-skills`，本機 clone 在 `~/Documents/Yang-Home/matt-skills`）。依序找，找到就停：

1. `~/Documents/Yang-Home/matt-skills/skills/<bucket>/<name>/SKILL.md`：唯一可信來源，`git pull` 即更新。
2. `~/.agents/skills/<name>/SKILL.md`、`~/.claude/skills/<name>/SKILL.md`：安裝副本，可能過舊（目前缺 `pr`、`retro`、`writing-for-agents`）。與 1 不一致時以 1 為準。
3. 都找不到：回報 skill 名稱與受阻的步驟，等使用者處理。不得憑名稱模擬流程。

`<bucket>` 為 `engineering`、`productivity`（`misc`、`in-progress` 非日常，用到再說）。
同名的自訂 skill（見下方「自家 Skills」）以專案 repo 的 `.agents/skills` 版本為先。

## 載入規則

- 進入適用步驟前才載入，不一次預載所有 skill。
- 讀完該 `SKILL.md`，以及它要求讀的 references，再執行。
- 「使用者呼叫型」skill 不能由 Skill 工具自動觸發，直接讀 `SKILL.md` 照做。
- 一個步驟可以疊多個 skill（例如 `implement` 內部會用 `tdd`、`code-review`），逐個載入，不要憑印象。

## 宣告格式

每個步驟開始前、動手之前，先用一行說明這步用了哪些 skill：

```
使用 Skill：grill-with-docs、domain-modeling（釐清需求並更新 GLOSSARY.md）
```

- 這步不需要任何 skill 時寫 `使用 Skill：無`。
- 步驟中途追加載入 skill，要再宣告一次。
- 載入失敗（找不到來源）要在同一行註明，見「來源解析」第 3 點。

## 路由表

「呼叫」欄：**人** 為使用者呼叫型（只在使用者要求或 workflow 規定的階段進入），**模** 為模型可自行取用。

### 主流程

| 情境 | Skill | 呼叫 |
|---|---|---|
| 在 repo 裡釐清想法、需求 | `grill-with-docs` | 人 |
| 沒有 repo 的計畫、設計、文章 | `grill-me` | 人 |
| 訪談本體（通常由上面兩個內部使用） | `grilling` | 模 |
| 需求中的用語含糊、重載 | `domain-modeling` | 模 |
| 設計 module 的形狀、介面、seam | `codebase-design` | 模 |
| 問題要跑得起來才能回答 | `prototype`（前後用 `handoff`） | 模 |
| 對話整理成 spec | `to-spec` | 人 |
| spec 拆成 tracer-bullet tickets | `to-tickets` | 人 |
| 實作單一 spec 或 ticket | `implement` | 人 |
| 一次實作整份 spec（多 agent） | `implement-spec` | 人 |
| 寫程式、修 bug 的紅綠燈循環 | `tdd` | 模 |
| 審查 diff（Standards + Spec） | `code-review` | 模 |
| 開 PR、寫 PR 內容 | `pr` | 模 |
| 做完後檢討 agent 環境 | `retro` | 人 |

### 入口與支線

| 情境 | Skill | 呼叫 |
|---|---|---|
| 累積的 bug 與需求要分流 | `triage`（只處理外部進來的 issue，不處理 `to-tickets` 產出） | 人 |
| 難查的 bug、flaky、回歸 | `diagnosing-bugs` | 模 |
| 一個 session 裝不下的大工程 | `wayfinder`，收斂後回主流程的 `to-spec` | 人 |
| 讀資料、查證、留下有引用的筆記 | `research` | 模 |
| 定期整理架構、找深化機會 | `improve-codebase-architecture` | 人 |
| 只有人能做的步驟（憑證、後台設定） | `wizard` | 模 |

### 輔助

| 情境 | Skill | 呼叫 |
|---|---|---|
| 不知道該用哪個 | `ask-matt` | 人 |
| 一則訊息沒講清楚，要重新說明 | `wait-what` | 人 |
| 換 harness、換目錄、交接 | `handoff` | 人 |
| 寫給 agent 讀的文件（skill、AGENTS.md、被指到的 doc） | `writing-for-agents` | 模 |
| 第一次在某個 repo 用工程類 skill | `setup-matt-pocock-skills` | 人 |

## 自家 Skills

尚無。之後新增（例如 Python、人類寫作類）放在獨立 repo，並在這裡補一張表，格式與上面相同，來源路徑另列。

## 備註

- `setup-matt-pocock-skills` 要產生的 `issue-tracker.md`、`triage-labels.md`、`domain.md` 已預先放在 `docs/agents/`，設定為 GitHub Issues，所以新專案不用再跑它；跑了反而會在 `CLAUDE.md` 產生重複的區塊。
- 上游 skill 有更新時，先 `git pull` fork，再核對本表是否需要調整。
