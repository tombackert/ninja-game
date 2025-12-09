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
