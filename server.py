"""Dedicated Multiplayer Server (MP-06).

Entry point for the authoritative game server. Runs a HeadlessGame
with GameServer networking at a fixed 60 Hz tick rate.

Usage:
    python server.py --port 7777 --level 0 --max-clients 4
    python server.py --metrics-file /tmp/server_metrics.jsonl  # perf logging
"""

from __future__ import annotations

import argparse
import json
import signal
import time

import pygame

from scripts.network.game_server import GameServer
from scripts.network.headless_game import HeadlessGame

TICK_RATE = 60
TICK_INTERVAL = 1.0 / TICK_RATE


def main() -> None:
    parser = argparse.ArgumentParser(description="Ninja Game Multiplayer Server")
    parser.add_argument("--port", type=int, default=7777, help="Server port")
    parser.add_argument("--level", type=int, default=0, help="Level to load")
    parser.add_argument("--max-clients", type=int, default=4, help="Max players")
    parser.add_argument("--metrics-file", default=None, help="Write per-second performance metrics as JSONL")
    args = parser.parse_args()

    # Initialize pygame minimally (needed for Rect in physics)
    pygame.init()

    game = HeadlessGame(level=args.level)

    # SDL swallows SIGTERM (it queues an SDL_QUIT event the headless loop
    # never polls), so a host calling Popen.terminate() would leave a zombie
    # server. Install our own handler for a clean shutdown instead.
    signal.signal(signal.SIGTERM, lambda signum, frame: setattr(game, "running", False))
    server = GameServer(port=args.port, max_clients=args.max_clients, game=game)

    # Wire callbacks
    server.on_player_join(lambda pid, name: _on_join(game, pid, name))
    server.on_player_leave(lambda pid, reason: _on_leave(game, pid, reason))

    print(
        f"Server started on port {args.port}, level {args.level}, " f"max {args.max_clients} players",
        flush=True,
    )

    metrics_fh = open(args.metrics_file, "a") if args.metrics_file else None

    # Fixed-timestep loop: next_tick accumulates so a slow tick is caught up
    # instead of permanently lowering the tick rate.
    next_tick = time.perf_counter()
    tick_durations: list[float] = []
    ticks_this_second = 0
    last_report = time.perf_counter()

    try:
        while game.running:
            start = time.perf_counter()

            server.process_inputs()
            game.simulate_tick()
            server.post_tick()

            tick_durations.append(time.perf_counter() - start)
            ticks_this_second += 1

            now = time.perf_counter()
            if now - last_report >= 1.0:
                _report(server, game, tick_durations, ticks_this_second, metrics_fh)
                tick_durations.clear()
                ticks_this_second = 0
                last_report = now

            next_tick += TICK_INTERVAL
            sleep_time = next_tick - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
            elif sleep_time < -1.0:
                # Fell way behind (e.g. suspended); don't try to catch up
                next_tick = time.perf_counter()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.shutdown()
        if metrics_fh:
            metrics_fh.close()
        pygame.quit()


def _report(server, game, tick_durations, tick_rate, metrics_fh) -> None:
    """Emit one line of per-second performance metrics."""
    if not tick_durations:
        return
    sorted_d = sorted(tick_durations)
    p50 = sorted_d[len(sorted_d) // 2] * 1000
    p95 = sorted_d[int(len(sorted_d) * 0.95)] * 1000
    worst = sorted_d[-1] * 1000
    sample = {
        "t": time.time(),
        "tick": game.tick,
        "tick_rate": tick_rate,
        "tick_ms_p50": round(p50, 3),
        "tick_ms_p95": round(p95, 3),
        "tick_ms_max": round(worst, 3),
        "clients": server.get_client_count(),
        "players": len(game.players),
        "enemies": len(game.enemies),
        "projectiles": len(game.projectiles),
        "snapshot_bytes_last": server.stats.get("last_snapshot_bytes", 0),
        "snapshots_sent": server.stats.get("snapshots_sent", 0),
    }
    if metrics_fh:
        metrics_fh.write(json.dumps(sample) + "\n")
        metrics_fh.flush()
    if tick_rate < 55 or p95 > 12.0:
        print(f"[perf] tick_rate={tick_rate} p95={p95:.1f}ms max={worst:.1f}ms", flush=True)


def _on_join(game: HeadlessGame, player_id: int, name: str) -> None:
    player = game.add_player(player_id)
    print(f"Player '{name}' (ID {player_id}) joined at {player.pos}", flush=True)


def _on_leave(game: HeadlessGame, player_id: int, reason: str) -> None:
    game.remove_player(player_id)
    print(f"Player ID {player_id} left ({reason})", flush=True)


if __name__ == "__main__":
    main()
