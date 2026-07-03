"""Application entry harness using StateManager.

Temporary experimental loop to validate migration of Game/Menu into
states. For now it launches directly into GameState. ESC in-game sets a
pause request which results in a PauseState being pushed.
"""

from __future__ import annotations

import argparse
import os

import pygame

from scripts.input_router import InputRouter
from scripts.state_manager import (
    AccessoriesState,
    GameState,
    LevelsState,
    MenuState,
    OptionsState,
    PauseState,
    StateManager,
    StoreState,
)


def main():
    parser = argparse.ArgumentParser(description="Ninja Game")
    parser.add_argument("--multiplayer", action="store_true", help="Connect to multiplayer server")
    parser.add_argument("--host", default="127.0.0.1", help="Server host for multiplayer")
    parser.add_argument("--port", type=int, default=7777, help="Server port for multiplayer")
    parser.add_argument("--name", default="Player", help="Player name for multiplayer")
    args = parser.parse_args()

    os.environ.setdefault("NINJA_GAME_TESTING", "0")
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))  # windowed for development
    clock = pygame.time.Clock()

    sm = StateManager()
    router = InputRouter()

    if args.multiplayer:
        from scripts.multiplayer_state import MultiplayerGameState

        sm.set(MultiplayerGameState(args.host, args.port, args.name))
    else:
        sm.set(MenuState())

    running = True
    while running:
        # --- Single central event poll (Issue 10 + 11) ---
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT:
                running = False

        # Input routing -> actions -> state handling
        current_name = sm.current.name if sm.current else ""
        actions = router.process(events, current_name)
        sm.handle_actions(actions)
        # Provide raw events to current state (GameState uses this to update movement flags)
        sm.handle(events)

        # State-driven transitions (minimal, non-invasive)
        cur = sm.current
        if isinstance(cur, MenuState):
            if getattr(cur, "start_game", False):
                sm.set(GameState())
                cur = sm.current
            elif getattr(cur, "quit_requested", False):
                running = False
            elif getattr(cur, "next_state", None):
                nxt = cur.next_state
                cur.next_state = None
                if nxt == "Levels":
                    sm.set(LevelsState())
                elif nxt == "Store":
                    sm.set(StoreState())
                elif nxt == "Accessories":
                    sm.set(AccessoriesState())
                elif nxt == "Options":
                    sm.set(OptionsState())
                cur = sm.current
        # Generic back handling for submenu states
        if isinstance(cur, (LevelsState, StoreState, AccessoriesState, OptionsState)):
            if getattr(cur, "request_back", False):
                sm.set(MenuState())
                cur = sm.current
        if isinstance(cur, GameState) and getattr(cur, "request_pause", False):
            sm.push(PauseState())
        if hasattr(cur, "name") and cur.name == "MultiplayerGameState" and getattr(cur, "request_pause", False):
            sm.push(PauseState())
        if isinstance(cur, PauseState) and cur.closed:
            return_to_menu = cur.return_to_menu
            sm.pop()  # resume underlying state (GameState)
            if return_to_menu:
                sm.set(MenuState())

        # --- Update & Render cycle ---
        dt = clock.tick(60) / 1000.0  # 60 FPS cap; dt in seconds
        sm.update(dt)
        # Mark end of work segment just after state update & render prep but before present
        sm.render(screen)
        pygame.display.flip()

    # Graceful shutdown
    pygame.quit()


if __name__ == "__main__":  # pragma: no cover
    main()
