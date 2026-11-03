# Council brief：第二階段（council 裁決 R1–R5 實作完）的檢討——該停還是該繼續？

日期 2026-11-04。主席：主 session。類型：檢討 council，小型（兩位委員、一輪）。
背景：v1-review council 的裁決 R1–R5 已實作並經兩軸 reviewer 審過（`notes/council/v1-review/synthesis.md`、
commit「依兩軸審查修正 T14–T18」）。97 個測試。仍然沒有官方模擬器（需隊伍帳號下載）。
使用者不在場，授權自主規劃與測試；裁決會以 `status: open` 寫入 Basic Memory。

## 問題

1. **這個階段的結果說明什麼？** 哪些結論現在站得住、哪些仍是假模型產物？（看 `docs/solution/README.md` 第 5 節的兩張表）
2. **沒有模擬器，還有沒有「做了會改變上機第一小時結果」的事？** 列出最多三件，各附驗收方式與「不做的代價」。若你認為沒有，明說「該停」並給理由。
3. **哪些現有工作在上機前就該被懷疑或拆掉？**（例如相機接線、探針旗標、`kibo.tune` 的變體）
4. **使用者回來後第一件該做的決定是什麼？**（除了下載模擬器）

## 必讀

- `notes/council/v1-review/synthesis.md`（裁決與驗收）、`docs/solution/README.md` 第 5、6 節、`docs/solution/tickets.md` 第二階段、`ros/README.md` 劇本。
- 程式：`src/kibo/mission.py`（`record_leg`、`move`、`visit`、`run_mission`）、`src/kibo/tune.py`、`ros/user_node.py`（`survey`、`_call`、`_config`）。
- Basic Memory（只讀）：tag `kibo-2026` 的筆記，特別是「v1-review council」決策與「速度校正的三次失敗」「四世界後悔表」。

## 委員

| 代號 | 角色 |
|---|---|
| E | 務實的隊長：資源有限、期限 2027-01-20，要的是能交、能跑、分數穩 |
| F | 懷疑論者：預設「沒有資料的工作都是在自我安慰」，要找出該停的理由 |

## 格式

一輪，≤ 1000 字，依題號作答，每點附來源；無來源標 `未驗證`；最後「值得記錄」≤ 3 條；回答放在一個 ```markdown 區塊回傳，不寫檔。
