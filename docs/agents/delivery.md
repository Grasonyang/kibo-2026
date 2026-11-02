# 交付：追蹤、交接與 Git

planner、worker、reviewer 之間怎麼交接，工作怎麼記錄，程式碼怎麼進主幹。角色定義見 [roles.md](./roles.md)，流程順序見 [workflow.md](./workflow.md)。

## 追蹤系統

- **Issue 是交接契約本身**，放在本 repo 的 GitHub Issues。操作方式見 [issue-tracker.md](./issue-tracker.md)。
- 本 repo 在個人帳號下，沒有 org 的 Issue type 與跨 repo 看板。狀態用標籤與指派表示（見下方「狀態流轉」），需要時間軸再另外建 user Project。
- 不用 Linear。Matt skills 對 GitHub 有完整的操作範本（sub-issue、原生依賴、標籤），Linear 沒有。

### Issue 類別

| 類別 | 標籤 | 來源 | 用途 |
|---|---|---|---|
| Task | `kind:task` | `to-tickets` | 一張 tracer-bullet ticket |
| Bug | `kind:bug` | 人或 `triage` | 非預期的行為 |
| Feature | `kind:feature` | 人或 `triage` | 新功能的想法 |
| Spec | `kind:spec` | `to-spec` | 規格 |
| Decision | `kind:decision` | `wayfinder`、`grill-with-docs` | 待定案的決策，ADR 候選 |
| Research | `kind:research` | `research` | 查證與調查 |
| Chore | `kind:chore` | 人 | 依賴、設定、重構、CI |

每個類別在 `.github/ISSUE_TEMPLATE/` 都有對應的網頁表單，表單會自動帶上 `kind:*` 標籤；用 CLI 建立時要自己加 `--label kind:<類別>`。

### 狀態流轉

| 狀態 | 怎麼表示 | 誰做 |
|---|---|---|
| Backlog | 開啟中的 issue，沒有 `ready-for-agent` | 任何人 |
| Ready | 規格完整、blocker 全部關閉、加上 `ready-for-agent` | planner 或協調者 |
| In progress | issue 有 assignee（`--add-assignee @me`），並已建好 worktree | worker 認領 |
| In review | PR 已開、交付報告已貼 | worker |
| Done | 使用者確認後 squash merge，PR 的 `Closes #<n>` 自動關閉 issue | 協調者 |

## 交接契約

### 1. Ticket（planner 交給 worker）

正文格式照 `to-tickets`，用 Issue form 的 Task：

```markdown
## Parent
#<上層編號>（沒有就省略）

## What to build
從使用者角度描述做完後能做到什麼，不寫逐層實作清單，不寫會過期的檔案路徑。

## Acceptance criteria
- [ ] ...

## Blocked by
原生依賴已設定時，省略這一段。
```

規則：一張 ticket 一個 worktree；blocker 要用原生依賴連結；XL 要拆；ticket 有疑問，worker 回報而不是自己改 spec。

### 2. 交付報告（worker 交給 reviewer 與協調者）

寫在 PR 描述（`.github/PULL_REQUEST_TEMPLATE.md`）加一則 issue 留言，內容固定：

```markdown
## 交付報告
- **Ticket**：#<n>
- **範圍**：<base>..HEAD
- **改了什麼**：<一到三句，用 GLOSSARY.md 的用語>
- **驗證**（專案「驗證指令」區塊的實際輸出）：
  - 格式：<指令> → <通過或失敗>
  - 靜態檢查：<指令> → <結果>
  - 測試：<指令> → <結果，例如 42 passed>
- **未決項目**：<沒有就寫「無」>
- **使用的 Skill**：<清單>
```

### 3. 審查報告（reviewer 交給協調者）

以 PR review 或 issue 留言送出，一份報告只審一軸：

```markdown
## 審查報告
- **軸**：Standards 或 Spec
- **範圍**：<base>..HEAD
- **結論**：通過，或需要修改
- **問題**（沒有就寫「無」）：
  1. [blocker|major|minor|nit] `檔案:行`：<原因>。建議：<做法>
- **使用的 Skill**：<清單>
```

嚴重度：blocker 不修不能合併；major 應該修；minor、nit 由 worker 判斷。

## Worktree 與 Git

**任何改動都先開新 worktree**，包括文件的一行小修。一張 issue 對一個 worktree、一個 branch、一個 PR。

| 項目 | 規則 |
|---|---|
| 名稱 | `<issue 編號>-<短英文 slug>`，例如 `12-add-roles` |
| Worktree 位置 | `<repo>/.claude/worktrees/<名稱>`（已被 `.gitignore` 忽略），與 Claude Code 的預設一致 |
| Branch | 與名稱相同，從 `origin/main` 開出 |
| 建立 | `git fetch origin && git worktree add .claude/worktrees/<名稱> -b <名稱> origin/main` |
| 開工後 | 在 worktree 內先跑專案「驗證指令」的「安裝」 |
| Commit | 一句話描述「做了什麼與為什麼」；Claude 的 commit 附 `Co-Authored-By` |
| PR | 標題簡短，內文用 PR 範本，`Closes #<n>`；單向門加標籤 `one-way-door` |
| 合併 | 協調者在使用者確認後 squash merge，主幹保持線性 |
| 清理 | 合併後 `git worktree remove .claude/worktrees/<名稱>` 並刪除 branch |
| 不要 | 在 main 上直接 commit、`git push --force`、改寫已推送的歷史 |

初始化階段（本文件建立之前）的提交直接進 main，這是唯一例外。

## 升級規則

停下來、回報給使用者，不要硬撐：

- worker 對同一個失敗修了 2 輪仍未解決，回報卡點與證據。
- reviewer 與 worker 來回超過 2 輪仍不同意，交給使用者裁決。
- 發現需要改 spec、ticket 範圍或介面，回到 planner，不在實作中悄悄改。
- 要做破壞性或對外可見的動作（刪除、覆寫、推送、發佈、付費額度）。
- 需要的 skill 找不到來源（見 [skill-routing.md](./skill-routing.md)）。

## 輕量路徑

同時符合下列全部條件，可以略過 `grill-with-docs`、`to-spec`、`to-tickets`：

- 影響不超過約 30 行，且不改行為或介面。
- 沒有新依賴，沒有資料遷移。
- 做完能立刻用驗證指令確認。

例：錯字、文件小修、設定值調整。仍然要：開 worktree 與 branch、跑驗證指令、開 PR。Issue 可以只是一行 Chore。

## 知識放哪裡

| 內容 | 放哪裡 |
|---|---|
| 專案用語、ADR、spec、ticket、PR | 專案 repo（事實來源） |
| 跨專案的工作規範、角色、流程 | 模板 repo `Yang-Home-99/agent-config`（本 repo 於 2026-11-03 複製，不會自動更新） |
| session 檢查點、研究結論摘要、踩雷與環境筆記 | Basic Memory（`sessions/`、`infra/`、`projects/<專案>`） |
| 有替代方案與理由的研究決策 | 專案的 ADR；Basic Memory 的 `decisions/` 只放摘要並連到 ADR |
| `retro` 的環境改善建議 | 本 repo 的 issue；通用的再回報 `agent-config` |

## 模板來源

本 repo 的流程文件、agent 設定與 Issue 表單複製自 `Yang-Home-99/agent-config`（2026-11-03），之後獨立演進，不自動同步。差異：

- 沒有 org Project 與 Issue type，改用 `kind:*` 標籤與指派表示狀態。
- 語言層不用 Rust，原因見 [ADR-0001](../adr/0001-python-for-ros-melodic.md)。
- 領域是 Kibo-RPC，競賽規則與 API 摘要在 `docs/kibo/`。
