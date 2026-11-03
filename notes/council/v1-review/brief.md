# Council brief：第一版純 Python 解法的檢討與下一階段開題

日期 2026-11-04。主席：主 session。類型：檢討 council（T1–T13 結案）兼下一階段開題。
背景：沒有官方模擬器（需隊伍帳號下載），所有數字來自假機器人；使用者不在場，裁決會以 `status: open` 寫入 Basic Memory 等確認。

## 問題（每題都要答）

1. **檢討**：第一版的設計決策哪些站得住、哪些最可能被模擬器推翻？列出前三個最可能被推翻的，各附「最便宜的檢驗方式」。
2. **刪點策略的避險**：規則書附錄 #20 說 Pt_goal 是「passes all CheckPoints within the time limit and reaches the GoalPoint」。在這個條件未驗證前，「先保 Goal、來不及就刪點」該改成什麼？給出一個可以在拿到模擬器前就實作、且在兩種規則解讀下都不會最差的策略。
3. **假機器人的保真度**：要讓 `kibo.tune` 的結論能轉移到真模擬器，假機器人最該補的三項動力學或行為是什麼（例如微重力擾動、到點後的殘餘振盪、導航漂移、action 回報比實際停穩早或晚）？每項附最便宜的實作方式與它會改變哪個結論。
4. **沒有模擬器時，下一階段最值得做的三件事**（每件附驗收方式）與**該停下來不做的事**。
5. **拿到模擬器後的第一小時**：核對順序，先驗什麼、怎麼驗、驗到什麼就要改程式。

## 必讀

- 規則：`docs/kibo/rules.md`；原文 `docs/reference/rulebook.txt`（2.2.2 前提、2.3 計分、附錄名詞 #7、#8、#18–#21）。
- API：`docs/kibo/api.md`；原文 `docs/reference/manual.txt`（5 章 Tips、6.3 API、6.4 範本、6.5 錯誤處理）。
- 解法：`docs/solution/spec.md`（實作決策 38–53 行）、`docs/solution/README.md` 第 5 節假設表、`docs/solution/ideas.md`。
- 程式：`src/kibo/mission.py`（`MissionConfig` 82–100、`settle` 181–198、`visit` 251–265、`run_mission` 273–）、`src/kibo/budget.py`（`plan_within_budget` 67–）、`src/kibo/fake_robot.py`（`FakeRobotConfig` 21–36、`move_to` 82–105、`notify_checkpoint` 132–142）、`src/kibo/judge.py`、`ros/README.md` 核對清單。
- Basic Memory（只讀）：搜尋 tag `kibo-2026` 的六篇筆記，特別是「審查後的修正與兩個待驗證的規則假設」「相機修正接線與假模型下的效益」。

## 委員

| 代號 | 角色 | 重點 |
|---|---|---|
| A | 規則律師 | 只認規則書與手冊的字面與結構，找我們對規則的誤讀與過度推論 |
| B | 自由飛行機器人控制工程師 | Int-Ball2 的動力學、ROS action 的實際行為、導航與相機的誤差來源；假機器人哪裡假得危險 |
| C | 競賽策略者 | 10 次平均下的期望值與方差，哪些決策在分數上真的重要，哪些是自我感覺良好 |
| D | 魔鬼代言人兼軟體審計 | 假設「第一次上模擬器就掛」，從 ROS 接線、時間、例外、複雜度找最先壞的地方；哪些工作是過度工程 |

## 格式

- 第一輪 ≤ 1500 字（中文字），依題號作答；每點附來源（`檔案:行` 或規則書章節）；無來源標 `未驗證`。
- 最後一節「值得記錄」≤ 5 條。
- 回答放在一個 ```markdown 區塊回傳，不寫檔。
