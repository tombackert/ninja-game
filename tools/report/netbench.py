"""Netbench over time: every recorded reference point, oldest first.

docs/benchmarks/netbench-baseline.json is overwritten by each --save, so the
progress of the netcode lives in the git history of that one file. This
reads every version back, keeps the median and the spread between runs of
the metrics the report shows, and can add a fresh run as the current state.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List, Optional

BASELINE = "docs/benchmarks/netbench-baseline.json"

KEYS = (
    "friend.corrections_per_min",
    "friend.mispredictions_per_min",
    "friend.view_age_p95_ms",
    "friend.freezes_per_min",
    "friend.freeze_max_ms",
    "friend.rtt_p50_ms",
    "friend.rtt_p95_ms",
    "friend.s2c_loss_pct",
    "server.friend_c2s_loss_pct",
    "server.friend_s2c_kbps",
    "server.max_packet_bytes",
    "server.tick_ms_p95",
    "host.corrections_per_min",
    "host.freezes_per_min",
    "host.view_age_p95_ms",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _reduce(point: Dict[str, Any]) -> Dict[str, Any]:
    """One reference point: per profile, median and range over the runs of each metric."""
    commit = point["commit"]
    profiles = {}
    for name, profile in point["profiles"].items():
        metrics = {}
        for key in KEYS:
            values = [run[key] for run in profile["runs"] if key in run]
            if values:
                metrics[key] = {
                    "median": profile["median"].get(key),
                    "min": min(values),
                    "max": max(values),
                    "runs": values,
                }
        profiles[name] = metrics
    return {
        "commit": commit,
        "date": point.get("date"),
        "subject": _git("log", "-1", "--format=%s", commit).strip(),
        "duration_s": point.get("duration"),
        "level": point.get("level"),
        "profiles": profiles,
    }


def collect(run_path: Optional[str] = None) -> Dict[str, Any]:
    versions = _git("log", "--reverse", "--format=%h", "--", BASELINE).split()
    points: List[Dict[str, Any]] = [_reduce(json.loads(_git("show", f"{v}:{BASELINE}"))) for v in versions]
    current = None
    if run_path:
        with open(run_path) as f:
            current = _reduce(json.load(f))
    return {"points": points, "current": current}
