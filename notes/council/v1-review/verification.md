# 主席查證（第一輪，2026-11-04）

| 說法（委員） | 結果 | 依據 |
|---|---|---|
| 預設參數下 10 點 80%、12 點 100% 的場景在 t=0 就刪點（D） | **屬實** | 主席重跑 40 場：10 點 32/40、12 點 40/40，平均刪 0.8／2.1 |
| 手冊範例在「相機原點」與「機體中心」兩種對中算法下都是 0.0°，分不出伺服器用哪種（D） | **屬實** | `judge(p, cp)` 與 `camera_offset=(0,0,0)` 皆 0.000° |
| 手冊 6.3.1 的對中是「direction from the vehicle to the AR marker」（B、A） | **屬實** | manual.txt:1694-1696 |
| 規則書 2.2.3 逾時只說「沒有完成回報的分」，沒說已得分作廢（A、B、C） | **屬實** | rulebook.txt:317-318 |
| 規則書 #12、#20 字面為「after/passes all CheckPoints」（A、B） | **屬實** | rulebook.txt:745、771 |
| 規則書引用的 score calculation table 不在 v1.1 PDF（A） | **屬實** | rulebook.txt:768-774 只有名詞定義，無表 |
| `_to_gray` 在 try 之外（D） | **屬實** | user_node.py:168 對 171 |
| `run_mission` 沒有 try/finally，例外會跳過 `mission_finish`（D） | **屬實** | mission.py:273-310 |
| 相機增益只在相對移動零誤差時成立，σ=5 cm 增益消失（B） | **屬實（方向）** | 主席重跑 30 場：無相機 104.8；σ=0／0.02／0.05 → 114.4／113.1／105.5 |
| 真速 0.05、12 點時 Goal 僅 10/20；規劃知道真速可大幅改善（B、C） | **屬實** | 主席重跑 20 場：38.1 分、10/20；oracle 84.6 分、18/20 |
| 四世界下刪點是 minimax：A/T1 小輸、其餘大贏（C） | **屬實** | 主席重跑 n=12、0.10：A/T0 +88.8、A/T1 −1.9、B/T0 +111.5、B/T1 +20.7；0.05：+27.7／−5.8／+38.1／+4.7 |
| C 的「最後一刻才刪 −7%~−80%」「可回補持平」 | **未重現** | 需另寫策略，暫不採納為裁決依據 |
| `move_timeout_sec=60` 低於最長腿（marker 11→12 約 7.3 m ÷ 0.1 = 73 s）（B、D） | **屬實** | field.py 的座標；mission.py:85 |
| 假裁判 `score()` 逾時整場 0 分是假設（A、B、C） | **屬實** | fake_robot.py:160-164 |
| Goal 不在 checkpoints 清單時 parse 失敗三次直接 finish，整場 0（A、B、D） | **屬實** | checkpoints.py:98-99、mission.py:280-283 |
| `#!/usr/bin/env python` 在 Melodic 可能是 2.7（D） | **未驗證** | 需看官方範本的 shebang |
