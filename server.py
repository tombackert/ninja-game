"""Dedicated Multiplayer Server (MP-06).

Entry point for the authoritative game server. Runs a HeadlessGame
with GameServer networking at 60 Hz.

Usage:
    python server.py --port 7777 --level 0 --max-clients 4
"""

from __future__ import annotations

import argparse
import time

import pygame

from scripts.network.game_server import GameServer
from scripts.network.headless_game import HeadlessGame


def main() -> None:
    parser = argparse.ArgumentParser(description="Ninja Game Multiplayer Server")
    parser.add_argument("--port", type=int, default=7777, help="Server port")
    parser.add_argument("--level", type=int, default=0, help="Level to load")
    parser.add_argument("--max-clients", type=int, default=4, help="Max players")
    args = parser.parse_args()

    # Initialize pygame minimally (needed for Rect in physics)
    pygame.init()

    game = HeadlessGame(level=args.level)
    server = GameServer(port=args.port, max_clients=args.max_clients, game=game)

    # Wire callbacks
    server.on_player_join(lambda pid, name: _on_join(game, pid, name))
    server.on_player_leave(lambda pid, reason: _on_leave(game, pid, reason))

    print(f"Server started on port {args.port}, level {args.level}, max {args.max_clients} players")

    tick_rate = 60
    tick_interval = 1.0 / tick_rate

    try:
        while game.running:
            start = time.time()

            server.process_inputs()
            game.simulate_tick()
            server.post_tick()

            # Sleep to maintain tick rate
            elapsed = time.time() - start
            sleep_time = tick_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.shutdown()
        pygame.quit()


def _on_join(game: HeadlessGame, player_id: int, name: str) -> None:
    player = game.add_player(player_id)
    print(f"Player '{name}' (ID {player_id}) joined at {player.pos}")


def _on_leave(game: HeadlessGame, player_id: int, reason: str) -> None:
    game.remove_player(player_id)
    print(f"Player ID {player_id} left ({reason})")


if __name__ == "__main__":
    main()
