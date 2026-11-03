# Council

主席（主 session）召集多位委員，就一個問題兩輪作答、匿名互評，主席查證後綜合。目的是在花時間寫程式或等模擬器之前，先把能被推翻的地方找出來。做法沿用 `~/Documents/Yang-Home/research1/docs/agents/council.md`，路徑改成本 repo。

## 什麼時候開

| 類型 | 時機 | 題目重點 |
|---|---|---|
| 開題 council | 一個階段開始、寫第一張 ticket 前 | 問題、方法、最便宜的推翻路徑 |
| 檢討 council | 每個階段結案後，**不論結果好壞** | 結果說明什麼、沒排除的解釋、下一步、要不要停 |
| 設計 council | 卡住的設計或架構問題 | 幾種截然不同的介面，比深度、局部性、seam 位置 |

「階段」的判準：它的結果會改變下一步做什麼。本專案的階段：純 Python 第一版（T1–T13）、模擬器接線、Web 模擬器校正、提交前。

## 流程

1. **Brief**（`notes/council/<topic>/brief.md`，≤ 60 行）：問題、必讀檔案（路徑與行號）、每位委員的代號與角色、回答格式、字數上限。
2. **第一輪**：每位委員一個 `council-member` subagent，**同一回合平行啟動**，各自只看 brief 與檔案，回答放在一個 ```markdown 區塊回傳，主席原樣存成 `round1_<X>.md`。委員之間不能對話。
3. **匿名化**：主席把回答打亂、去掉身分，寫 `answers_anonymized.md`；對照表寫 `mapping_private.md`。
4. **第二輪**：每位委員讀匿名回答，回傳 `round2_<X>.md`：互評名次（含自己）、修正自己的過度措辭、新發現的盲點。小題目可以省略第二輪，但要在 synthesis 說明。
5. **主席查證**：每個要採納的說法先開檔或對照規則書核對，列成「說法 / 結果（屬實、未驗證、不得引用）/ 依據」的表。未驗證的推估不採納。
6. **Synthesis**（`synthesis.md`，≤ 150 行）：互評結果、共識、盲點、查證表、**裁決**（採納項逐條，對應 ticket 或 ADR）。
7. **寫入**：裁決寫成 Basic Memory decision 筆記（`decisions/`，tag `kibo-2026`、`council`），使用者確認前 `status: open`，確認後改 `accepted`。council 本身不改程式。

## 檔案

```text
notes/council/<topic>/
  brief.md  round1_A.md …  answers_anonymized.md  mapping_private.md
  round2_A.md …  synthesis.md
```

委員沒有 Bash，讀不了 PDF；規則書與手冊的文字版放 `docs/reference/*.txt`（不進版控，用 `pdftotext -layout` 產生）。

## 主席義務

- 委員的分數只供參考；採不採納看查證，不看票數。
- 裁決只能**收緊**既有門檻，或開新的實驗；不得在看數據後放寬門檻。
- 使用者有否決權：裁決以選項呈現，使用者確認後才寫 `accepted`。
- 小問題不開大 council：兩位委員、一輪也可以，但 brief 與 synthesis 仍要寫。
