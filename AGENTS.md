# AGENTS.md

Claude Code、Codex 等 agent 共用的指令。Claude 透過 `CLAUDE.md` 匯入本檔，請只在這裡維護一份。

## 語言
- 與使用者溝通一律使用繁體中文；程式碼、識別字、技術名詞維持原文。

## 工作方式
- 動手前先讀現有程式碼與慣例，風格與周圍保持一致。
- 有破壞性或對外可見的動作（刪除、覆寫、推送、發佈）先確認。
- 回報結果要如實：測試失敗就貼輸出，跳過的步驟要說明。

## Skill 載入
下列流程技能均指 Matt 原版：grill-with-docs、to-spec、to-tickets、implement、implement-spec、tdd、code-review、pr、retro、writing-for-agents，其餘見路由表。
進入適用步驟前，依 `docs/agents/skill-routing.md` 的「來源解析」找到來源，讀取該 `SKILL.md` 與它要求的 references，再執行；不能只憑名稱模擬流程，也不一次預載所有技能。
缺少來源就回報名稱與受阻步驟；自家 skills 依同一份路由表載入。

**每個步驟動手前，先用一行說明用了哪些 skill**，格式見路由文件的「宣告格式」。

## 交付
追蹤用本 repo 的 GitHub Issues（類別用 `kind:*` 標籤，狀態用標籤與指派）；交接格式、worktree 與 Git 約定、升級規則、輕量路徑見 `docs/agents/delivery.md`。
**任何改動都先開新 worktree**（一張 issue 一個 worktree、branch、PR），不在 main 上直接 commit。

## 角色
Claude 與 Codex 都有三個標準 agent：planner、worker、reviewer。職責、權限與模型見 `docs/agents/roles.md`；設定檔在 `.claude/agents/` 與 `.codex/agents/`，兩邊保持一致。

## 專案背景
第 7 屆 Kibo-RPC：為 ISS 的 Int-Ball2 寫 ROS 任務程式。規則摘要在 `docs/kibo/rules.md`，API 在 `docs/kibo/api.md`，用語在 `GLOSSARY.md`。
官方模擬器實際怎麼評分、怎麼出題、哪裡會讓整場沒有成績：`docs/kibo/simulator-internals.md`；一次移動要幾秒與各場實測：`docs/kibo/motion-model.md`。
- 語言只用 **Python**，執行環境是 **3.6.9／ROS 1 Melodic**（`docs/adr/0001-python-for-ros-melodic.md`）。`src/` 的程式不能用 3.7 以後的特性，不能依賴映像沒有的套件。
- 官方範本中標 `DO NOT REMOVE` 的 `/ib2_user/start`、`/ib2_user/stop`、`/ib2_user/ready` 不得移除。
- 只改 `krpc_user/` 與 `src/`；解壓後的 `sim/` 內其他目錄是官方基礎設施，不改。
- 決賽程式要給 JAXA 審查安全性：迴圈要有次數與時間上限、Action 要有逾時與取消、不做無限重試（手冊第 5 章）。
- 邏輯寫成純函式放 `src/kibo/` 並用 pytest 測；ROS 節點只做接線。

## Council
階段開始前開**開題 council**，每個階段結案後開**檢討 council**，卡住的設計開**設計 council**（`docs/agents/council.md`）。委員是 `council-member` subagent，平行啟動、匿名互評、主席查證後裁決；裁決寫成 Basic Memory decision，使用者確認前 `status: open`。

## 開發流程
預設走 `docs/agents/workflow.md`：釐清、spec、tickets、實作（tdd）、審查、回顧。不跳階段。
環境見 `docs/agents/dev-env.md`，驗證指令見下方「驗證指令」區塊。

來源：org fork `Yang-Home-99/matt-skills`（上游 `mattpocock/skills`）。

## 驗證指令
- 安裝：`uv sync --locked`
- 格式：`uv run ruff format --check .`
- 靜態檢查：`uv run ruff check . && uv run pyright && uv run vermin --target=3.6- --no-tips --violations src ros`
- 測試（全部）：`uv run pytest`
- 測試（單檔）：`uv run pytest tests/test_x.py`
- 一次跑完上面全部：`scripts/check.sh`（推送前跑；`scripts/install-hooks.sh` 可把它掛成 pre-push hook）

動到會進 `krpc_user/` 的程式時，另外在本機模擬器跑一次（`scripts/sim.sh run`）並附上結果；細節見 `docs/agents/dev-env.md`。

## Agent skills

`setup-matt-pocock-skills` 的設定已預先完成，不需要重跑；重跑會在 `CLAUDE.md` 產生重複的區塊。

### Issue tracker

GitHub Issues（`Grasonyang/kibo-2026`）。See `docs/agents/issue-tracker.md`.

### Triage labels

五個標準角色，標籤字串不改名。See `docs/agents/triage-labels.md`.

### Domain docs

single-context：根目錄一份 `GLOSSARY.md` 加 `docs/adr/`。See `docs/agents/domain.md`.
