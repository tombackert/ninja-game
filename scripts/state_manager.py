"""State management foundation (Issue 10).

This module introduces a minimal stack based state manager used to drive
high-level application states (Menu, Game, Pause, Store, etc.).  It is an
incremental, non-breaking addition: existing code paths (direct calls to
`Menu()` or `Game().run()`) continue to function. A future iteration will
finish migration of event loops into state `handle/update/render` methods.

Usage Example (see `app.py` for a runnable harness):

    sm = StateManager()
    sm.set(MenuState())
    while running:
        events = pygame.event.get()
        sm.handle(events)
        sm.update(dt)
        sm.render(screen)

Design Notes:
- States are kept deliberately light: no enforced inheritance beyond the
  abstract interface. This keeps adoption friction low for existing code.
- A stack is used to allow overlays (e.g. PauseState) without discarding
  the underlying GameState.
- Transition helpers `push`, `pop`, and `set` invoke lifecycle hooks to
  let states allocate / release resources (or pause timers later on).
"""

from __future__ import annotations
from typing import List, Sequence
import pygame


class State:
    """Abstract base class for an application state.

    Subclasses should override lifecycle + loop hook methods. All methods
    are optional; the base implementations are no-ops to minimize friction
    during incremental migration.
    """

    name: str = "State"

    # Lifecycle -----------------------------------------------------
    def on_enter(
        self, previous: "State | None"
    ) -> None:  # pragma: no cover - default no-op
        pass

    def on_exit(
        self, next_state: "State | None"
    ) -> None:  # pragma: no cover - default no-op
        pass

    # Main loop hooks -----------------------------------------------
    def handle(
        self, events: Sequence[pygame.event.Event]
    ) -> None:  # pragma: no cover - default no-op
        pass

    def update(self, dt: float) -> None:  # pragma: no cover - default no-op
        pass

    def render(
        self, surface: pygame.Surface
    ) -> None:  # pragma: no cover - default no-op
        pass


class StateManager:
    """Stack-based state manager.

    Provides push/pop semantics and a `set` convenience to replace the
    current stack with a single state. Only the top state receives loop
    callbacks. This design allows overlay states (Pause) to be pushed on
    top of an active game state without discarding it.
    """

    def __init__(self) -> None:
        self._stack: List[State] = []

    # Introspection -------------------------------------------------
    @property
    def current(self) -> State | None:
        return self._stack[-1] if self._stack else None

    def stack_size(self) -> int:
        return len(self._stack)

    # Transitions ---------------------------------------------------
    def push(self, state: State) -> None:
        prev = self.current
        self._stack.append(state)
        state.on_enter(prev)

    def pop(self) -> State | None:
        if not self._stack:
            return None
        top = self._stack.pop()
        next_state = self.current
        top.on_exit(next_state)
        return top

    def set(self, state: State) -> None:
        # Exit all existing states (LIFO) before setting new root.
        while self._stack:
            popped = self._stack.pop()
            popped.on_exit(None if not self._stack else state)
        self._stack.append(state)
        state.on_enter(None)

    # Loop dispatch -------------------------------------------------
    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        if self.current:
            self.current.handle(events)

    def update(self, dt: float) -> None:
        if self.current:
            self.current.update(dt)

    def render(self, surface: pygame.Surface) -> None:
        if self.current:
            self.current.render(surface)


# Minimal placeholder state implementations -------------------------
# These wrap (or will wrap) existing modules. For now they are simple
# stubs; future iterations will migrate logic from `menu.py` & `game.py`.


class MenuState(State):
    name = "MenuState"

    def __init__(self) -> None:
        from scripts.displayManager import DisplayManager
        from scripts.ui import UI

        self.dm = DisplayManager()
        self.BASE_W = self.dm.BASE_W
        self.BASE_H = self.dm.BASE_H
        self.display = pygame.Surface((self.BASE_W, self.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self.options = ["Play", "Quit"]
        self.selected = 0
        self.enter = False
        self.quit_requested = False
        self.start_game = False
        self._ui = UI

    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    self.selected = (self.selected - 1) % len(self.options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.selected = (self.selected + 1) % len(self.options)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.enter = True
                elif event.key == pygame.K_ESCAPE:
                    self.quit_requested = True
            elif event.type == pygame.KEYUP:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.enter = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.enter = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.enter = False

    def update(self, dt: float) -> None:
        if self.enter:
            choice = self.options[self.selected]
            if choice == "Play":
                self.start_game = True
            elif choice == "Quit":
                self.quit_requested = True
            self.enter = False

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, "Menu", surface.get_width() // 2, 200)
        UI.render_o_box(
            surface, self.options, self.selected, surface.get_width() // 2, 300, 50
        )
        UI.render_menu_ui_element(
            surface,
            "ENTER select / ESC quit",
            surface.get_width() // 2 - 120,
            surface.get_height() - 40,
        )


class GameState(State):
    name = "GameState"

    def __init__(self) -> None:
        from game import Game

        self._game = Game()
        self._accum = 0.0  # basic accumulator if we later add fixed timestep

    @property
    def game(self):  # convenience
        return self._game

    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        if (
            hasattr(self._game, "km")
            and self._game.km
            and hasattr(self._game.km, "process_events")
        ):
            self._game.km.process_events(events)
        self.request_pause = False
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.request_pause = True
                break

    def update(self, dt: float) -> None:
        g = self._game
        # Partial migration: replicate subset of Game.run inner loop per frame.
        # This will be iteratively completed in future issues.
        if not g.running:
            return
        # Begin frame setup similar to Game.run
        g.cm.load_collectables()
        # Timer and screen prep
        g.timer.update(g.level)
        g.display.fill((0, 0, 0, 0))
        g.display_2.blit(g.assets["background"], (0, 0))
        g.screenshake = max(0, g.screenshake - 1)
        # Flag collisions / level completion (trimmed for brevity)
        for flag_rect in getattr(g, "flags", []):
            if g.player.rect().colliderect(flag_rect):
                g.endpoint = True
        # Basic transition handling (no level advance to avoid side-effects yet)
        if g.transition:
            from scripts.effects import Effects

            Effects.transition(g)

    def render(self, surface: pygame.Surface) -> None:
        # Compose displays onto provided surface with scaling to window size.
        g = self._game
        from scripts.ui import UI

        # Ensure timer UI (and later: best time, level etc.)
        UI.render_game_ui_element(g.display_2, f"{g.timer.text}", g.BASE_W - 70, 5)

        # Scale internal low-res buffer to target surface size (avoids quarter-size issue)
        if g.display_2.get_size() != surface.get_size():
            scaled = pygame.transform.scale(g.display_2, surface.get_size())
            surface.blit(scaled, (0, 0))
        else:
            surface.blit(g.display_2, (0, 0))


class PauseState(State):
    name = "PauseState"

    def __init__(self) -> None:
        self._ticks = 0
        self.closed = False
        self.return_to_menu = False
        self._underlying: State | None = None  # set in on_enter

    def on_enter(self, previous: "State | None") -> None:  # capture underlying
        self._underlying = previous

    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.closed = True
                if event.key == pygame.K_m:
                    self.return_to_menu = True
                    self.closed = True

    def update(self, dt: float) -> None:
        self._ticks += 1

    def render(self, surface: pygame.Surface) -> None:
        # Render underlying (frozen) game frame if available before overlay.
        if self._underlying and hasattr(self._underlying, "render"):
            # Only call render (no update) to keep simulation paused.
            self._underlying.render(surface)

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))  # semi-transparent darkening
        surface.blit(overlay, (0, 0))
        font = pygame.font.SysFont(None, 48)
        text = font.render("PAUSED (ESC resume / M menu)", True, (255, 255, 255))
        surface.blit(text, (surface.get_width() // 2 - text.get_width() // 2, 120))


"""End of Issue 10 implementation."""
