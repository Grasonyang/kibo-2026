# Reviewer 的 brief

協調者叫 reviewer 之前照這份寫 brief。reviewer 只看得到 brief 與 repo，brief 沒寫的它不知道。
誰審、審幾軸、何時審見 [roles.md](./roles.md) 與 [workflow.md](./workflow.md)；這裡只管 brief 怎麼寫。

## 寫 brief 的原則

- **給範圍，不給結論。** 寫「對照舊版逐條確認是否等價」，不寫「我確認過等價」。拿到結論的 reviewer 會回報同意。
- **要它查的寫成問題。** 你最沒把握的地方各寫一條，要求具體的檔案與行號，找得到反例就給數字。
- **說出已經決定的事。** 已知而且接受的取捨、council 的裁決、不在這次範圍的東西，各寫一句，reviewer 才不會把它們當成發現。
- **issue 全文貼進 Spec 的 brief**，留言也貼。相關的裁決貼原句。
- **範圍用 `origin/main`**（先 `git fetch`），不用本機的 `main`：本機的可能落後。

## 兩軸共用的開頭

```markdown
你是 reviewer，審查 **<Standards 或 Spec> 軸**。用繁體中文回報。

工作目錄（worktree）：`<絕對路徑>`
範圍：`git diff origin/main...HEAD`（`git log origin/main..HEAD --oneline` 看 commit）。
這是 issue #<編號>「<標題>」：<一句話說這次改動的定位，例如「不改變飛行行為的重構」>。
已經決定、不用再報的：<已知且接受的取捨、不在這次範圍的東西；沒有就寫「無」>

專案約束：`AGENTS.md` 的「專案背景」整節。這次特別相關的是：<挑兩三條，例如「`src/`、`ros/` 要能在 Python 3.6.9 跑」>

唯讀：
- 可以跑 `uv run pytest`、`uv run ruff`、`uv run pyright`、`git` 與 `gh` 的唯讀指令；測試請自己跑一次。
- worktree 裡的檔案一個都不改，也不 commit。要做突變驗證或新舊比對，先把 worktree 複製到你自己的
  暫存目錄（不含 `.venv`、`.git`），在副本裡改、在副本裡跑。
- 不跑 `scripts/sim.sh`。<模擬器正在跑的話加一句：它每次啟動都會把 worktree 的 `src/kibo/` 與 `ros/`
  同步進容器，所以這兩個目錄連暫時的改動都不行。>
- 結束前跑 `git status --short`，把結果寫進報告。
```

## Standards 軸

```markdown
標準來源（先讀）：`AGENTS.md`、`docs/agents/dev-env.md`、`docs/adr/`、`GLOSSARY.md`（用語一致），
以及周圍程式碼既有的風格（註解與 docstring 用繁體中文白話，說明「為什麼」）。
另外套用 `code-review` skill 第 3 步的 smell baseline（skill 的位置照 `docs/agents/skill-routing.md`
的「來源解析」找）：都是判斷題；repo 有文件的標準優先；工具（ruff、pyright、vermin）會擋的不用報。

用自己的眼睛確認，不要假設我做對：
1. <最沒把握的地方，寫成問題>
2. <…>
N. `src/` 與 `ros/` 有沒有 Python 3.7 以後的語法或標準庫（vermin 會擋一部分，新檔案請再看一次）。

<共用的「回報」段>
```

## Spec 軸

```markdown
規格是 issue #<編號>（`gh issue view <編號> --repo <owner/repo>`），全文：

> <issue 的標題、全文與留言，逐字貼上>

相關的裁決：<檔案與原句；沒有就寫「無」>

請回報：
(a) 規格要求但沒做或只做一半的。逐條對驗收條件，每條引用規格原句。<我自己在驗的項目註明「不用驗」，
    但請從程式判斷它會不會成立。>
(b) 規格沒要求的行為或範圍。<規格說行為不變的話：列出要對照的舊版檔案，`git show origin/main:<路徑>`。>
(c) 看起來做了但做錯的：<逐條列出要核對的對象，例如官方規則的原文對實作、測試名稱對它實際測到的事>
(d) 文件與程式是否一致；repo 裡（`notes/` 是歷史紀錄，不算）還有沒有指向舊名稱或舊位置的說法。
(e) 沒做到的地方，文件與 PR 的說明是否如實（有沒有把沒做的說成做了）。

<共用的「回報」段>
```

## 兩軸共用的「回報」段

```markdown
回報：照 `docs/agents/delivery.md` 的「審查報告」，一份清單、每條標嚴重度與 `檔案:行`。
- <Standards 軸加這一句：違反有文件的標準可以是 blocker 或 major；smell 是判斷題，最多 minor，
  並註明是哪個 smell。>
- 看過沒問題的面向各用一行說怎麼看的。
- 另列「沒辦法驗證的」：你想確認但做不到的事（例如要跑模擬器才知道的）。
- 「使用的 Skill」寫 `code-review`（<軸>）。
不客套、不重述 diff。<字數上限，通常 600 字>以內。
```

## 重構的審查另加

定位是「行為不變」的改動，兩軸各加這一段：

```markdown
這次改動宣稱行為不變。請找出新舊版結果不同的輸入：
- 邊界：對照 `git show origin/main:<舊檔>` 與新檔，逐條列邊界（空的輸入、門檻值的兩側、上限、
  關閉的開關），每個邊界說新舊是否相同；不同就給具體數字。
- 隨機輸入：在你的副本裡把舊檔另存一份（`git show origin/main:<舊檔> > <暫存路徑>`），寫一小段程式
  用幾千組隨機輸入各跑新舊兩版，回報不一致的輸入；全部一致就寫跑了幾組、輸入的範圍。
- 既有測試：`git diff origin/main...HEAD -- tests/` 是否只改了寫法、沒有動斷言。列出任何改了預期值、
  改了比較、被刪掉的斷言，以及因為改寫而失去牙齒（改壞程式也不會紅）的測試。
```

協調者自己另外留一份整場的比對：改動前先錄一批固定 seed 的假機器人任務（每場的通過點、等級、完成秒數、
分數、整份 log 的雜湊），改完再跑一次逐場比。reviewer 的隨機輸入抓單一函式的差異，這一份抓整場流程的差異。
