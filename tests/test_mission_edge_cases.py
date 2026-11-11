"""run_mission 在不順利時的行為：沒有導航、晃動、拒絕、逾時、中途停止。

每個情境改掉假機器人的一個行為，其餘照舊：能用 `FakeRobotConfig` 表達的用設定
（到點偏移、還沒轉完、移動一律失敗），其餘用子類別覆寫 `Robot` 介面的一個方法。
"""

from conftest import PERFECT
from kibo.ctl_result import MOVE_INVALID, MOVE_TIMEOUT
from kibo.geometry import Pose, add
from kibo.mission import DEFAULT_MISSION, run_mission
from kibo_lab.fake_robot import CAMERA_FIX_MAX_M, FakeRobot

CAMERA_ON = DEFAULT_MISSION._replace(camera_fix_max_m=CAMERA_FIX_MAX_M)
SIDEWAYS_15CM = (0.0, 0.15, 0.0)  # 機體 +Y，與視線垂直：位置 Lv2、對中約 17° 也是 Lv2
LOST_35CM = (0.0, 0.0, 0.35)  # 超出最寬的位置餘裕


class BlindRobot(FakeRobot):
    def pose(self):
        return None


# 每次移動都停在目標旁邊固定的偏移處。
OFFSET = PERFECT._replace(arrival_offsets_m=(SIDEWAYS_15CM,))
LOST = PERFECT._replace(arrival_offsets_m=(LOST_35CM,))
# 第一次到某點會偏，再移動一次就準。
SECOND_TRY = PERFECT._replace(arrival_offsets_m=(SIDEWAYS_15CM, (0.0, 0.0, 0.0)))


class RejectingRobot(FakeRobot):
    notify_calls = 0

    def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
        self.notify_calls += 1
        return False


class StopAfterFirstRobot(FakeRobot):
    def notify_checkpoint(self, checkpoint_id, timeout_sec=float("inf")):
        accepted = super().notify_checkpoint(checkpoint_id, timeout_sec)
        self.stop = True
        return accepted


def test_without_navigation_nothing_is_reported(three_point_message):
    robot = BlindRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.finished
    assert robot.judge.judged_ids == []  # 一個通過通知都沒送
    assert all(v.judged_level == 0 and not v.notified for v in report.visits)
    # 但它確實盲飛到了 Goal，官方在完成回報時會用當下姿態判 Goal，所以 Goal 仍然算到。
    assert robot.judge.passed_ids == [12]


def test_unstable_but_inside_margin_is_still_reported_as_unstable(three_point_message):
    robot = FakeRobot(three_point_message, OFFSET)
    report = run_mission(robot, DEFAULT_MISSION)
    assert [v.stable for v in report.visits] == [False, False, False]
    assert [v.notified for v in report.visits] == [True, True, True]
    assert len(robot.judge.passed_levels) == 3 and all(lv < 3 for lv in robot.judge.passed_levels)


def test_outside_every_margin_is_not_reported(three_point_message):
    robot = FakeRobot(three_point_message, LOST)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.judge.passed_ids == []
    assert all(not v.notified for v in report.visits)


def test_when_there_is_no_time_to_spare_a_lower_level_counts_as_stable(three_point_message):
    # 時間剛好夠飛完：每一點都偏 15 cm（Lv2），沒有餘裕等或修正，直接以 Lv2 回報。
    dry_run = run_mission(FakeRobot(three_point_message, PERFECT), DEFAULT_MISSION)
    tight = DEFAULT_MISSION._replace(
        time_limit_sec=dry_run.elapsed_sec + 2.0,
        budget=DEFAULT_MISSION.budget._replace(margin_sec=0.0),
        finish_reserve_sec=0.0,  # 這裡只看餘裕的規則；收尾保留另外在 test_time_safety.py 測
        cancel_reserve_sec=0.0,
    )
    robot = FakeRobot(three_point_message, OFFSET)
    report = run_mission(robot, tight)
    assert report.visits[0].stable  # 不趕時間時 Lv2 不算穩定（上一個測試），沒餘裕時就算
    assert report.visits[0].judged_level == 2
    assert robot.move_calls == 3  # 沒有多花一次移動去修正


def test_one_refinement_move_recovers_level_3(three_point_message):
    robot = FakeRobot(three_point_message, SECOND_TRY)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.judge.passed_levels == [3, 3, 3]
    assert all(v.stable for v in report.visits)
    assert robot.move_calls == 6  # 每點：第一次偏掉，第二次修正


def test_rejected_notifications_are_retried_a_bounded_number_of_times(three_point_message):
    robot = RejectingRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.notify_calls == 3 * DEFAULT_MISSION.notify_attempts
    assert not report.goal_reached


def test_invalid_move_is_not_retried(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT._replace(move_always=MOVE_INVALID))
    run_mission(robot, DEFAULT_MISSION)
    assert robot.move_calls == 3  # 三個點各一次


def test_timed_out_move_is_retried_up_to_the_limit(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT._replace(move_always=MOVE_TIMEOUT))
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.move_calls <= 3 * DEFAULT_MISSION.max_move_attempts
    assert report.finished


def test_stop_in_the_middle_aborts_without_finish(three_point_message):
    robot = StopAfterFirstRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert report.aborted == "stop requested"
    assert len(robot.judge.passed_ids) == 1
    assert robot.judge.finished_at is None


# 每次絕對移動都偏 15 cm，但有相機；相對移動是準的。
DRIFTING_WITH_CAMERA = OFFSET._replace(camera=True)


def test_camera_correction_recovers_level_3_without_a_second_absolute_move(three_point_message):
    robot = FakeRobot(three_point_message, DRIFTING_WITH_CAMERA)
    report = run_mission(robot, CAMERA_ON)
    assert robot.judge.passed_levels == [3, 3, 3]
    assert all(v.stable for v in report.visits)
    assert robot.move_calls == 3  # 絕對移動每點一次
    assert robot.relative_calls == 3  # 修正每點一次


def test_large_but_allowed_drift_is_still_corrected_by_camera(three_point_message):
    # 位置超出餘裕，但相機修正量在上限內
    far = DRIFTING_WITH_CAMERA._replace(arrival_offsets_m=((0.0, 0.0, 0.29),))
    robot = FakeRobot(three_point_message, far)
    run_mission(robot, CAMERA_ON)
    assert robot.judge.passed_levels == [3, 3, 3]
    assert robot.relative_calls == 3


def test_implausible_camera_correction_falls_back_to_absolute_move(three_point_message):
    # 超過 camera_fix_max_m，應該不信相機、改用絕對移動
    huge = DRIFTING_WITH_CAMERA._replace(arrival_offsets_m=((0.0, 0.0, 0.5),))
    robot = FakeRobot(three_point_message, huge)
    run_mission(robot, CAMERA_ON)
    assert robot.relative_calls == 0
    assert robot.move_calls == 6


def test_camera_fix_is_off_by_default_even_when_the_robot_has_a_camera(three_point_message):
    robot = FakeRobot(three_point_message, DRIFTING_WITH_CAMERA)
    run_mission(robot, DEFAULT_MISSION)
    assert robot.relative_calls == 0


class HistoryRobot(FakeRobot):
    """移動回來時，手上已經有最近一段導航紀錄（真機器人在 action 的尾段一直在收）。"""

    history_offset = (0.0, 0.0, 0.0)  # 紀錄裡最舊那筆相對現在位置的偏移
    recent_calls = 0

    def recent_poses(self, seconds):
        self.recent_calls += 1
        here = self.pose()
        assert here is not None
        stamps = [self.now() - seconds + 0.1 * k for k in range(int(seconds / 0.1) + 1)]
        poses = [Pose(here.position, here.orientation, stamp=s) for s in stamps]
        oldest = add(here.position, self.history_offset)
        poses[0] = Pose(oldest, here.orientation, stamp=stamps[0])
        return poses


class DriftedHistoryRobot(HistoryRobot):
    history_offset = LOST_35CM  # 一秒前還在容差外：剛到，還沒穩


def _seconds_between_arrival_and_report(robot, checkpoint_id):
    import re

    left = {}
    for line in robot.logs:
        m = re.match(r"\[t=([\d.]+) ", line)
        if m and "move to #%d attempt 1: success" % checkpoint_id in line:
            left["moved"] = float(m.group(1))
        if m and "checkpoint #%d accepted" % checkpoint_id in line:
            left["accepted"] = float(m.group(1))
    return left["accepted"] - left["moved"]


def test_a_second_already_spent_in_tolerance_before_the_move_returned_counts(three_point_message):
    # 尾段紀錄顯示已經在 Lv3 內待滿 1 秒：不用再等一秒，直接回報（只剩通知本身的 0.3 秒）。
    robot = HistoryRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert all(v.stable and v.notified and v.judged_level == 3 for v in report.visits)
    assert _seconds_between_arrival_and_report(robot, 1) < 0.5


def test_without_history_the_robot_still_waits_its_own_second(three_point_message):
    robot = FakeRobot(three_point_message, PERFECT)
    run_mission(robot, DEFAULT_MISSION)
    assert _seconds_between_arrival_and_report(robot, 1) >= 1.0


def test_history_that_was_outside_tolerance_a_second_ago_does_not_count(three_point_message):
    robot = DriftedHistoryRobot(three_point_message, PERFECT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert robot.recent_calls > 0
    assert all(v.stable and v.notified for v in report.visits)
    assert _seconds_between_arrival_and_report(robot, 1) >= 1.0


# 移動回報成功後的 2 秒內，機體還差 15° 滾轉沒轉完（Lv2），之後才到位。
# 真的控制器就是這樣：姿態進到 0.5 rad 以內就回報成功，不等轉完。
STILL_TURNING = PERFECT._replace(residual_roll_deg=15.0, residual_roll_sec=2.0)
# 回報成功後 2 秒內滾轉還差 9°：算 Lv3（上限 10°），但只差 1°。
NEAR_THE_LIMIT = STILL_TURNING._replace(residual_roll_deg=9.0)
FOR_EVER = 1000.0  # 一直停在那個角度，不會再變好


def _realistic_message():
    # 共用的三點場景裡，Goal 剛好正對 -X、姿態是整整 180°，官方的滾轉量測在那裡退化成 0
    # （見 docs/kibo/simulator-internals.md 的 J5）。這兩個測試要看滾轉，所以用產生器的場景。
    from kibo_lab.scenarios import random_checkpoints_message

    return random_checkpoints_message(3, seed=5)


def test_with_time_to_spare_at_the_goal_it_waits_for_level_3():
    # 2026-11-10 本機 hard 場：到 Goal 時還剩 26 秒，但「剩不到 40 秒就趕」讓它在機體還沒轉完時
    # 就回報，官方只給 Lv1。到 Goal 之後已經沒有別的事要做，剩下的時間都可以拿來等。
    message = _realistic_message()
    dry_run = run_mission(FakeRobot(message, PERFECT), DEFAULT_MISSION)
    roomy = DEFAULT_MISSION._replace(time_limit_sec=dry_run.elapsed_sec + 30.0)
    robot = FakeRobot(message, STILL_TURNING)
    report = run_mission(robot, roomy)
    assert report.visits[-1].checkpoint_id == 12
    assert [v.judged_level for v in report.visits] == [3, 3, 3]
    assert robot.judge.passed_levels == [3, 3, 3]
    assert report.elapsed_sec <= roomy.time_limit_sec


def test_when_the_rest_of_the_route_needs_the_time_it_settles_for_less():
    # 時間只夠剛好飛完：每一點都沒有多餘的秒數可以等，還在轉（Lv2）就回報。
    message = _realistic_message()
    dry_run = run_mission(FakeRobot(message, PERFECT), DEFAULT_MISSION)
    tight = DEFAULT_MISSION._replace(
        time_limit_sec=dry_run.elapsed_sec + 2.0,
        budget=DEFAULT_MISSION.budget._replace(margin_sec=0.0),
        finish_reserve_sec=0.0,  # 這裡只看餘裕的規則；收尾保留另外在 test_time_safety.py 測
        cancel_reserve_sec=0.0,
    )
    robot = FakeRobot(message, STILL_TURNING)
    report = run_mission(robot, tight)
    assert [v.judged_level for v in report.visits] == [2, 2, 2]
    assert report.elapsed_sec <= tight.time_limit_sec


def test_with_time_to_spare_it_does_not_report_right_at_the_edge_of_level_3():
    # 官方用的姿態最多舊 0.2 秒，Goal 點的滾轉讀數又會晃；貼著 10° 回報很容易被判成 Lv2。
    # 有餘裕就等讀數降到上限的八成以內。
    message = _realistic_message()
    robot = FakeRobot(message, NEAR_THE_LIMIT)
    report = run_mission(robot, DEFAULT_MISSION)
    assert [v.judged_level for v in report.visits] == [3, 3, 3]
    reported = [line for line in robot.logs if line.split("] ", 1)[-1].startswith("at #")]
    assert all("roll=0.0" in line for line in reported), reported


def test_a_reading_that_stays_near_the_edge_is_reported_after_a_few_seconds():
    # 等不到更好的讀數也不能一直等：幾秒後照 Lv3 回報。
    message = _realistic_message()
    robot = FakeRobot(message, NEAR_THE_LIMIT._replace(residual_roll_sec=FOR_EVER))
    report = run_mission(robot, DEFAULT_MISSION)
    assert [v.judged_level for v in report.visits] == [3, 3, 3]
    assert all(v.stable and v.notified for v in report.visits)
    assert robot.move_calls == 3  # 沒有為此多移動一次


def test_the_level_3_buffer_does_not_apply_when_only_level_2_is_wanted():
    # 只求 Lv2 的設定：停在 15°（Lv2）就該馬上算穩定，不該被「Lv3 上限的八成」擋住再等 3 秒。
    message = _realistic_message()
    robot = FakeRobot(message, STILL_TURNING._replace(residual_roll_sec=FOR_EVER))
    report = run_mission(robot, DEFAULT_MISSION._replace(target_level=2))
    assert [v.judged_level for v in report.visits] == [2, 2, 2]
    assert all(v.stable for v in report.visits)
    assert _seconds_between_arrival_and_report(robot, 12) < 2.0


def test_a_fake_robot_that_stopped_before_the_move_returned_is_reported_at_once(
    three_point_message,
):
    # 模擬器實測：action 回報成功前，機器人通常已經在目標上停了 1.5 秒左右。
    settled_early = PERFECT._replace(settled_before_return_sec=1.5)
    robot = FakeRobot(three_point_message, settled_early)
    report = run_mission(robot, DEFAULT_MISSION)
    assert all(v.stable and v.judged_level == 3 for v in report.visits)
    assert _seconds_between_arrival_and_report(robot, 1) < 0.5
    # 停得不夠久（0.5 秒）就還是要自己等滿
    barely = FakeRobot(three_point_message, PERFECT._replace(settled_before_return_sec=0.5))
    run_mission(barely, DEFAULT_MISSION)
    assert _seconds_between_arrival_and_report(barely, 1) >= 1.0
