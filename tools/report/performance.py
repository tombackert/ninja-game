"""The benchmark suite's reference point and history, reduced for the report."""

from __future__ import annotations

import json
from typing import Any, Dict

BASELINE = "docs/benchmarks/baseline.json"
HISTORY = "docs/benchmarks/history.json"

PROBE_KEYS = ("frame_p50_ms", "frame_p99_ms", "startup_ms", "level_start_ms", "window", "frames_played")
SUITE_KEYS = ("frame.p50_ms", "frame.p99_ms", "level_start.p50_ms", "startup.to_menu_ms", "pause.frame_p50_ms")


def collect() -> Dict[str, Any]:
    with open(BASELINE) as f:
        base = json.load(f)
    with open(HISTORY) as f:
        history = json.load(f)
    from tools.bench.report import steps

    measured = [e for e in history["entries"] if e.get("suite") and not e.get("suite_quick")]
    jumps = [
        {
            "commit": after["commit"],
            "subject": after["subject"],
            "metric": m.label,
            "unit": m.unit,
            "before": before,
            "after": value,
            "verdict": verdict,
        }
        for after, m, before, value, verdict in steps(measured)
    ]
    entries = []
    for e in history["entries"]:
        probe = e.get("probe") or {}
        suite = e.get("suite") or {}
        entries.append(
            {
                "commit": e["commit"],
                "date": e["date"],
                "subject": e["subject"],
                "probe": {k: probe[k] for k in PROBE_KEYS if k in probe},
                "suite": {k: suite[k] for k in SUITE_KEYS if k in suite},
            }
        )
    return {
        "reference": {
            "commit": base["commit"],
            "subject": base["subject"],
            "measured": base["measured"],
            "sessions": base["sessions"],
            "machine": base["machine"],
            "env": base["env"],
            "metrics": base["metrics"],
            "spread": base["spread"],
            "campaign_frame_ms": base["detail"]["campaign_frame_ms"],
            "level_start_ms": base["detail"]["level_start_ms"],
            "respawn_ms": base["detail"]["respawn_ms"],
        },
        "history": entries,
        "steps": jumps,
    }
