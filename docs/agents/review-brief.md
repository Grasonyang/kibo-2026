# Reviewer 的 brief

協調者叫 reviewer 之前照這份寫 brief。reviewer 只看得到 brief 與 repo，brief 沒寫的它不知道。
角色見 [roles.md](./roles.md)，審查報告的格式與嚴重度見 [delivery.md](./delivery.md) 的「審查報告」，兩軸的定義來自 `code-review` skill。

Standards 與 Spec 各寫一份、各開一個 reviewer、同一回合平行送出。

## 寫 brief 的原則

- **給範圍，不給結論。** 寫「對照舊版逐條確認是否等價」，不寫「我確認過等價」。拿到結論的 reviewer 會回報同意。
- **要它查的寫成問題。** 你最沒把握的地方各寫一條，條條要求具體的檔案與行號，找得到反例就給數字。
- **要它回報看過什麼。** 沒問題的面向也要一行「怎麼看的」，否則分不出「沒問題」與「沒看」。
- **issue 全文貼進 Spec 的 brief。** 相關的 council 裁決貼原句並註明哪些不在這次範圍。

## 兩軸共用的開頭

```markdown
你是 reviewer，審查 **<Standards 或 Spec> 軸**。用繁體中文回報。

工作目錄（worktree）：`<絕對路徑>`
範圍：`git diff <base>...HEAD`（`git log <base>..HEAD --oneline` 看 commit）。
這是 issue #<編號>「<標題>」：<一句話說這次改動的定位，例如「不改變飛行行為的重構」>。

唯讀：
- 可以跑 `uv run pytest`、`uv run ruff`、`uv run pyright`、`git` 與 `gh` 的唯讀指令。
- worktree 裡的檔案一個都不改，也不 commit。要做突變驗證，先把 worktree 複製到你自己的暫存目錄
  （不含 `.venv`、`.git`），在副本裡改、在副本裡跑 pytest。
- 不跑 `scripts/sim.sh`。<模擬器正在跑的話加一句：它每次啟動都會把 worktree 的 `src/kibo/` 與 `ros/`
  同步進容器，所以這兩個目錄連暫時的改動都不行。>
- 結束前跑 `git status --short`，把結果寫進報告。
```

## Standards 軸

```markdown
標準來源（先讀）：
- `AGENTS.md` 的「專案背景」：`src/`、`ros/` 要能在 Python 3.6.9 跑；迴圈與等待有次數與時間上限；
  邏輯放 `src/kibo/` 的純函式、ROS 節點只做接線；`src/kibo/` 整個進提交包，飛行程式不匯入 `kibo_lab`；
  `DO NOT REMOVE` 的三個 topic 不得移除。
- `docs/agents/dev-env.md`、`docs/adr/`、`GLOSSARY.md`（用語一致）。
- 周圍程式碼既有的風格：註解與 docstring 用繁體中文白話，說明「為什麼」。

另外套用 `code-review` skill 第 3 步的 smell baseline
（`~/Documents/Yang-Home/matt-skills/skills/engineering/code-review/SKILL.md`）：
都是判斷題；repo 有文件的標準優先；工具（ruff、pyright、vermin）會擋的不用報。

用自己的眼睛確認，不要假設我做對：
1. <最沒把握的地方，寫成問題>
2. <…>
N. `src/` 與 `ros/` 有沒有 Python 3.7 以後的語法或標準庫（vermin 會擋一部分，新檔案請再看一次）。

回報：照 `docs/agents/delivery.md` 的「審查報告」。每條寫 `檔案:行`、問題、引用哪條標準或哪個 smell、建議；
documented 標準的違反與 smell 的判斷題分開列。看過沒問題的面向各用一行說怎麼看的。
不客套、不重述 diff。<字數上限，通常 600 字>以內。
```

## Spec 軸

```markdown
規格是 issue #<編號>（`gh issue view <編號> --repo <owner/repo>`），全文：

> <issue 的標題與全文，逐字貼上>

相關的裁決：<檔案與原句；註明哪些不在這次範圍>

請回報：
(a) 規格要求但沒做或只做一半的。逐條對驗收條件，每條引用規格原句。<我自己在驗的項目註明「不用驗」。>
(b) 規格沒要求的行為或範圍。<規格說行為不變的話：列出要對照的舊版檔案，`git show <base>:<路徑>`。>
(c) 看起來做了但做錯的：<逐條列出要核對的對象，例如官方規則的原文對實作、測試名稱對它實際測到的事>
(d) 文件與程式是否一致；repo 裡（`notes/` 是歷史紀錄，不算）還有沒有指向舊名稱或舊位置的說法。
(e) 沒做到的地方，文件與 PR 的說明是否如實（有沒有把沒做的說成做了）。

回報：照 `docs/agents/delivery.md` 的「審查報告」。每條附 `檔案:行`。不客套、不重述 diff。<字數上限>以內。
```

## 重構的審查另加

定位是「行為不變」的改動，兩軸各加一條：

```markdown
這次改動宣稱行為不變。請找出新舊版結果不同的輸入：
- 對照 `git show <base>:<舊檔>` 與新檔，逐條列邊界（空的輸入、門檻值的兩側、上限、關閉的開關），
  每個邊界說新舊是否相同；不同就給具體數字。
- `git diff <base>...HEAD -- tests/`：既有測試是否只改了寫法、沒有動斷言。列出任何改了預期值、
  改了比較、被刪掉的斷言，以及因為改寫而失去牙齒（改壞程式也不會紅）的測試。
```

協調者自己另外留一份逐場比對：改動前後跑同一批隨機場景，比結果與 log 的雜湊（做法見 PR #26 的 Evidence）。
