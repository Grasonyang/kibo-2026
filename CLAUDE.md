@AGENTS.md

## Claude Code 專屬
- 三個標準 subagent（planner、worker、reviewer）放在 `.claude/agents/`，定義見 `docs/agents/roles.md`。

## 使用 Codex（選用）

預設不用。只在使用者明說要用，或 `docs/agents/workflow.md` 的決策支線需要跨模型意見（例如單向門的 PR）時才用。

### 已串接的方式
已安裝 OpenAI 官方外掛 `codex@openai-codex`（user scope，v1.0.6，來源 `openai/codex-plugin-cc`）。它在 Claude Code 裡呼叫本機的 Codex CLI，不是 MCP。2026-10-21 `/codex:setup` 回報 ready（Codex CLI 0.156.1、ChatGPT 登入有效）。

| 指令 | 用途 | 誰能觸發 |
|---|---|---|
| `/codex:review [--wait\|--background] [--base <ref>] [--scope auto\|working-tree\|branch]` | 一般程式碼審查，唯讀 | 只有使用者 |
| `/codex:adversarial-review [同上參數] [焦點]` | 挑戰實作取向與設計假設 | 只有使用者 |
| `/codex:rescue [--background\|--wait] [--resume\|--fresh] [--model ...] [--effort ...] <任務>` | 交給 Codex 調查或修正，**會寫檔** | 使用者；也可由 `codex:codex-rescue` subagent 轉送 |
| `/codex:status`、`/codex:result`、`/codex:cancel` | 管理背景工作 | 使用者 |
| `/codex:transfer` | 把目前 session 轉成可續接的 Codex thread | 只有使用者 |
| `/codex:setup` | 檢查 Codex 是否就緒 | 使用者 |

### 主 agent 的規則
- `review`、`adversarial-review` 外掛設成只有使用者能下。需要跨模型審查時，**提示使用者執行**並建議參數（例如 `/codex:review --base main --wait`），不要自己用 Bash 繞過去。
- `codex:codex-rescue` 的描述是「卡住時主動使用」，本專案**不主動使用**，除非使用者要求。它可能寫檔，委派時限定在單一 worktree。
- 外掛有自己的內建 reviewer，**不讀** `.codex/agents/*.toml`；那三個 agent 是給直接開 Codex 用的。
- Stop 時的 review gate 預設關閉，不要啟用（`/codex:setup --enable-review-gate` 會讓每次停止前都跑一次 Codex，耗額度又拖慢）。
- Codex 的輸出是意見，不是結論。逐條對照程式碼驗證，成立才轉成 issue 留言或 PR 意見。
- 宣告行要註明，例如「使用 Skill：code-review（跨模型：Codex review）」。
- 呼叫 Codex 會把相關程式碼送到 OpenAI；含機密的內容不要傳。

### 後備：直接跑 Codex CLI
想套用 `.codex/agents/reviewer.toml` 的模型與指令時，可以直接用 Bash（唯讀由 Codex sandbox 強制）：

```bash
codex exec -s read-only --ephemeral -C <worktree 路徑> \
  -m gpt-6-luna -c model_reasoning_effort=high -o <輸出檔路徑> \
  "依 .codex/agents/reviewer.toml 的 developer_instructions 擔任 reviewer。審查 <base>..HEAD 的 <Standards 或 Spec> 軸。"
```

flag 來自 `codex exec --help`（0.156.1），尚未實際試跑；不使用 `--dangerously-bypass-approvals-and-sandbox` 或 `-s danger-full-access`。
