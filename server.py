"""Dedicated Multiplayer Server (MP-06).

Entry point for the authoritative game server. Runs a HeadlessGame
with GameServer networking at a fixed 60 Hz tick rate.

Every run writes a session log (JSONL) to data/netlogs/: a session line,
one sample per second (tick timing, snapshot sizes, per-client netcode
health including each client's own summary) and events (hitches, stalls,
joins/leaves). See docs/multiplayer.md.

Usage:
    python server.py --port 7777 --level 0 --max-clients 4
    python server.py --metrics-file /tmp/server_metrics.jsonl  # log to this file instead
    python server.py --no-netlog                               # no session log
"""

from __future__ import annotations

import argparse
import os
import signal
import time

import pygame

from scripts.network.game_server import GameServer
from scripts.network.headless_game import HeadlessGame
from scripts.network.netstats import SessionLog

TICK_RATE = 60
TICK_INTERVAL = 1.0 / TICK_RATE
# A tick starting this late after the previous one is a hitch players feel
HITCH_INTERVAL = 2 * TICK_INTERVAL


def main() -> None:
    parser = argparse.ArgumentParser(description="Ninja Game Multiplayer Server")
    parser.add_argument("--port", type=int, default=7777, help="Server port")
    parser.add_argument("--level", type=int, default=0, help="Level to load")
    parser.add_argument("--max-clients", type=int, default=4, help="Max players")
    parser.add_argument("--metrics-file", default=None, help="Write the session log (JSONL) to this file")
    parser.add_argument("--no-netlog", action="store_true", help="Do not write a session log")
    parser.add_argument("--parent-pid", type=int, default=0, help="Shut down when this process (the host's game) exits")
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

    log = _open_log(args)
    started = time.time()
    if log:
        log.write(
            {
                "type": "session",
                "role": "server",
                "t": round(started, 3),
                "pid": os.getpid(),
                "port": args.port,
                "level": args.level,
                "max_clients": args.max_clients,
                "tick_rate": TICK_RATE,
                "snapshot_interval": GameServer.SNAPSHOT_INTERVAL,
                "full_snapshot_interval": GameServer.FULL_SNAPSHOT_INTERVAL,
            }
        )
        print(f"Session log: {log.path}", flush=True)

    # Fixed-timestep loop: next_tick accumulates so a slow tick is caught up
    # instead of permanently lowering the tick rate.
    next_tick = time.perf_counter()
    ticks_this_second = 0
    last_report = time.perf_counter()
    last_start = 0.0

    try:
        while game.running:
            start = time.perf_counter()

            server.process_inputs()
            game.simulate_tick()
            server.post_tick()

            duration = time.perf_counter() - start
            server.netstats.add("tick_ms", duration * 1000.0)
            if last_start:
                interval = start - last_start
                server.netstats.add("tick_interval_ms", interval * 1000.0)
                if interval > HITCH_INTERVAL or duration > TICK_INTERVAL:
                    server.netstats.count("hitches")
                    server.netstats.event(
                        "server_hitch",
                        tick=game.tick,
                        interval_ms=round(interval * 1000.0, 1),
                        tick_ms=round(duration * 1000.0, 1),
                    )
            last_start = start
            ticks_this_second += 1

            now = time.perf_counter()
            if now - last_report >= 1.0:
                _report(server, game, ticks_this_second, log)
                ticks_this_second = 0
                last_report = now
                if args.parent_pid and os.getppid() != args.parent_pid:
                    # The game that hosts us is gone (crash, force quit):
                    # an orphaned server would keep holding the port
                    print("Host game exited, shutting down", flush=True)
                    break

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
        if log:
            log.write_all(server.netstats.drain_events())
            log.write(
                {
                    "type": "summary",
                    "t": round(time.time(), 3),
                    "duration_s": round(time.time() - started, 1),
                    "ticks": game.tick,
                    "counts": server.netstats.totals,
                }
            )
            log.close()
        pygame.quit()


def _open_log(args) -> SessionLog | None:
    if args.metrics_file:
        return SessionLog(args.metrics_file)
    if args.no_netlog:
        return None
    return SessionLog.create("server")


def _report(server: GameServer, game: HeadlessGame, tick_rate: int, log: SessionLog | None) -> None:
    """Emit one per-second sample: tick timing, snapshot sizes, per-client health."""
    stats = server.netstats.take_sample()
    peers = server.client_reports()
    sample = {
        "type": "sample",
        "t": round(time.time(), 3),
        "tick": game.tick,
        "tick_rate": tick_rate,
        **stats,
        "clients": server.get_client_count(),
        "players": len(game.players),
        "enemies": len(game.enemies),
        "projectiles": len(game.projectiles),
        "snapshot_bytes_last": server.stats.get("last_snapshot_bytes", 0),
        "snapshots_sent": server.stats.get("snapshots_sent", 0),
        "peers": peers,
    }
    if log:
        log.write(sample)
        log.write_all(server.netstats.drain_events())
    else:
        server.netstats.drain_events()
    p95 = stats.get("tick_ms_p95", 0.0)
    if tick_rate < 55 or p95 > 12.0:
        print(f"[perf] tick_rate={tick_rate} p95={p95:.1f}ms max={stats.get('tick_ms_max', 0.0):.1f}ms", flush=True)


def _on_join(game: HeadlessGame, player_id: int, name: str) -> None:
    player = game.add_player(player_id)
    print(f"Player '{name}' (ID {player_id}) joined at {player.pos}", flush=True)


def _on_leave(game: HeadlessGame, player_id: int, reason: str) -> None:
    game.remove_player(player_id)
    print(f"Player ID {player_id} left ({reason})", flush=True)


if __name__ == "__main__":
    main()
