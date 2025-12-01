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

from scripts.logger import get_logger
from scripts.ui_widgets import ScrollableListWidget

_state_log = get_logger("state")


class State:
    """Abstract base class for an application state.

    Subclasses should override lifecycle + loop hook methods. All methods
    are optional; the base implementations are no-ops to minimize friction
    during incremental migration.
    """

    name: str = "State"

    # Lifecycle -----------------------------------------------------
    def on_enter(self, previous: "State | None") -> None:  # pragma: no cover - default no-op
        pass

    def on_exit(self, next_state: "State | None") -> None:  # pragma: no cover - default no-op
        pass

    # Main loop hooks -----------------------------------------------
    def handle(self, events: Sequence[pygame.event.Event]) -> None:  # pragma: no cover - default no-op
        pass

    # New action-based hook (Issue 11). States migrating to InputRouter
    # should override this instead of `handle`.
    def handle_actions(self, actions: Sequence[str]) -> None:  # pragma: no cover
        pass

    def update(self, dt: float) -> None:  # pragma: no cover - default no-op
        pass

    def render(self, surface: pygame.Surface) -> None:  # pragma: no cover - default no-op
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
        _state_log.debug("StateManager init (empty stack)")

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
        _state_log.debug("push", state.name, "-> stack:", [s.name for s in self._stack])

    def pop(self) -> State | None:
        if not self._stack:
            return None
        top = self._stack.pop()
        next_state = self.current
        top.on_exit(next_state)
        _state_log.debug("pop", top.name, "-> stack:", [s.name for s in self._stack])
        return top

    def set(self, state: State) -> None:
        # Exit all existing states (LIFO) before setting new root.
        while self._stack:
            popped = self._stack.pop()
            popped.on_exit(None if not self._stack else state)
            _state_log.debug("discard", popped.name)
        self._stack.append(state)
        state.on_enter(None)
        _state_log.debug("set", state.name, "(root)")

    # Loop dispatch -------------------------------------------------
    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        if self.current:
            self.current.handle(events)

    def handle_actions(self, actions: Sequence[str]) -> None:
        if self.current:
            # Prefer new action API when implemented by state.
            if hasattr(self.current, "handle_actions"):
                if actions:
                    _state_log.debug("actions ->", self.current.name, actions)
                self.current.handle_actions(actions)  # type: ignore[attr-defined]

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
        self.options = [
            "Play",
            "Levels",
            "Store",
            "Accessories",
            "Options",
            "Quit",
        ]
        self.list_widget = ScrollableListWidget(self.options, visible_rows=6, spacing=50, font_size=30)
        self.selected = 0  # legacy compatibility (to be removed)
        self.enter = False
        self.quit_requested = False
        self.start_game = False
        self.next_state: str | None = None  # for submenu transitions
        self._ui = UI

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act == "menu_up":
                self.list_widget.move_up()
            elif act == "menu_down":
                self.list_widget.move_down()
            elif act == "menu_select":
                self.enter = True
            elif act == "menu_quit":
                self.quit_requested = True

    def update(self, dt: float) -> None:
        if self.enter:
            choice = self.list_widget.options[self.list_widget.selected_index]
            if choice == "Play":
                self.start_game = True
            elif choice == "Quit":
                self.quit_requested = True
            elif choice in ("Levels", "Store", "Accessories", "Options"):
                # Defer instantiation to app loop to avoid heavy imports here
                self.next_state = choice
            # Future: branch to other submenus (Levels/Store/etc.) via state transitions
            self.enter = False

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, "Menu", surface.get_width() // 2, 200)
        self.list_widget.render(surface, surface.get_width() // 2, 300)
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

        # Underlying legacy Game object (entities, systems, assets)
        self._game = Game()
        # Allow renderer to query state flags (performance HUD toggle) without tight coupling
        try:
            setattr(self._game, "state_ref", self)
        except Exception:
            pass
        self._accum = 0.0  # placeholder for future fixed timestep accumulator
        self._initialized_audio = False
        self.request_pause = False
        # Performance HUD (timings + counts) toggle (F1) - start disabled to match legacy debug overlay test expectation
        self.perf_enabled = False
        # Backward-compatible alias for existing test referencing debug_overlay
        self.debug_overlay = self.perf_enabled

    @property
    def game(self):  # convenience
        return self._game

    # ------------------------------------------------------------------
    # Lifecycle
    def on_enter(self, previous: "State | None") -> None:  # pragma: no cover - simple side-effect
        # Start background music / ambience (skip when under test to avoid mixer issues).
        import os

        # Initialize RNG service to ensure it's ready for gameplay
        from scripts.rng_service import RNGService

        RNGService.get()

        if os.environ.get("NINJA_GAME_TESTING") != "1" and not self._initialized_audio:
            try:  # Best-effort; audio is ancillary.
                self._game.audio.play_music("data/music.wav", loops=-1)
                self._game.audio.play("ambience", loops=-1)
                self._initialized_audio = True
            except Exception:  # pragma: no cover - audio optional in CI
                pass

    def on_exit(self, next_state: "State | None") -> None:  # pragma: no cover - simple persistence
        # Persist collectables & best times when leaving game state entirely (not just pausing).
        try:
            self._game.cm.save_collectables()
            # Commit any pending replay if we finished a level?
            # Actually, replay commit happens on level completion, which is inside update() usually.
            # But if we quit, we might want to abort.
            replay = getattr(self._game, "replay", None)
            if replay:
                replay.recording = None # Abort on exit without finish
        except Exception:  # pragma: no cover
            pass

    def handle_actions(self, actions: Sequence[str]) -> None:
        # Reset per-frame toggles
        self.request_pause = False
        for act in actions:
            if act == "pause_toggle":
                self.request_pause = True
            elif act == "debug_toggle":
                self.perf_enabled = not self.perf_enabled
                self.debug_overlay = self.perf_enabled  # keep alias in sync
        
        # Pass actions to replay system
        replay = getattr(self._game, "replay", None)
        player = getattr(self._game, "player", None)
        if replay and player:
            replay.update(player, list(actions))

    # Raw event handling (for continuous movement / jump / dash until migrated to action axes)
    def handle(self, events: Sequence[pygame.event.Event]) -> None:  # pragma: no cover - thin delegation
        # Delegate to legacy KeyboardManager in batch-processing mode to update movement flags
        km = getattr(self._game, "km", None)
        if km and hasattr(km, "process_events"):
            try:
                km.process_events(events)
            except Exception:
                pass

    def update(self, dt: float) -> None:
        """Full simulation step (logic-only; rendering handled in render()).

        This migrates the legacy `Game.run` loop responsibilities into
        a per-frame update suitable for the state-driven architecture.
        Visual layering & HUD composition live in `Renderer`.
        """
        g = self._game
        if not g.running:
            return  # Game externally marked finished (future: transition to Menu)
        # If a PauseState render is freezing this frame, skip simulation changes.
        if getattr(g, "_paused_freeze", False):
            return
        replay_mgr = getattr(g, "replay", None)

        # --- Core time & housekeeping ---
        g.timer.update(g.level)
        g.screenshake = max(0, g.screenshake - 1)

        # --- Level completion / flag collision ---
        for flag_rect in getattr(g, "flags", []):
            if g.player.rect().colliderect(flag_rect):
                g.endpoint = True

        from scripts.constants import (
            DEAD_ANIM_FADE_START,
            RESPAWN_DEAD_THRESHOLD,
            TRANSITION_MAX,
        )
        from scripts.level_cache import list_levels
        from scripts.settings import settings

        if g.endpoint:
            g.transition += 1
            if g.transition > TRANSITION_MAX:
                # Level advance logic
                elapsed_ms = g.timer.elapsed_time
                new_best = g.timer.update_best_time()
                if replay_mgr:
                    replay_mgr.commit_run(new_best=new_best)
                levels = list_levels()
                try:
                    current_level_index = levels.index(g.level)
                except ValueError:
                    current_level_index = 0
                if current_level_index == len(levels) - 1:
                    g.load_level(g.level)
                else:
                    next_level = levels[current_level_index + 1]
                    g.level = next_level
                    settings.set_level_to_playable(g.level)
                    settings.selected_level = g.level
                    g.load_level(g.level)
        if g.transition < 0:
            g.transition += 1

        # --- Death / respawn handling ---
        # (Note: legacy attribute 'lifes' renamed to 'lives' internally; we access both defensively.)
        player_lives_attr = getattr(g.player, "lives", getattr(g.player, "lifes", 0))
        if player_lives_attr < 1:
            g.dead += 1
        if g.dead:
            g.dead += 1
            if g.dead >= DEAD_ANIM_FADE_START:
                g.transition = min(TRANSITION_MAX, g.transition + 1)
            if g.dead > RESPAWN_DEAD_THRESHOLD and player_lives_attr >= 1:
                if replay_mgr:
                    try:
                        replay_mgr.abort_current_run()
                    except Exception:
                        pass
                g.load_level(g.level, player_lives_attr, respawn=True)
            if g.dead > RESPAWN_DEAD_THRESHOLD and player_lives_attr < 1:
                if replay_mgr:
                    try:
                        replay_mgr.abort_current_run()
                    except Exception:
                        pass
                g.load_level(g.level)

        # --- Input (legacy direct keyboard polling) ---
        # Retain existing KeyboardManager driven movement until action-based movement introduced.
        if hasattr(g, "km"):
            try:
                # Only mouse polling here; keyboard handled via handle(events)
                g.km.handle_mouse_input()
            except Exception:  # pragma: no cover - input optional in headless tests
                pass

        # --- Transition visual state (logic portion) ---
        if g.transition:
            # Only the numeric transition value is advanced here; actual
            # drawing of the transition effect occurs in Renderer.render.
            pass

        # --- Systems ---
        if hasattr(g, "projectiles") and hasattr(g.projectiles, "update"):
            g.projectiles.update(g.tilemap, g.players, g.enemies)

        # Particle system update remains in renderer (coupled to render order)

    def render(self, surface: pygame.Surface) -> None:
        # Delegate full frame composition to unified Renderer (Issue 14).
        from scripts.renderer import Renderer

        if not hasattr(self, "_renderer"):
            # Lazy construct; avoids cost during test discovery when GameState unused.
            # Use renderer's own performance HUD (app-level HUD removed to avoid duplication).
            self._renderer = Renderer(show_perf=True)
        self._renderer.render(self._game, surface)


class PauseState(State):
    name = "PauseState"

    def __init__(self) -> None:
        from scripts.ui_widgets import ScrollableListWidget

        self._ticks = 0
        self.closed = False
        self.return_to_menu = False
        self.quit_requested = False
        self._underlying: State | None = None  # set in on_enter
        self.options = ["Resume", "Menu"]
        self.widget = ScrollableListWidget(self.options, visible_rows=3, spacing=60, font_size=30)
        self.bg: pygame.Surface | None = None
        # Background image (menu backdrop) for pause overlay decoration
        try:
            self.bg = pygame.image.load("data/images/background-big.png")
        except Exception:  # pragma: no cover - asset optional in tests
            pass

    def on_enter(self, previous: "State | None") -> None:  # capture underlying
        self._underlying = previous

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act in ("menu_up",):
                self.widget.move_up()
            elif act in ("menu_down",):
                self.widget.move_down()
            elif act in ("pause_close",):  # ESC resume
                self.closed = True
            elif act == "pause_menu":  # legacy direct key -> menu
                self.return_to_menu = True
                self.closed = True
            elif act == "menu_select":
                choice = self.options[self.widget.selected_index]
                if choice == "Resume":
                    self.closed = True
                elif choice == "Menu":
                    self.return_to_menu = True
                    self.closed = True

    def update(self, dt: float) -> None:
        self._ticks += 1

    def render(self, surface: pygame.Surface) -> None:
        # Render underlying (frozen) game frame if available before overlay.
        if self._underlying and hasattr(self._underlying, "render"):
            # Freeze underlying simulation-driven updates inside render path.
            underlying = self._underlying
            game_obj = getattr(underlying, "game", None)
            if game_obj is not None:
                setattr(game_obj, "_paused_freeze", True)
            # Render one frozen frame
            underlying.render(surface)
            if game_obj is not None:
                setattr(game_obj, "_paused_freeze", False)
        # Semi-transparent overlay
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))  # semi-transparent darkening
        surface.blit(overlay, (0, 0))
        # Optional faint menu background blended in
        if self.bg:
            try:
                bg_scaled = pygame.transform.scale(self.bg, surface.get_size())
                bg_scaled.set_alpha(60)
                surface.blit(bg_scaled, (0, 0))
            except Exception:  # pragma: no cover
                pass
        # Title
        from scripts.ui import UI

        font = UI.get_font(50)
        UI.draw_text_with_outline(
            surface=surface,
            font=font,
            text="Paused",
            x=surface.get_width() // 2,
            y=140,
            center=True,
            scale=3,
        )
        # Options list (centered)
        self.widget.render(surface, surface.get_width() // 2, 260)
        # Footer hint
        UI.render_menu_ui_element(
            surface,
            "ENTER select / ESC resume",
            surface.get_width() // 2 - 130,
            surface.get_height() - 60,
        )
        UI.render_menu_ui_element(
            surface,
            "Up/Down navigate",
            surface.get_width() // 2 - 110,
            surface.get_height() - 40,
        )


# ---------------- Additional Menu Sub-States (Issue 12) -----------------


class LevelsState(State):
    name = "LevelsState"

    def __init__(self) -> None:
        from scripts.displayManager import DisplayManager
        from scripts.level_cache import list_levels
        from scripts.progress_tracker import get_progress_tracker
        from scripts.settings import settings
        from scripts.ui import UI

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.progress = get_progress_tracker()
        # Use tracker levels (already sorted) to populate list;
        # fallback to direct scan if empty.
        self.levels = self.progress.levels or list_levels()
        # Ensure currently selected level is visible
        selected = self.settings.selected_level
        if selected in self.levels:
            self.index = self.levels.index(selected)
        else:
            self.index = 0
        self.widget = ScrollableListWidget(
            [f"Level {lvl:<2}" for lvl in self.levels],
            visible_rows=5,
            spacing=50,
            font_size=30,
        )
        self.widget.selected_index = self.index
        self.message: str | None = None
        self.message_timer: float = 0.0
        self.request_back = False
        self.enter = False

    def handle_actions(self, actions: Sequence[str]) -> None:
        for a in actions:
            if a == "menu_up":
                self.widget.move_up()
            elif a == "menu_down":
                self.widget.move_down()
            elif a == "menu_select":
                self.enter = True
            elif a in ("menu_back", "menu_quit"):
                self.request_back = True

    def update(self, dt: float) -> None:
        if self.enter:
            lvl = self.levels[self.widget.selected_index]
            # Use tracker authoritative unlock state
            if self.progress.is_unlocked(lvl):
                self.settings.selected_level = lvl
                self.message = f"Selected level {lvl}"
            else:
                self.message = "Level not unlocked!"
            self.message_timer = 1.0  # seconds
            self.enter = False
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, "Select Level", surface.get_width() // 2, 160)
        # Decorate selected & owned indicator with padlocks at side
        self.widget.render(surface, surface.get_width() // 2, 260)
        # Draw padlocks
        for i in range(self.widget.visible_rows):
            idx = self.widget._scroll_offset + i
            if idx >= len(self.levels):
                break
            lvl = self.levels[idx]
            icon = "data/images/padlock-o.png" if self.progress.is_unlocked(lvl) else "data/images/padlock-c.png"
            UI.render_ui_img(
                surface,
                icon,
                surface.get_width() // 2 + 150,
                260 + (i * self.widget.spacing),
                0.15,
            )
        UI.render_menu_ui_element(
            surface,
            f"Current: {self.settings.selected_level}",
            20,
            20,
        )
        UI.render_menu_ui_element(
            surface,
            "ESC to menu",
            20,
            surface.get_height() - 40,
        )
        if self.message:
            UI.render_menu_msg(
                surface,
                self.message,
                surface.get_width() // 2,
                surface.get_height() - 120,
            )


class StoreState(State):
    name = "StoreState"

    def __init__(self) -> None:
        from scripts.collectableManager import CollectableManager
        from scripts.displayManager import DisplayManager
        from scripts.settings import settings
        from scripts.ui import UI

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.cm = CollectableManager(None)
        self.options_raw = list(self.cm.ITEMS.keys())
        # Build formatted options with aligned prices
        max_len = max(len(o) for o in self.options_raw)
        self.options = [f"{o.ljust(max_len)}  ${self.cm.ITEMS[o]:<6}" for o in self.options_raw]
        self.widget = ScrollableListWidget(self.options, visible_rows=5, spacing=50, font_size=30)
        self.message: str | None = None
        self.message_timer = 0.0
        self.request_back = False
        self.enter = False

    def handle_actions(self, actions: Sequence[str]) -> None:
        for a in actions:
            if a == "menu_up":
                self.widget.move_up()
            elif a == "menu_down":
                self.widget.move_down()
            elif a == "menu_select":
                self.enter = True
            elif a in ("menu_back", "menu_quit"):
                self.request_back = True

    def update(self, dt: float) -> None:
        if self.enter:
            opt = self.options[self.widget.selected_index]
            name = opt.split("$")[0].strip()
            result = self.cm.buy_collectable(name)
            if result == "success":
                self.message = f"Bought {name} for ${self.cm.ITEMS[name]}"
            elif result == "not enough coins":
                self.message = "Not enough coins!"
            elif result == "not purchaseable":
                self.message = "Item is not purchaseable!"
            else:
                self.message = result
            self.message_timer = 1.5
            self.enter = False
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, "Store", surface.get_width() // 2, 160)
        self.widget.render(surface, surface.get_width() // 2, 260)
        # Padlocks indicating purchaseable status
        for i in range(self.widget.visible_rows):
            idx = self.widget._scroll_offset + i
            if idx >= len(self.options_raw):
                break
            item_name = self.options_raw[idx]
            icon = "data/images/padlock-o.png" if self.cm.is_purchaseable(item_name) else "data/images/padlock-c.png"
            UI.render_ui_img(
                surface,
                icon,
                surface.get_width() // 2 + 350,
                260 + (i * self.widget.spacing),
                0.15,
            )
        # Coins + item amount of selected
        sel_name = self.options_raw[self.widget.selected_index]
        UI.render_menu_ui_element(surface, f"${self.cm.coins}", 20, 20)
        UI.render_menu_ui_element(
            surface,
            f"{sel_name}: {self.cm.get_amount(sel_name)}",
            surface.get_width() - 20,
            20,
            "right",
        )
        UI.render_menu_ui_element(surface, "ESC to menu", 20, surface.get_height() - 40)
        if self.message:
            UI.render_menu_msg(
                surface,
                self.message,
                surface.get_width() // 2,
                surface.get_height() - 120,
            )


class AccessoriesState(State):
    name = "AccessoriesState"

    def __init__(self) -> None:
        from scripts.collectableManager import CollectableManager
        from scripts.displayManager import DisplayManager
        from scripts.settings import settings
        from scripts.ui import UI

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.cm = CollectableManager(None)
        self.weapons = list(self.cm.WEAPONS)
        self.skins = list(self.cm.SKINS)
        self.weapon_widget = ScrollableListWidget([w for w in self.weapons], visible_rows=4, spacing=50, font_size=30)
        self.skin_widget = ScrollableListWidget([s for s in self.skins], visible_rows=4, spacing=50, font_size=30)
        self.active_panel = 0  # 0 weapons, 1 skins
        self.request_back = False
        self.enter = False
        self.message: str | None = None
        self.message_timer = 0.0

    def handle_actions(self, actions: Sequence[str]) -> None:
        for a in actions:
            if a == "menu_up":
                (self.weapon_widget if self.active_panel == 0 else self.skin_widget).move_up()
            elif a == "menu_down":
                (self.weapon_widget if self.active_panel == 0 else self.skin_widget).move_down()
            elif a == "menu_select":
                self.enter = True
            elif a in ("menu_back", "menu_quit"):
                self.request_back = True
            elif a == "accessories_switch":
                self.active_panel = (self.active_panel + 1) % 2

    def update(self, dt: float) -> None:
        if self.enter:
            if self.active_panel == 0:  # weapons
                idx = self.weapon_widget.selected_index
                name = self.weapons[idx]
                if self.cm.get_amount(name) > 0:
                    self.settings.selected_weapon = idx
                    self.message = f"Equipped {name}"
                else:
                    self.message = f"Locked {name}"
            else:
                idx = self.skin_widget.selected_index
                name = self.skins[idx]
                if self.cm.get_amount(name) > 0:
                    self.settings.selected_skin = idx
                    self.message = f"Equipped {name}"
                else:
                    self.message = f"Locked {name}"
            self.message_timer = 1.0
            self.enter = False
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, "Accessories", surface.get_width() // 2, 120)
        UI.render_menu_subtitle(surface, "Weapons", surface.get_width() // 2 - 350, 260)
        UI.render_menu_subtitle(surface, "Skins", surface.get_width() // 2 + 350, 260)
        # Render weapon list
        self.weapon_widget.render(surface, surface.get_width() // 2 - 350, 330)
        self.skin_widget.render(surface, surface.get_width() // 2 + 350, 330)
        # Padlocks for each visible item
        for i in range(self.weapon_widget.visible_rows):
            idx = self.weapon_widget._scroll_offset + i
            if idx >= len(self.weapons):
                break
            name = self.weapons[idx]
            icon = "data/images/padlock-o.png" if self.cm.is_purchaseable(name) else "data/images/padlock-c.png"
            UI.render_ui_img(
                surface,
                icon,
                surface.get_width() // 2 - 150,
                330 + (i * self.weapon_widget.spacing),
                0.15,
            )
        for i in range(self.skin_widget.visible_rows):
            idx = self.skin_widget._scroll_offset + i
            if idx >= len(self.skins):
                break
            name = self.skins[idx]
            icon = "data/images/padlock-o.png" if self.cm.is_purchaseable(name) else "data/images/padlock-c.png"
            UI.render_ui_img(
                surface,
                icon,
                surface.get_width() // 2 + 600,
                330 + (i * self.skin_widget.spacing),
                0.15,
            )
        UI.render_menu_ui_element(surface, f"Coins: ${self.cm.coins}", 20, 20)
        UI.render_menu_ui_element(surface, f"Weapon: {self.cm.WEAPONS[self.settings.selected_weapon]}", 20, 40)
        UI.render_menu_ui_element(surface, f"Skin: {self.cm.SKINS[self.settings.selected_skin]}", 20, 60)
        UI.render_menu_ui_element(
            surface,
            "TAB switch list",
            surface.get_width() // 2 - 90,
            surface.get_height() - 70,
        )
        UI.render_menu_ui_element(
            surface,
            "ESC back",
            surface.get_width() // 2 - 50,
            surface.get_height() - 40,
        )
        if self.message:
            UI.render_menu_msg(
                surface,
                self.message,
                surface.get_width() // 2,
                surface.get_height() - 120,
            )
        # Highlight active panel title
        highlight_rect = pygame.Surface((300, 40), pygame.SRCALPHA)
        highlight_rect.fill((255, 255, 255, 40))
        if self.active_panel == 0:
            surface.blit(highlight_rect, (surface.get_width() // 2 - 500, 250))
        else:
            surface.blit(highlight_rect, (surface.get_width() // 2 + 200, 250))


class OptionsState(State):
    name = "OptionsState"

    def __init__(self) -> None:
        from scripts.displayManager import DisplayManager
        from scripts.settings import settings
        from scripts.ui import UI

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.widget = ScrollableListWidget([], visible_rows=3, spacing=50, font_size=30)
        self.request_back = False
        self.enter = False

    def handle_actions(self, actions: Sequence[str]) -> None:
        for a in actions:
            if a == "menu_up":
                self.widget.move_up()
            elif a == "menu_down":
                self.widget.move_down()
            elif a in ("menu_back", "menu_quit"):
                self.request_back = True
            elif a == "options_left":
                if self.widget.selected_index == 0:
                    self.settings.music_volume = self.settings.music_volume - 0.1
                    pygame.mixer.music.set_volume(self.settings.music_volume)
                elif self.widget.selected_index == 1:
                    self.settings.sound_volume = self.settings.sound_volume - 0.1
                elif self.widget.selected_index == 2:
                    self.settings.show_perf_overlay = not self.settings.show_perf_overlay
                elif self.widget.selected_index == 3:
                    self.settings.ghost_enabled = not self.settings.ghost_enabled
            elif a == "options_right":
                if self.widget.selected_index == 0:
                    self.settings.music_volume = self.settings.music_volume + 0.1
                    pygame.mixer.music.set_volume(self.settings.music_volume)
                elif self.widget.selected_index == 1:
                    self.settings.sound_volume = self.settings.sound_volume + 0.1
                elif self.widget.selected_index == 2:
                    self.settings.show_perf_overlay = not self.settings.show_perf_overlay
                elif self.widget.selected_index == 3:
                    self.settings.ghost_enabled = not self.settings.ghost_enabled

    def update(self, dt: float) -> None:
        # Refresh options list each frame to reflect current values
        self.widget.options = [
            f"Music Volume: {int(self.settings.music_volume * 100):3d}%",
            f"Sound Volume: {int(self.settings.sound_volume * 100):3d}%",
            # f"Perf Overlay: {'ON ' if self.settings.show_perf_overlay else 'OFF'}",
            f"Ghosts: {'ON ' if self.settings.ghost_enabled else 'OFF'}",
        ]

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, "Options", surface.get_width() // 2, 160)
        self.widget.render(surface, surface.get_width() // 2, 260)
        UI.render_menu_ui_element(surface, "ESC back", 20, surface.get_height() - 40)
