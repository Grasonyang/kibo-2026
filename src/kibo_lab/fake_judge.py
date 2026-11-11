"""假裁判：照官方評分模組的行為記錄每一點過不過，最後用假設的分數表算分。

官方的規則集中在這裡（編號是 docs/kibo/simulator-internals.md 的表）：

- J7：每個 CheckPoint 只判第一次通知，沒過也記錄，之後的通知不重判。
- J9：完成回報時，Goal 點先前通過就算到達；否則用當下姿態對 Goal 點再判一次，
  通過的話 Goal 點也補記為通過。
- J10：任務開始之前、完成回報之後的通知一律忽略。

到點幾級用的是飛行程式自己那份 `kibo.judge`（從官方算式移植，有黃金值測試），
所以假裁判與自判同源：它測得出流程的錯，測不出判定算式本身的錯。
分數表與倍率是假設值（`kibo_lab.scoring`），只能相對比較。

假裁判不看時鐘，時間由呼叫端給：`mission_finish` 的 `at_sec` 是從任務開始起算的秒數。
"""

from typing import List, Optional

from kibo.checkpoints import CheckpointSet
from kibo.geometry import Pose
from kibo.judge import judge
from kibo_lab.scoring import DEFAULT_SCORING, Scoring


class FakeJudge(object):
    def __init__(self, checkpoints: CheckpointSet, scoring: Scoring = DEFAULT_SCORING) -> None:
        self.checkpoints = checkpoints
        self.scoring = scoring
        self.started = False
        self.finished_at: Optional[float] = None
        self.judged_ids: List[int] = []  # 已經被判過的點（過或沒過都算）
        self.passed_ids: List[int] = []
        self.passed_levels: List[int] = []  # 與 passed_ids 同順序
        self.goal_reached = False

    def mission_start(self) -> None:
        self.started = True

    def checkpoint_passed(self, checkpoint_id: int, pose: Pose) -> None:
        """一次通過通知；pose 是機器人當下真正的姿態。"""
        if not self.started or self.finished_at is not None:
            return  # J10：官方只記一行警告
        if checkpoint_id in self.judged_ids:
            return  # J7：官方只記一行 "already processed"
        self.judged_ids.append(checkpoint_id)
        if checkpoint_id not in [cp.id for cp in self.checkpoints.checkpoints]:
            return  # 不存在的 id：官方記成「判過、沒過」
        self._record(checkpoint_id, pose)

    def mission_finish(self, pose: Pose, at_sec: float) -> None:
        """完成回報（J9）。"""
        self.finished_at = at_sec
        goal_id = self.checkpoints.goal_id
        if goal_id in self.passed_ids:
            self.goal_reached = True
        else:
            self.goal_reached = self._record(goal_id, pose)

    def _record(self, checkpoint_id: int, pose: Pose) -> bool:
        result = judge(pose, self.checkpoints.by_id(checkpoint_id))
        if result.passed:
            self.passed_ids.append(checkpoint_id)
            self.passed_levels.append(result.level)
        return result.passed

    # ---- 結算 ----
    def remaining_at_finish(self) -> float:
        if self.finished_at is None:
            return 0.0
        return max(0.0, self.scoring.time_limit_sec - self.finished_at)

    def score(self, scoring: Optional[Scoring] = None) -> float:
        """假分數。不給 scoring 就用建立時的；給 `kibo_lab.scoring.WORLDS` 的某一個可看其他世界。"""
        rules = scoring or self.scoring
        late = self.finished_at is None or self.finished_at > rules.time_limit_sec
        all_passed = len(self.passed_ids) == len(self.checkpoints.checkpoints)
        return rules.total(
            self.passed_levels, self.goal_reached, self.remaining_at_finish(), all_passed, late
        )
