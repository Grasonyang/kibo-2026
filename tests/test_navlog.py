"""導航紀錄：節點把 200 Hz 的導航餵進來，任務邏輯問「現在在哪」與「最近幾秒在哪」。"""

from kibo.geometry import IDENTITY_QUAT, Pose
from kibo.navlog import NavLog


def pose(stamp, x=0.0):
    return Pose((x, 0.0, 0.0), IDENTITY_QUAT, stamp=stamp)


def stamps(poses):
    return [p.stamp for p in poses if p.stamp is not None]


def test_latest_is_the_newest_sample_even_between_kept_ones():
    log = NavLog(step_sec=0.05)
    log.add(pose(10.000, x=1.0))
    log.add(pose(10.005, x=2.0))  # 離上一筆太近，不進紀錄，但仍是「最新」
    latest = log.latest(now=10.01)
    assert latest is not None and latest.position[0] == 2.0


def test_no_data_or_stale_data_means_no_pose():
    log = NavLog(fresh_sec=1.0)
    assert log.latest(now=5.0) is None
    log.add(pose(10.0))
    assert log.latest(now=10.9) is not None
    assert log.latest(now=11.1) is None  # 比 1 秒舊：當作不知道自己在哪


def test_history_is_thinned_to_the_step():
    # 200 Hz 餵 1 秒，紀錄只留大約 20 Hz。2026-11-10 沒降頻時 64 筆只跨 0.33 秒，尾段自判因此失效。
    log = NavLog(step_sec=0.05, capacity=64)
    for i in range(201):
        log.add(pose(100.0 + i * 0.005))
    recent = stamps(log.recent(now=101.0, seconds=1.0))
    assert 19 <= len(recent) <= 21
    assert recent[-1] - recent[0] >= 0.9
    assert min(b - a for a, b in zip(recent, recent[1:])) >= 0.05 - 1e-9


def test_recent_returns_only_the_asked_window_oldest_first():
    log = NavLog(step_sec=0.05)
    for i in range(100):
        log.add(pose(i * 0.1))  # 0.0 到 9.9
    recent = stamps(log.recent(now=9.9, seconds=0.5))
    assert [round(s, 1) for s in recent] == [9.4, 9.5, 9.6, 9.7, 9.8, 9.9]


def test_capacity_drops_the_oldest():
    log = NavLog(step_sec=0.05, capacity=10)
    for i in range(50):
        log.add(pose(i * 0.1))
    recent = stamps(log.recent(now=4.9, seconds=100.0))
    assert len(recent) == 10 and round(recent[0], 1) == 4.0


def test_a_clock_that_jumps_backwards_starts_a_fresh_history():
    # 模擬時鐘重設：舊的紀錄比「現在」還新，留著會讓人以為已經穩定很久。
    log = NavLog(step_sec=0.05, fresh_sec=1.0)
    log.add(pose(100.0))
    log.add(pose(100.1))
    log.add(pose(5.0))
    assert stamps(log.recent(now=5.0, seconds=10.0)) == [5.0]


def test_a_sample_that_arrives_slightly_late_is_dropped_not_treated_as_a_clock_reset():
    # 晚到 40 ms 的一筆不能把整本紀錄清掉（那會讓尾段湊不滿 1 秒），也不能蓋掉比較新的那筆。
    log = NavLog(step_sec=0.05, fresh_sec=1.0)
    for i in range(21):
        log.add(pose(10.0 + 0.05 * i, x=float(i)))
    log.add(pose(10.96, x=99.0))
    assert len(log.recent(now=11.0, seconds=10.0)) == 21
    latest = log.latest(now=11.0)
    assert latest is not None and latest.position[0] == 20.0


def test_samples_exactly_one_step_apart_are_all_kept():
    # 0.05 的倍數用浮點加起來會差一點點；不能因此每隔一筆丟一筆。
    log = NavLog(step_sec=0.05)
    for i in range(21):
        log.add(pose(51.5 - 0.05 * (20 - i)))
    assert len(log.recent(now=51.5, seconds=10.0)) == 21


def test_samples_without_a_stamp_are_ignored():
    log = NavLog()
    log.add(Pose((0.0, 0.0, 0.0), IDENTITY_QUAT))
    assert log.latest(now=0.0) is None and log.count == 0


def test_rate_is_measured_from_the_stamps():
    log = NavLog()
    for i in range(201):
        log.add(pose(50.0 + i * 0.005))
    assert log.count == 201
    assert abs(log.rate_hz() - 200.0) < 1.0
