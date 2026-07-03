"""Headless multiplayer E2E bot (used by tools/mp_e2e.py).

Connects a real GameClient to a running server, plays a scripted input
pattern at 60 Hz, and records what it observes: RTT, snapshot arrival
rate, input acks, and per-snapshot player/enemy/collectable state.

At the end it writes a JSON report to --report so the orchestrator can
assert cross-client consistency (both clients must observe identical
authoritative state for the same tick).

Usage:
    python tools/mp_e2e_bot.py --port 7777 --name BotA --pattern runner \
        --duration 10 --report /tmp/botA.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, ".")

from scripts.network.game_client import GameClient  # noqa: E402

FRAME_INTERVAL = 1.0 / 60.0


def input_for_frame(pattern: str, frame: int) -> tuple[tuple[bool, bool], list[str]]:
    """Scripted input patterns."""
    actions: list[str] = []
    if pattern == "runner":
        # Run right 2s, left 2s, jump every 90 frames, dash every 200
        phase = (frame // 120) % 2
        move = (False, True) if phase == 0 else (True, False)
        if frame % 90 == 45:
            actions.append("jump")
        if frame % 200 == 100:
            actions.append("dash")
    elif pattern == "shooter":
        # Mostly stationary, hops and shoots
        move = (False, False)
        if frame % 120 == 60:
            actions.append("jump")
        if frame % 45 == 10:
            actions.append("shoot")
    else:  # idle
        move = (False, False)
    return move, actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--name", default="Bot")
    parser.add_argument("--pattern", default="runner")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    client = GameClient(server_host=args.host, server_port=args.port, player_name=args.name)
    events: list[str] = []
    client.on_disconnected(lambda r: events.append(f"disconnected:{r}"))
    client.connect()

    # Wait for connection (up to 6s)
    deadline = time.time() + 6.0
    while not client.is_connected and time.time() < deadline:
        client.update()
        time.sleep(0.01)

    report: dict = {
        "name": args.name,
        "connected": client.is_connected,
        "player_id": client.player_id,
        "level": client.level,
        "events": events,
        "snapshots": [],  # sampled (tick -> state digest)
        "rtt_samples": [],
        "ack_lag_samples": [],
        "frame_overruns": 0,
    }
    if not client.is_connected:
        with open(args.report, "w") as f:
            json.dump(report, f)
        return 1

    seen_ticks: set[int] = set()
    snapshot_count = 0
    frame = 0
    start = time.perf_counter()
    next_frame = start

    while time.perf_counter() - start < args.duration:
        client.update()

        move, actions = input_for_frame(args.pattern, frame)
        client.send_input_state(move, actions)

        snap = client.get_latest_snapshot()
        if snap is not None and snap.tick not in seen_ticks:
            seen_ticks.add(snap.tick)
            snapshot_count += 1
            # Record a digest of authoritative state for cross-client checks
            report["snapshots"].append(
                {
                    "tick": snap.tick,
                    "players": {
                        str(p.id): [round(p.pos[0], 3), round(p.pos[1], 3), p.lives, p.coins, p.ammo]
                        for p in snap.players
                    },
                    "enemies": {str(e.id): [round(e.pos[0], 3), round(e.pos[1], 3)] for e in snap.enemies},
                    "projectiles": len(snap.projectiles),
                    "collected": sorted(snap.collected),
                }
            )

        if frame % 60 == 30:
            report["rtt_samples"].append(round(client.rtt * 1000, 3))
            report["ack_lag_samples"].append(client.local_tick - client.input_ack_tick)

        frame += 1
        next_frame += FRAME_INTERVAL
        sleep = next_frame - time.perf_counter()
        if sleep > 0:
            time.sleep(sleep)
        else:
            report["frame_overruns"] += 1
            next_frame = time.perf_counter()

    elapsed = time.perf_counter() - start
    report["snapshot_rate"] = round(snapshot_count / elapsed, 2)
    report["frames"] = frame
    report["fps"] = round(frame / elapsed, 2)
    report["server_tick_end"] = client.server_tick
    report["local_tick_end"] = client.local_tick
    report["input_ack_tick_end"] = client.input_ack_tick

    client.disconnect()
    client.close()

    with open(args.report, "w") as f:
        json.dump(report, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
