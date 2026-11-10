# G（規則律師）第一輪

## 1. 結果說明什麼
- 站得住：判定算式、每點只判第一次通知、Goal 用當下姿態補判，都是讀 judge.py 得來（simulator-internals.md J1–J10）。程式遵守手冊 6.5「移動失敗不回報」：`moved` 為真才通知（mission.py:437）。
- 只在本機成立：J11/J12 寫明評分模組不算分、不看時限。「Lv3 幾場」只是 judge.py 的等級，不是比賽分數。規則書 2.2.5 說資格賽分數是 10 場平均，倍率、時限、Pt_goal 全在伺服器（規則書附錄 #16–#21）。
- 規則書 3.1 的硬條件：只有 Preliminary 畫面上狀態是 FINISHED 的程式才能按 SUBMIT，FAILED 不行。本機 20 場沒人驗證過這一關，這比任何一場的等級重要。

## 2. 本機最佳化逐項（風險／最便宜檢驗）
- **起跑保護（10 秒）**：規則書附錄 #7 說計時從 Release 完成起算。若 Web 的時鐘從 /ib2_user/start 算，最多白吃 10 秒。更大的疑點是 `/gs/data` 是本機 API 節點的內部接線，實機可能有別的發佈者或訂閱者而白等 10 秒（user_node.py:83,261–270，`未驗證`）。檢驗：Web 第一場看 log 的 "event listeners connected after Xs"。
- **尾段自判／兩成緩衝**：緩衝讓 Lv3 等待最多多 3 秒（mission.py:103）。風險是 E9 的導航延遲換個環境可能不同，緩衝反而拖時間。檢驗：Web 回報的 level 對比自判。
- **保險 15 秒**：沒有規則依據。附錄 #8 只說超過時限後的動作無效，逾時是否整場歸零要問（questions #2）。檢驗：問主辦，不用試。
- **ctl.yaml 參數照抄**：速度模型（motion-model）是 Gazebo 控制器。實機與 Web 若有擾動（規則書 2.2.2 #3、附錄 #22），腿的秒數會偏。校正只往慢修、最多 2 倍（mission.py:241–286），方向安全。檢驗：Web 第一場看 "speed calibrated"。
- **RES_OPTIONS**：只是環境變數，無害，審查看得懂。
- **Goal 排最後**：字面最安全（規則書 2.2.4、附錄 #12），維持。

## 3. 規則書／手冊合規
1. **2.2.3 2b 的相機 1 秒**：我們只靠導航自判，相機只記錄。J1 顯示模擬器本身也用導航，所以本機沒問題。但規則書 2.3.1 寫「marker 在相機中央」，實機決賽的判定來源未驗證。審查者會問「為什麼不用相機」，答案要備好（ideas.md、E6：相機深度差 15 cm）。
2. **手冊 6.3.1 說「確認三條件都滿足且穩定後才送」**。`should_notify = level>0 and moved`（mission.py:437）在不穩定時也會送 Lv1。這與字面不符，但沒穩定就不送必定 0 分，且 J7 只判第一次。屬於有意的偏離，要在文件寫明理由。
3. **2.2.4 完成回報「必須在抵達 GoalPoint 時送出」**：`run_mission` 在 abort、例外、Goal 移動失敗時仍呼叫 `mission_finish`（mission.py:473–476）。這在字面上是不在 Goal 就回報完成。理由合理（倍率乘在全部分數上）。但審查會挑，建議在 Goal 未到時也在程式註解與 log 標明原因，並列入給主辦的提問。
4. **探針旗標**：`deliberate_late_after` 是刻意超過時限的程式碼（mission.py:441–446），`skip_one_waypoint`、`notify_even_if_level0` 也在。決賽審查看原始碼，JAXA 目的是「不影響軌道上的 IB2」（規則書 4.1 1)）。即使預設關、靠 ROS 參數開（user_node.py:528–530），出現在原始碼就會被問。**提交前移除**，不是只確認 launch 沒帶。
5. **手冊第 5 章**：迴圈有上限（mission.py:498 `range`；settle 的 `max_samples`；user_node 的 EVENT_MAX_POLLS）。notify 15 秒逾時、cancel 等 5 秒都有上限，合規。`_bounded` 的 daemon thread 逾時後留在背景，不算洩漏（5.11 要求清理 thread，這裡未清理，低風險）。
6. **提交包帶假機器人與 tune**：規則書 4.1/4.3.1 只說「審查原始碼」，細節「稍後公布」，`未驗證`。fake_robot.py、tune.py、simulate.py、scoring.py（假分數 10/6/3、Goal 20）不進 ROS 路徑，但混在 src/kibo 會被讀。便宜做法：提交包只拷執行路徑上的模組。

## 4. 沒帳號前會改變 Web 第一小時的事（最多三件）
1. **把探針旗標從原始碼拿掉或用編譯期移除**。驗收：grep 提交包無 "probe"。代價：決賽審查打回，或第一次 Preliminary 就帶著刻意逾時的路徑。但 Web 第一小時本來就會要用這些旗標定規則世界（ros/README.md:64–68），所以改成「分支或第二份檔案」而不是刪除。
2. **寫好一份 Web 第一場的核對表與 log 判讀**（"listeners connected"、"speed calibrated"、level 與自判差）。驗收：表格有預期值與判定準則。代價：第一小時白燒次數，而 Web 次數上限未知（questions #8）。
3. **確認程式在 Preliminary 一定能 FINISHED**（規則書 3.1）：模擬 mission_start 失敗、get_checkpoints 失敗、節點例外時，節點是否乾淨結束。驗收：已有 fake 測試涵蓋；只需對照 FAILED 的可能原因。代價：整隊無法提交。
否則「該停」，其餘都是猜 Web 行為。

## 5. 使用者回來最該先決定
- **第 3 項的 `mission_finish` 在未到 Goal 時要不要送**（正文 3.3）：這是被忽略的一條，屬於規則字面對上分數倍率的取捨，要由使用者定。
- **提問清單 #11（Goal 能不能先過）與 #12（judge.py 是否同一份）要在 2027-01-20 12:00 前送**；以 Web 第一場的結果能回答的就不用問。

## 值得記錄
1. 規則書 3.1：只有 Preliminary 狀態 FINISHED 才能 SUBMIT，FAILED 不行。這是提交前的硬閘門。
2. 手冊 6.3.1 要求「穩定後才送」與程式 mission.py:437 的「不穩定也送 Lv1」是有意的偏離，理由應寫進 decision。
3. 規則書附錄 #8：Mission Finish 是「開始回報」的時刻，之後動作無效，所以完成回報的呼叫時刻就是計時終點。
