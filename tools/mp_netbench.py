"""Multiplayer netcode benchmark (real processes, emulated networks).

Plays the online mode the way two friends do: the dedicated server, the
host's game client on loopback, and the friend's game client behind
tools/mp_netem.py with a network profile. Both clients are the real game
(app.py -> MultiplayerGameState with the "runner" autopilot, SDL dummy
drivers), so prediction, reconciliation and interpolation run as in a
real session, and both quit the way a player closes the window.

Each run reduces the session logs (docs/multiplayer.md#session-logs) to
the core metrics of docs/online-benchmark-brainstorm.md, section 9.
Several runs per profile (different netem seeds) are reduced to their
median, since single runs move with timing noise.

The profiles are starting values until a real session calibrates them;
mp_netem's jitter is uniform and independent per packet, so it reorders
more than a real line with the same jitter would.

Like the single-player suite (python -m tools.bench), results are shown
next to a reference point, docs/benchmarks/netbench-baseline.json; --save
records a new one.

Usage:
    python tools/mp_netbench.py                         # all profiles, 3 runs each (~6 min)
    python tools/mp_netbench.py --quick                 # 1 short run per profile (~1.5 min)
    python tools/mp_netbench.py --profiles wlan --runs 5
    python tools/mp_netbench.py --save                  # record a new reference point
    python tools/mp_netbench.py --out try.json          # save the results elsewhere
    python tools/mp_netbench.py --compare try.json      # compare with those instead
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(REPO, "docs", "benchmarks", "netbench-baseline.json")

# name -> (description, mp_netem arguments; None = friend connects directly)
PROFILES: Dict[str, tuple[str, Optional[List[str]]]] = {
    "loopback": ("both on this machine", None),
    "internet": (
        "wired lines within Germany",
        ["--delay-ms", "12", "--jitter-ms", "4", "--loss", "0.005"],
    ),
    "wlan": (
        "friend on Wi-Fi at home",
        ["--delay-ms", "15", "--jitter-ms", "10", "--loss", "0.01", "--doze-ms", "40", "--doze-period-ms", "500"],
    ),
    "bad_wlan": (
        "weak Wi-Fi, power-save bursts",
        ["--delay-ms", "15", "--jitter-ms", "25", "--loss", "0.02", "--doze-ms", "80", "--doze-period-ms", "300"],
    ),
}

# The friend's first seconds (joining, interpolation delay settling) are not scored
WARMUP_S = 3.0
# Player data that must never change during a benchmark
PLAYER_FILES = ("data/settings.json", "data/collectables.json", "data/best_times.json")

# Rows of the result table: (key, label, decimals)
ROWS: List[tuple[str, str, int]] = [
    ("friend.corrections_per_min", "friend: own ninja snaps / min", 1),
    ("host.corrections_per_min", "host: own ninja snaps / min", 1),
    ("friend.freezes_per_min", "friend sees host freeze / min", 1),
    ("host.freezes_per_min", "host sees friend freeze / min", 1),
    ("friend.freeze_max_ms", "longest freeze seen by friend (ms)", 0),
    ("friend.view_age_p95_ms", "friend: view age p95 (ms)", 0),
    ("host.view_age_p95_ms", "host: view age p95 (ms)", 0),
    ("server.friend_starved_pct", "ticks w/o new friend input (%)", 1),
    ("server.friend_burst_pct", "ticks with 2+ friend inputs (%)", 1),
    ("server.host_starved_pct", "ticks w/o new host input (%)", 1),
    ("server.friend_no_step_pct", "ticks friend's ninja made no step (%)", 1),
    ("server.friend_multi_step_pct", "ticks friend's ninja made 2+ steps (%)", 1),
    ("friend.mispredictions_per_min", "friend: mispredictions / min", 0),
    ("friend.correction_max_px", "friend: largest snap (px)", 1),
    ("friend.rtt_p50_ms", "friend: RTT p50 (ms)", 1),
    ("friend.rtt_p95_ms", "friend: RTT p95 (ms)", 1),
    ("friend.stalls_per_min", "friend: snapshot stalls / min", 1),
    ("friend.s2c_loss_pct", "loss server -> friend (%)", 2),
    ("server.friend_c2s_loss_pct", "loss friend -> server (%)", 2),
    ("server.friend_s2c_kbps", "bandwidth to friend (kbit/s)", 0),
    ("server.max_packet_bytes", "largest packet (bytes)", 0),
    ("server.tick_ms_p95", "server tick p95 (ms)", 2),
    ("friend.fps_p50", "friend: fps", 0),
]


# ---------------------------------------------------------------------------
# Client mode: one real game client that quits after --duration seconds
# ---------------------------------------------------------------------------


def client_main(args: argparse.Namespace) -> int:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["NINJA_MP_AUTOPILOT"] = args.pattern
    os.environ["NINJA_MP_METRICS"] = args.log
    os.chdir(REPO)
    sys.path.insert(0, REPO)
    import pygame

    import app

    sys.argv = ["app.py", "--multiplayer", "--host", "127.0.0.1", "--port", str(args.port), "--name", args.name]
    deadline = time.time() + args.duration
    real_get = pygame.event.get

    def get_events(*a: Any, **kw: Any) -> list:
        events = real_get(*a, **kw)
        if time.time() >= deadline:
            events.append(pygame.event.Event(pygame.QUIT))  # like closing the window
        return events

    pygame.event.get = get_events
    app.main()
    return 0


# ---------------------------------------------------------------------------
# One benchmark run
# ---------------------------------------------------------------------------


def run_once(profile: str, seed: int, duration: float, port: int, level: int, workdir: str) -> Dict[str, Any]:
    """Server + host client + friend client (through netem); returns the reduced metrics."""
    _, netem_args = PROFILES[profile]
    server_log = os.path.join(workdir, "server.jsonl")
    host_log = os.path.join(workdir, "host.jsonl")
    friend_log = os.path.join(workdir, "friend.jsonl")
    out = open(os.path.join(workdir, "processes.log"), "w")
    procs: List[subprocess.Popen] = []

    def spawn(cmd: List[str]) -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, *cmd], cwd=REPO, stdout=out, stderr=subprocess.STDOUT)
        procs.append(p)
        return p

    friend_port = port
    try:
        spawn(["server.py", "--port", str(port), "--level", str(level), "--metrics-file", server_log])
        time.sleep(1.5)
        if netem_args is not None:
            friend_port = port + 1
            spawn(
                [
                    "tools/mp_netem.py",
                    "--listen-port",
                    str(friend_port),
                    "--server-port",
                    str(port),
                    *netem_args,
                    "--seed",
                    str(seed),
                ]
            )
            time.sleep(0.5)
        me = os.path.abspath(__file__)
        host = spawn(
            [me, "--client", "--port", str(port), "--name", "Host", "--duration", str(duration + 2), "--log", host_log]
        )
        time.sleep(1.0)  # the host is in the level first, as in a real session
        friend = spawn(
            [
                me,
                "--client",
                "--port",
                str(friend_port),
                "--name",
                "Friend",
                "--duration",
                str(duration),
                "--log",
                friend_log,
            ]
        )
        friend.wait(timeout=duration + 60)
        host.wait(timeout=duration + 60)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        out.close()

    return reduce_run(_load(server_log), _load(host_log), _load(friend_log))


def _load(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Reducing session logs to the core metrics
# ---------------------------------------------------------------------------


def _samples(records: List[Dict[str, Any]], start: float, end: float) -> List[Dict[str, Any]]:
    return [r for r in records if r.get("type") == "sample" and start <= r["t"] <= end]


def _median(values: List[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _client_metrics(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    secs = len(samples)
    if not secs:
        return {}

    def per_min(key: str) -> float:
        return 60.0 * sum(s.get(key, 0) for s in samples) / secs

    def med(key: str) -> Optional[float]:
        return _median([s[key] for s in samples if s.get(key) is not None])

    def top(key: str) -> float:
        return max((s[key] for s in samples if s.get(key) is not None), default=0.0)

    lost = sum(s["link_lost"] for s in samples)
    expected = sum(s["link_rx_packets"] - s["link_duplicates"] - s["link_late"] + s["link_lost"] for s in samples)
    return {
        "seconds": secs,
        "fps_p50": med("fps"),
        "rtt_p50_ms": med("rtt_ms_p50"),
        "rtt_p95_ms": med("rtt_ms_p95"),
        "corrections_per_min": per_min("corrections"),
        "mispredictions_per_min": per_min("mispredictions"),
        "correction_max_px": top("reconcile_px_max"),
        "view_age_p95_ms": med("view_age_ms_p95"),
        "freezes_per_min": per_min("freezes"),
        "freeze_max_ms": top("freeze_ms_max"),
        "stalls_per_min": per_min("stalls"),
        "s2c_loss_pct": 100.0 * lost / expected if expected else 0.0,
    }


def _server_metrics(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not samples:
        return {}
    out: Dict[str, Any] = {"tick_ms_p95": _median([s["tick_ms_p95"] for s in samples if "tick_ms_p95" in s])}
    max_packet = 0
    for who in ("Host", "Friend"):
        peers = [p for s in samples for p in s.get("peers", {}).values() if p.get("name") == who]
        if not peers:
            continue
        ticks = sum(p["ticks"]["ticks"] for p in peers)
        link = [p["link"] for p in peers]
        lost = sum(x["lost"] for x in link)
        expected = sum(x["rx_packets"] - x["duplicates"] - x["late"] + x["lost"] for x in link)
        prefix = who.lower()
        out[f"{prefix}_starved_pct"] = 100.0 * sum(p["ticks"]["starved"] for p in peers) / ticks if ticks else 0.0
        out[f"{prefix}_burst_pct"] = 100.0 * sum(p["ticks"]["burst"] for p in peers) / ticks if ticks else 0.0
        for key in ("no_step", "multi_step"):
            out[f"{prefix}_{key}_pct"] = 100.0 * sum(p["ticks"].get(key, 0) for p in peers) / ticks if ticks else 0.0
        out[f"{prefix}_c2s_loss_pct"] = 100.0 * lost / expected if expected else 0.0
        out[f"{prefix}_s2c_kbps"] = sum(x["tx_bytes"] for x in link) * 8 / 1000.0 / len(peers)
        max_packet = max(max_packet, max(x["tx_max_bytes"] for x in link))
    out["max_packet_bytes"] = max_packet
    return out


def reduce_run(
    server: List[Dict[str, Any]], host: List[Dict[str, Any]], friend: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Flat metrics of one run, scored over the time both clients played."""
    friend_t = [r["t"] for r in friend if r.get("type") == "sample"]
    if not friend_t:
        return {"error": "friend wrote no samples"}
    start, end = friend_t[0] + WARMUP_S, friend_t[-1]
    result: Dict[str, Any] = {}
    for prefix, metrics in (
        ("friend", _client_metrics(_samples(friend, start, end))),
        ("host", _client_metrics(_samples(host, start, end))),
        ("server", _server_metrics(_samples(server, start, end))),
    ):
        for key, value in metrics.items():
            result[f"{prefix}.{key}"] = value
    return result


def median_of_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    keys = sorted({k for r in runs for k in r if k != "error"})
    return {k: _median([r[k] for r in runs if r.get(k) is not None]) for k in keys}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _fmt(value: Optional[float], decimals: int) -> str:
    return "-" if value is None else f"{value:.{decimals}f}"


def print_table(results: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> None:
    profiles = list(results["profiles"])
    width = 18 if baseline else 10
    print()
    print(f"{'':38}" + "".join(f"{p:>{width}}" for p in profiles))
    for key, label, decimals in ROWS:
        cells = []
        for p in profiles:
            new = results["profiles"][p]["median"].get(key)
            if baseline and p in baseline.get("profiles", {}):
                old = baseline["profiles"][p]["median"].get(key)
                cells.append(f"{_fmt(old, decimals)} -> {_fmt(new, decimals)}")
            else:
                cells.append(_fmt(new, decimals))
        print(f"{label:38}" + "".join(f"{c:>{width}}" for c in cells))
    runs = {p: len(results["profiles"][p]["runs"]) for p in profiles}
    print(
        f"\nmedian of {runs} runs, {results['duration']} s each, level {results['level']}, commit {results['commit']}"
    )
    if baseline:
        print(f"compared with commit {baseline.get('commit')} ({baseline.get('date')})")


def _git_commit() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "-uno"], cwd=REPO, capture_output=True, text=True
        ).stdout
        return rev.strip() + ("+dirty" if dirty.strip() else "")
    except OSError:
        return "?"


def _player_file_times() -> Dict[str, float]:
    return {f: os.path.getmtime(os.path.join(REPO, f)) for f in PLAYER_FILES if os.path.exists(os.path.join(REPO, f))}


def bench_main(args: argparse.Namespace) -> int:
    profiles = args.profiles.split(",") if args.profiles else list(PROFILES)
    unknown = [p for p in profiles if p not in PROFILES]
    if unknown:
        print(f"unknown profile(s): {', '.join(unknown)}; known: {', '.join(PROFILES)}")
        return 2
    runs = 1 if args.quick and args.runs is None else (args.runs or 3)
    duration = args.duration or (12.0 if args.quick else 20.0)
    baseline = None
    compare = args.compare or (BASELINE if os.path.exists(BASELINE) and not args.save else None)
    if compare:
        with open(compare) as f:
            baseline = json.load(f)

    files_before = _player_file_times()
    tmp = tempfile.mkdtemp(prefix="mp_netbench_")
    results: Dict[str, Any] = {
        "commit": _git_commit(),
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "duration": duration,
        "level": args.level,
        "profiles": {},
    }
    print(f"[netbench] {len(profiles)} profiles x {runs} runs x {duration:.0f} s, logs in {tmp}")
    port = args.port
    for name in profiles:
        description, netem_args = PROFILES[name]
        print(f"[netbench] {name}: {description}" + (f" ({' '.join(netem_args)})" if netem_args else ""))
        run_results = []
        for i in range(runs):
            workdir = os.path.join(tmp, f"{name}-{i}")
            os.makedirs(workdir)
            result = run_once(name, args.seed + i, duration, port, args.level, workdir)
            port += 10
            run_results.append(result)
            if "error" in result:
                print(f"[netbench]   run {i + 1}: FAILED ({result['error']}), see {workdir}")
            else:
                print(
                    f"[netbench]   run {i + 1}: {result.get('friend.corrections_per_min', 0):.1f} snaps/min, "
                    f"RTT p50 {_fmt(result.get('friend.rtt_p50_ms'), 1)} ms, "
                    f"starved {_fmt(result.get('server.friend_starved_pct'), 1)} %"
                )
        good = [r for r in run_results if "error" not in r]
        results["profiles"][name] = {"median": median_of_runs(good), "runs": run_results}

    print_table(results, baseline)
    for path in [args.out] + ([BASELINE] if args.save else []):
        if path:
            with open(path, "w") as f:
                json.dump(results, f, indent=1)
                f.write("\n")
            print(f"saved to {os.path.relpath(path, REPO)}")

    changed = [f for f, t in _player_file_times().items() if files_before.get(f) != t]
    if changed:
        print(f"[netbench] WARNING: player data changed during the benchmark: {', '.join(changed)}")
        return 1
    failed = sum("error" in r for p in results["profiles"].values() for r in p["runs"])
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Multiplayer netcode benchmark")
    parser.add_argument("--profiles", help=f"comma-separated, default all: {', '.join(PROFILES)}")
    parser.add_argument("--runs", type=int, default=None, help="runs per profile (default 3, --quick 1)")
    parser.add_argument("--duration", type=float, default=None, help="seconds per run (default 20, --quick 12)")
    parser.add_argument("--quick", action="store_true", help="one short run per profile")
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7, help="netem seed of the first run")
    parser.add_argument("--port", type=int, default=25700, help="first server port")
    parser.add_argument("--save", action="store_true", help="record the results as the new reference point")
    parser.add_argument("--out", help="also write the results to this JSON file")
    parser.add_argument("--compare", help="compare with this results file instead of the reference point")
    # Internal: run one game client
    parser.add_argument("--client", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--name", default="Player", help=argparse.SUPPRESS)
    parser.add_argument("--pattern", default="runner", help=argparse.SUPPRESS)
    parser.add_argument("--log", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.client:
        args.duration = args.duration or 20.0
        return client_main(args)
    return bench_main(args)


if __name__ == "__main__":
    sys.exit(main())
