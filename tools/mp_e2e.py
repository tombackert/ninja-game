"""Multiplayer end-to-end test orchestrator (real processes).

Spawns the dedicated server (server.py) and two headless bot clients
(tools/mp_e2e_bot.py) as separate OS processes, lets them play a
scripted session, then verifies correctness and performance:

- Both clients connect and see each other (2 players in snapshots)
- Cross-client consistency: for every tick both clients observed, the
  authoritative state digests must be identical (catches delta-chain
  corruption)
- Movement actually happens (inputs are applied server-side)
- Enemies are simulated and synced
- Server holds ~60 ticks/s; clients hold ~60 fps; snapshot rate ~20/s
- RTT stays low on loopback, no packets are lost in either direction,
  and the per-client netcode reports reach the server's session log

Usage:
    python tools/mp_e2e.py [--duration 10] [--port 21777] [--keep-logs]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(duration: float, port: int, keep_logs: bool) -> int:
    tmp = tempfile.mkdtemp(prefix="mp_e2e_")
    server_metrics = os.path.join(tmp, "server_metrics.jsonl")
    report_a = os.path.join(tmp, "botA.json")
    report_b = os.path.join(tmp, "botB.json")
    server_log = open(os.path.join(tmp, "server.log"), "w")

    print(f"[e2e] logs in {tmp}")

    server = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port), "--level", "0", "--metrics-file", server_metrics],
        cwd=REPO,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    try:
        time.sleep(2.0)  # server boot
        if server.poll() is not None:
            print("[e2e] FAIL: server exited early")
            return 1

        bots = []
        for name, pattern, report in (
            ("BotA", "runner", report_a),
            ("BotB", "shooter", report_b),
        ):
            bots.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "tools/mp_e2e_bot.py",
                        "--port",
                        str(port),
                        "--name",
                        name,
                        "--pattern",
                        pattern,
                        "--duration",
                        str(duration),
                        "--report",
                        report,
                    ],
                    cwd=REPO,
                )
            )

        for b in bots:
            b.wait(timeout=duration + 30)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()

    # ---------------- Analysis ----------------
    with open(report_a) as f:
        a = json.load(f)
    with open(report_b) as f:
        b = json.load(f)
    server_records = []
    if os.path.exists(server_metrics):
        with open(server_metrics) as f:
            server_records = [json.loads(line) for line in f if line.strip()]
    server_samples = [r for r in server_records if r.get("type") == "sample"]

    failures: list[str] = []

    def check(cond: bool, label: str, detail: str = "") -> None:
        status = "ok" if cond else "FAIL"
        print(f"[e2e] {status:4} {label} {detail}")
        if not cond:
            failures.append(label)

    # Connectivity
    check(a["connected"] and b["connected"], "both clients connected", f"(ids {a['player_id']}, {b['player_id']})")

    # Both see two players in their final snapshots
    def last_snap(r):
        return r["snapshots"][-1] if r["snapshots"] else {"players": {}, "enemies": {}}

    check(len(last_snap(a)["players"]) == 2, "client A sees 2 players")
    check(len(last_snap(b)["players"]) == 2, "client B sees 2 players")

    # Cross-client consistency at common ticks (delta-chain integrity)
    digests_a = {s["tick"]: s for s in a["snapshots"]}
    digests_b = {s["tick"]: s for s in b["snapshots"]}
    common = sorted(set(digests_a) & set(digests_b))
    mismatches = [t for t in common if digests_a[t] != digests_b[t]]
    check(len(common) >= 20, "enough common snapshot ticks", f"({len(common)})")
    check(
        not mismatches,
        "cross-client state identical at common ticks",
        f"({len(mismatches)} mismatches of {len(common)})" if mismatches else f"({len(common)} ticks)",
    )

    # Movement: BotA (runner) must move horizontally over the session
    pid_a = str(a["player_id"])
    xs = [s["players"][pid_a][0] for s in a["snapshots"] if pid_a in s["players"]]
    check(
        len(xs) > 10 and (max(xs) - min(xs)) > 30,
        "runner bot moved via networked inputs",
        f"(x range {min(xs):.0f}..{max(xs):.0f})" if xs else "(no data)",
    )

    # Enemies simulated and synced
    enemy_counts = [len(s["enemies"]) for s in a["snapshots"]]
    check(
        enemy_counts and max(enemy_counts) > 0,
        "enemies present in snapshots",
        f"(max {max(enemy_counts) if enemy_counts else 0})",
    )

    # Projectiles appeared (BotB shoots)
    proj_max = max((s["projectiles"] for s in b["snapshots"]), default=0)
    check(proj_max > 0, "projectiles synced", f"(max {proj_max})")

    # Performance: snapshot rate, client fps, rtt, ack lag
    check(a["snapshot_rate"] >= 15, "client A snapshot rate >= 15/s", f"({a['snapshot_rate']}/s)")
    check(b["snapshot_rate"] >= 15, "client B snapshot rate >= 15/s", f"({b['snapshot_rate']}/s)")
    check(a["fps"] >= 55, "bot A frame rate >= 55", f"({a['fps']})")
    rtts = [r for r in a["rtt_samples"] + b["rtt_samples"] if r > 0]
    check(
        bool(rtts) and max(rtts) < 50, "RTT < 50ms on loopback", f"(max {max(rtts):.1f}ms)" if rtts else "(no samples)"
    )
    ack_lags = a["ack_lag_samples"] + b["ack_lag_samples"]
    check(
        bool(ack_lags) and max(ack_lags) <= 30,
        "input ack lag <= 30 ticks",
        f"(max {max(ack_lags) if ack_lags else '?'} ticks)",
    )

    # Netcode health (netstats): per-snapshot RTT, loss in both directions
    net = a["net_samples"] + b["net_samples"]
    rtt_p95 = [s["rtt_ms_p95"] for s in net if "rtt_ms_p95" in s]
    check(
        bool(rtt_p95) and max(rtt_p95) < 50,
        "per-snapshot RTT p95 < 50ms on loopback",
        f"(max {max(rtt_p95):.2f}ms)" if rtt_p95 else "(no samples)",
    )
    s2c_lost = a["link_totals"]["lost"] + b["link_totals"]["lost"]
    check(s2c_lost == 0, "no server->client packet loss on loopback", f"({s2c_lost} lost)")

    # Server performance
    if server_samples:
        rates = [s["tick_rate"] for s in server_samples[1:]] or [0]
        p95s = [s["tick_ms_p95"] for s in server_samples]
        sizes = [s["snapshot_bytes_last"] for s in server_samples if s.get("snapshot_bytes_last")]
        check(min(rates) >= 58, "server tick rate >= 58/s", f"(min {min(rates)})")
        check(max(p95s) < 12, "server tick p95 < 12ms", f"(max {max(p95s):.2f}ms)")
        if sizes:
            print(f"[e2e] info full-snapshot size ~{max(sizes)} bytes")

        peers = [p for s in server_samples for p in s.get("peers", {}).values()]
        c2s_lost = sum(p["link"]["lost"] for p in peers)
        check(c2s_lost == 0, "no client->server packet loss on loopback", f"({c2s_lost} lost)")
        check(
            any(p.get("client") for p in peers),
            "client netcode reports reach the server log",
        )
        if peers:
            starved = max(p["starved_pct"] for p in peers)
            burst = max(p["burst_pct"] for p in peers)
            print(f"[e2e] info server ticks without a new input: max {starved}%, with 2+ inputs: max {burst}%")
        rtt_p50 = [s["rtt_ms_p50"] for s in net if "rtt_ms_p50" in s]
        jitter = [s["link_jitter_ms"] for s in net]
        if rtt_p50:
            print(
                f"[e2e] info RTT p50 {sorted(rtt_p50)[len(rtt_p50) // 2]:.2f}ms, " f"s2c jitter max {max(jitter):.2f}ms"
            )
        delta_p95 = [s["delta_bytes_p95"] for s in server_samples if "delta_bytes_p95" in s]
        if delta_p95:
            print(f"[e2e] info delta snapshot p95 up to {max(delta_p95):.0f} bytes")
    else:
        check(False, "server metrics recorded")

    print(f"[e2e] {'PASS' if not failures else 'FAIL'} ({len(failures)} failures)")
    if not keep_logs and not failures:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--port", type=int, default=21777)
    parser.add_argument("--keep-logs", action="store_true")
    args = parser.parse_args()
    return run(args.duration, args.port, args.keep_logs)


if __name__ == "__main__":
    sys.exit(main())
