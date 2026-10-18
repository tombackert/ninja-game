from scripts.perf_hud import PerformanceHUD


def test_performance_hud_ema_smoothing():
    hud = PerformanceHUD(enabled=True, alpha=0.1)
    hud.begin_frame()
    # simulate first work segment 10ms
    hud._t_work_start -= 0.010  # monkeypatch start time
    hud.end_work_segment()
    first = hud.last_sample
    assert first is not None
    assert 9.5 <= first.work_ms <= 10.5  # coarse bounds
    assert first.avg_work_ms == first.work_ms  # first sample seeds EMA

    # second frame with higher work cost 30ms
    hud.begin_frame()
    hud._t_work_start -= 0.030
    hud.end_work_segment()
    second = hud.last_sample
    assert second is not None
    # EMA: 0.1 * 30 + 0.9 * 10 = 12.0
    assert 11.5 <= (second.avg_work_ms or 0) <= 12.5


def test_performance_hud_metrics_collection():
    hud = PerformanceHUD(enabled=True)
    hud.begin_frame()
    hud.end_work_segment()
    hud.end_frame()
    sample = hud.last_sample
    assert sample is not None
    # Check fields exist (may be None if dependencies missing in test env)
    assert hasattr(sample, "memory_rss")
    assert hasattr(sample, "asset_count")


def test_performance_hud_tracks_frame_intervals_and_hitches(monkeypatch):
    import scripts.perf_hud as perf_hud

    now = [100.0]
    monkeypatch.setattr(perf_hud.time, "perf_counter", lambda: now[0])
    hud = PerformanceHUD(enabled=True)
    for step in (0.0, 0.0167, 0.0167, 0.040, 0.0167):  # one 40 ms hitch
        now[0] += step
        hud.begin_frame()
        hud.end_work_segment()
        hud.end_frame()
    sample = hud.last_sample
    assert sample is not None
    assert abs((sample.interval_ms or 0) - 16.7) < 0.01
    assert abs((sample.worst_interval_ms or 0) - 40.0) < 0.01
    assert sample.hitches == 1


def test_memory_is_the_current_rss_not_the_peak():
    import mmap

    import pytest

    from scripts.perf_hud import current_rss_mb

    before = current_rss_mb()
    if before is None:
        pytest.skip("no current RSS on this platform")
    block = mmap.mmap(-1, 64 << 20)
    for i in range(0, len(block), mmap.PAGESIZE):
        block[i] = 1  # touch every page so it becomes resident
    during = current_rss_mb()
    block.close()
    after = current_rss_mb()
    assert during - before > 48
    assert during - after > 48  # the peak (ru_maxrss) would not go down
