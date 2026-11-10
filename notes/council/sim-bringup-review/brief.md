# Council brief：「模擬器接線」階段結案的檢討

日期 2026-11-11。主席：主 session。類型：檢討 council，三位委員、一輪（小型；理由寫在 synthesis）。
使用者不在場，授權自主推進並合併到 main；裁決會以 `status: open` 寫入 Basic Memory，等使用者確認。

## 背景（事實，出處都在必讀檔案裡）

- 官方模擬器資源 2026-11-10 取得，評分模組、場景產生器、控制器的原始碼都讀過。
- 本機模擬器 20 場：easy 6／6、normal 8／8、hard 8–9／10、veryhard 9／12；除一場外全部 Lv3。
- 三種出過事的情況各有一個修正：起跑太快讓評分模組漏掉任務開始（兩場無成績）、到 Goal 時過早回報（一場 Lv1）、模擬器自己啟動失敗（擋不了）。
- **Web 模擬器沒上過**（需要隊伍帳號）。分數、時間倍率、5 分鐘時限都在伺服器端，本機看不到。規則書說模擬器有微重力擾動，下載包裡沒有。
- 資格賽程式提交截止 2027-01-20；給主辦的提問截止同日 12:00。

## 問題（依題號作答）

1. **這個階段的結果說明什麼？** 哪些結論現在站得住，哪些只在本機模擬器成立、換到 Web 模擬器或實機可能不成立？
2. **有哪些做法是「為本機模擬器最佳化」，在 Web 模擬器或實機反而可能害事？** 逐項評估：起跑保護（最多等 10 秒）、尾段自判、有餘裕時留兩成緩衝、保險 15 秒、時間模型的參數照抄模擬器的 `ctl.yaml`、`RES_OPTIONS=single-request`、Goal 排最後。各給「風險、最便宜的檢驗方式」。
3. **程式是否合乎規則書與手冊？** 特別看：規則書 2.2.3 的「辨識 AR marker、在餘裕內停 1 秒」（我們靠導航自判，相機只記錄）、2.2.4 的完成回報、手冊第 5 章的安全要求、探針旗標還在程式裡、提交包帶著假機器人與 tune。哪些在決賽審查會被挑出來？
4. **沒有 Web 帳號之前，還有沒有「做了會改變上 Web 第一小時結果」的事？** 最多三件，各附驗收方式與不做的代價。若認為沒有，明說「該停」。
5. **使用者回來後，最該先做的決定是什麼？**（issue #6 的保險秒數、#7 的 Web 模擬器與 POC 提問之外，還有沒有被忽略的）

## 必讀

- `docs/kibo/simulator-internals.md`（J、A、G、R、E 各表與對策）、`docs/kibo/motion-model.md`（實測表、「各難度能去幾個點」、「試過但沒採用」）、`docs/kibo/questions-for-poc.md`、`docs/solution/README.md` 第 5 節。
- 程式：`src/kibo/mission.py`（`slack` 214、`required_level` 221、`record_leg` 241、`settle` 298、`visit` 425、`run_mission`）、`src/kibo/settle.py`、`src/kibo/budget.py`、`ros/user_node.py`（`_wait_for_event_listeners` 236、檔案開頭的 `RES_OPTIONS`）。
- 規則書與手冊文字版：`/home/grason/Documents/kibo-2026/docs/reference/rulebook.txt`（2.2、2.3、附錄用語）、`/home/grason/Documents/kibo-2026/docs/reference/manual.txt`（第 5、6 章）。這兩個檔不在 worktree 裡，請用絕對路徑。
- Basic Memory（只讀）：tag `kibo-2026` 的筆記，特別是「官方模擬器原始碼揭露的評分與場景規則」「起跑太快會讓評分模組漏掉任務開始」「Goal 點的滾轉讀數會放大誤差」，以及兩篇舊的 council 決策。

worktree 根目錄：`/home/grason/Documents/kibo-2026/.claude/worktrees/13-council-sim-bringup`。

## 委員

| 代號 | 角色 |
|---|---|
| G | 規則律師：只認規則書與手冊的字面，找出會被判違規、或決賽審查會挑的地方 |
| H | 魔鬼代言人：預設「本機模擬器上的每個好結果都不會轉移到 Web 與實機」，逐項找理由 |
| I | 競賽策略者：目標是資格賽 10 場平均分數最高；看時間、等級、Goal 的取捨與還沒用到的分數 |

## 格式

一輪，≤ 1100 字，依題號作答，每點附來源（`檔案:行` 或規則書章節）；無來源標 `未驗證`；最後「值得記錄」≤ 3 條。
回答放在一個 ```markdown 區塊回傳，不寫檔。
