# Issue tracker: GitHub

Issue 與 spec 放在本 repo 的 GitHub Issues（`Grasonyang/kibo-2026`），用 `gh` CLI 操作。狀態流轉見 [delivery.md](./delivery.md)。

`gh` 會從 `git remote -v` 推斷 repo；在 clone 裡執行時不用指定。

## 基本操作

- **建立**：`gh issue create --title "..." --body "..." --label "..."`，多行內容用 heredoc。
- **建立並設定類別與上層**：`gh issue create --label kind:task --parent <上層編號或 URL> --title "..." --body "..."`。個人帳號沒有 Issue type，類別用 `kind:*` 標籤。
- **讀取**：`gh issue view <number> --json number,title,body,labels,comments`
- **列出**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，依需要加 `--label`、`--state`。
- **留言**：`gh issue comment <number> --body "..."`
- **標籤**：`gh issue edit <number> --add-label "..."` 或 `--remove-label "..."`
- **關閉**：`gh issue close <number> --comment "..."`
- `.github/ISSUE_TEMPLATE/` 的表單只在網頁介面生效；CLI 與 agent 建立時，正文要自己照表單的欄位寫。

## Sub-issue 與依賴

需要 `gh` 2.102 以上（`--parent` 與依賴旗標在個人 repo 是否可用，第一次用時實測並回來更新這句）：

- **設為 sub-issue**：建立時用 `--parent`，或事後 `gh issue edit <parent> --add-sub-issue <child>`；移除用 `--remove-sub-issue`。
- **加上依賴（被擋住）**：`gh issue edit <child> --add-blocked-by <blocker>`；移除用 `--remove-blocked-by`。
- **查依賴**：`gh api repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by --jq 'map({number,state})'`

`issue_dependencies_summary` 欄位會延遲幾秒才更新，要判斷是否被擋住，讀上面的清單。blocker 全部關閉，ticket 才算解除。

## PR 不當作需求入口

**PRs as a request surface: no.** 外部 PR 不走 triage 流程。若要改成 yes，編輯這裡，`/triage` 會讀這個旗標。

## 當 skill 說「publish to the issue tracker」

建立一個 GitHub issue，標籤帶 `kind:*`；準備好交給 agent 時加 `ready-for-agent`。

## 當 skill 說「fetch the relevant ticket」

用上面的「讀取」。

## Wayfinding 操作

給 `/wayfinder` 用。**地圖**是一個 issue，**子 ticket** 是它的 sub-issue。

- **地圖**：標籤 `wayfinder:map` 的單一 issue，正文放 Notes、Decisions-so-far、Fog。
- **子 ticket**：用 `--parent <地圖>` 建立的 sub-issue，標籤 `wayfinder:<type>`（`research`、`prototype`、`grilling`、`task`）。被認領後指派給負責的人。
- **阻擋**：用原生依賴（見上方）。
- **前線查詢**：列出地圖的開啟中子 ticket，排除有未關閉 blocker 或已有 assignee 的，依地圖順序取第一個。
- **認領**：`gh issue edit <n> --add-assignee @me`，這是 session 的第一個寫入動作。
- **解決**：`gh issue comment <n> --body "<答案>"`，接著 `gh issue close <n>`，再把脈絡指標（gist 加連結）附到地圖的 Decisions-so-far。
