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
    manager: "StateManager | None" = None

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
        state.manager = self
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
        state.manager = self
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
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
        self.dm = DisplayManager()
        self.BASE_W = self.dm.BASE_W
        self.BASE_H = self.dm.BASE_H
        self.display = pygame.Surface((self.BASE_W, self.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self.options_keys = [
            "menu.play",
            "menu.levels",
            "menu.store",
            "menu.accessories",
            "menu.options",
            "menu.quit",
        ]
        # Translate initially
        self.options = [self.loc.translate(k) for k in self.options_keys]

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
            # Map translated choice back to key or index?
            # Safer to use index since we control the list order
            idx = self.list_widget.selected_index
            key = self.options_keys[idx]

            if key == "menu.play":
                self.start_game = True
            elif key == "menu.quit":
                self.quit_requested = True
            elif key == "menu.levels":
                self.next_state = "Levels"
            elif key == "menu.store":
                self.next_state = "Store"
            elif key == "menu.accessories":
                self.next_state = "Accessories"
            elif key == "menu.options":
                self.next_state = "Options"
            # Future: branch to other submenus (Levels/Store/etc.) via state transitions
            self.enter = False

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("menu.title"), surface.get_width() // 2, 200)
        self.list_widget.render(surface, surface.get_width() // 2, 300)
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("menu.enter_hint")
            + " / "
            + self.loc.translate("menu.quit"),  # Hacky concat or add combined key
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
        self.level_complete_capture = None  # Store clean snapshot for level end
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
                # Issue 53: Per-level music tracks
                track = "data/music/music_0.wav"
                if hasattr(self._game, "tilemap") and hasattr(self._game.tilemap, "meta_data"):
                    track = self._game.tilemap.meta_data.get("music", track)

                self._game.audio.play_music(track, loops=-1)
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
                replay.recording = None  # Abort on exit without finish
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
        # Update internal clock to track FPS (Issue 50)
        g.clock.tick()

        # Update Audio Service (Ducking)
        g.audio.update()

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

        if g.endpoint:
            g.transition += 1
            if g.transition > TRANSITION_MAX:
                # Level advance logic
                old_best_val = g.timer.update_best_time()
                is_new_best = old_best_val is not None

                if replay_mgr:
                    replay_mgr.commit_run(new_best=is_new_best)

                # Identify next level
                levels = list_levels()
                try:
                    current_level_index = levels.index(g.level)
                except ValueError:
                    current_level_index = 0

                next_level = None
                if current_level_index < len(levels) - 1:
                    next_level = levels[current_level_index + 1]
                    # Unlock next level
                    from scripts.progress_tracker import get_progress_tracker

                    get_progress_tracker().unlock(next_level)
                    # settings.set_level_to_playable(next_level) # handled by tracker now

                # Transition to Level Complete State
                if self.manager:
                    old_best_str = g.timer.format_time(old_best_val) if is_new_best else None
                    self.manager.set(
                        LevelCompleteState(
                            current_level=g.level,
                            next_level=next_level,
                            time_str=g.timer.text,
                            best_time_str=g.timer.best_time_text,
                            new_best=is_new_best,
                            old_best_str=old_best_str,
                        )
                    )

        if g.transition < 0:
            g.transition += 1

        # --- Camera Update ---
        # Moved from Renderer.render to ensure it pauses (Issue 47)
        if hasattr(g, "player") and g.player:
            g.scroll[0] += (g.player.rect().centerx - g.display.get_width() / 2 - g.scroll[0]) / 30
            g.scroll[1] += (g.player.rect().centery - g.display.get_height() / 2 - g.scroll[1]) / 30

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

        # --- Entities & World Update (Moved from UI.render_game_elements) ---
        # Clouds
        if hasattr(g, "clouds"):
            g.clouds.update()

        # Enemies
        for enemy in g.enemies.copy():
            kill = enemy.update(g.tilemap, (0, 0))
            if kill:
                g.enemies.remove(enemy)

        # Players
        if not g.dead:
            for player in g.players:
                if player.id == g.playerID:
                    # Movement driven by legacy input flags
                    player.update(g.tilemap, (g.movement[1] - g.movement[0], 0))
                    replay_mgr = getattr(g, "replay", None)
                    if replay_mgr is not None:
                        try:
                            replay_mgr.capture_player(player)
                        except Exception:
                            pass
                else:
                    player.update(g.tilemap, (0, 0))

        # Particles / Sparks
        if hasattr(g, "particle_system"):
            g.particle_system.update()
        else:
            # Legacy path
            for spark in g.sparks.copy():
                kill = spark.update()
                if kill:
                    g.sparks.remove(spark)

        # Collectables
        if hasattr(g, "cm") and hasattr(g, "player"):
            g.cm.update(g.player.rect())

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
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
        self._ticks = 0
        self.closed = False
        self.return_to_menu = False
        self.quit_requested = False
        self._underlying: State | None = None  # set in on_enter
        self.options_keys = [
            "menu.resume",
            "menu.menu",
        ]  # 'Menu' reused? "menu.menu" -> "Menu" (implied context) or "level_complete.menu"?
        # Let's use "level_complete.menu" for "Menu" button
        self.options_keys = ["menu.resume", "level_complete.menu"]

        self.widget = ScrollableListWidget(
            [self.loc.translate(k) for k in self.options_keys], visible_rows=3, spacing=60, font_size=30
        )
        self.bg: pygame.Surface | None = None
        # Background image (menu backdrop) for pause overlay decoration
        try:
            self.bg = pygame.image.load("data/images/background-big.png")
        except Exception:  # pragma: no cover - asset optional in tests
            pass

    def on_enter(self, previous: "State | None") -> None:  # capture underlying
        self._underlying = previous
        self.pause_start_ticks = pygame.time.get_ticks()

    def on_exit(self, next_state: "State | None") -> None:
        # Calculate pause duration and offset the game timer so elapsed time remains correct
        if hasattr(self, "pause_start_ticks") and self._underlying and hasattr(self._underlying, "game"):
            duration = pygame.time.get_ticks() - self.pause_start_ticks
            if hasattr(self._underlying.game, "timer"):
                self._underlying.game.timer.adjust_for_pause(duration)

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
                # Use index to match key logic
                idx = self.widget.selected_index
                key = self.options_keys[idx]
                if key == "menu.resume":
                    self.closed = True
                elif key == "level_complete.menu":
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
            text=self.loc.translate("menu.paused"),
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
            self.loc.translate("menu.enter_hint") + " / " + self.loc.translate("menu.resume"),
            surface.get_width() // 2 - 130,
            surface.get_height() - 60,
        )
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("menu.navigate_hint"),
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
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
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
                self.message = self.loc.translate("menu.selected", lvl)
            else:
                self.message = self.loc.translate("menu.locked")
            self.message_timer = 1.0  # seconds
            self.enter = False
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("menu.select_level"), surface.get_width() // 2, 160)
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
            f"{self.loc.translate('menu.current')}: {self.settings.selected_level}",
            20,
            20,
        )
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("menu.back_hint"),
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
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
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
                self.message = self.loc.translate("store.buy_success", name, self.cm.ITEMS[name])
            elif result == "not enough coins":
                self.message = self.loc.translate("store.not_enough")
            elif result == "not purchaseable":
                self.message = self.loc.translate("store.not_purchaseable")
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
        UI.render_menu_title(surface, self.loc.translate("store.title"), surface.get_width() // 2, 160)
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
        UI.render_menu_ui_element(surface, self.loc.translate("menu.back_hint"), 20, surface.get_height() - 40)
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
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.cm = CollectableManager(None)
        self.weapons = list(self.cm.WEAPONS)
        self.skins = list(self.cm.SKINS)
        self.weapon_widget = ScrollableListWidget(self.weapons, visible_rows=4, spacing=50, font_size=30)
        self.skin_widget = ScrollableListWidget(self.skins, visible_rows=4, spacing=50, font_size=30)
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
                    self.message = self.loc.translate("accessories.equipped", name)
                else:
                    self.message = self.loc.translate("accessories.locked", name)
            else:
                idx = self.skin_widget.selected_index
                name = self.skins[idx]
                if self.cm.get_amount(name) > 0:
                    self.settings.selected_skin = idx
                    self.message = self.loc.translate("accessories.equipped", name)
                else:
                    self.message = self.loc.translate("accessories.locked", name)
            self.message_timer = 1.0
            self.enter = False
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("accessories.title"), surface.get_width() // 2, 120)
        UI.render_menu_subtitle(surface, self.loc.translate("accessories.weapons"), surface.get_width() // 2 - 350, 260)
        UI.render_menu_subtitle(surface, self.loc.translate("accessories.skins"), surface.get_width() // 2 + 350, 260)
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
        UI.render_menu_ui_element(surface, self.loc.translate("accessories.coins", self.cm.coins), 20, 20)
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("accessories.equipped_weapon", self.cm.WEAPONS[self.settings.selected_weapon]),
            20,
            40,
        )
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("accessories.equipped_skin", self.cm.SKINS[self.settings.selected_skin]),
            20,
            60,
        )
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("accessories.tab_hint"),
            surface.get_width() // 2 - 90,
            surface.get_height() - 70,
        )
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("menu.back_hint"),
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
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.widget = ScrollableListWidget([], visible_rows=4, spacing=50, font_size=30)
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
            elif a == "options_left" or a == "options_right":
                # Cycle or toggle
                idx = self.widget.selected_index
                if idx == 0:
                    change = -0.1 if a == "options_left" else 0.1
                    self.settings.music_volume += change
                    pygame.mixer.music.set_volume(self.settings.music_volume)
                elif idx == 1:
                    change = -0.1 if a == "options_left" else 0.1
                    self.settings.sound_volume += change
                elif idx == 2:
                    self.settings.ghost_enabled = not self.settings.ghost_enabled
                elif idx == 3:
                    # Toggle mode
                    current = self.settings.ghost_mode
                    self.settings.ghost_mode = "last" if current == "best" else "best"

    def update(self, dt: float) -> None:
        # Refresh options list each frame to reflect current values
        ghosts_status = (
            self.loc.translate("options.on") if self.settings.ghost_enabled else self.loc.translate("options.off")
        )
        self.widget.options = [
            self.loc.translate("options.music_volume", int(self.settings.music_volume * 100)),
            self.loc.translate("options.sound_volume", int(self.settings.sound_volume * 100)),
            self.loc.translate("options.ghosts", ghosts_status),
            self.loc.translate("options.ghost_mode", self.settings.ghost_mode.upper()),
        ]

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("options.title"), surface.get_width() // 2, 160)
        self.widget.render(surface, surface.get_width() // 2, 260)
        UI.render_menu_ui_element(surface, self.loc.translate("menu.back_hint"), 20, surface.get_height() - 40)


class LevelCompleteState(State):
    name = "LevelCompleteState"

    def __init__(self, current_level, next_level, time_str, best_time_str, new_best=False, old_best_str=None):
        from scripts.ui_widgets import ScrollableListWidget
        from scripts.displayManager import DisplayManager
        from scripts.ui import UI
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
        self.current_level = current_level
        self.next_level = next_level
        self.time_str = time_str
        self.best_time_str = best_time_str
        self.new_best = new_best
        self.old_best_str = old_best_str
        self.bg = None
        try:
            self.bg = pygame.image.load("data/images/background-big.png")
        except Exception:
            pass

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self._ui = UI

        # Options
        self.options_keys = []
        if self.next_level:
            self.options_keys.append("level_complete.next_level")
        self.options_keys.append("level_complete.replay")
        self.options_keys.append("level_complete.menu")

        self.widget = ScrollableListWidget(
            [self.loc.translate(k) for k in self.options_keys], visible_rows=3, spacing=50, font_size=30
        )
        self.enter = False

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act == "menu_up":
                self.widget.move_up()
            elif act == "menu_down":
                self.widget.move_down()
            elif act == "menu_select":
                self.enter = True

    def update(self, dt: float) -> None:
        if self.enter:
            idx = self.widget.selected_index
            choice_key = self.options_keys[idx]
            if choice_key == "level_complete.next_level":
                if self.manager:
                    from scripts.settings import settings

                    settings.selected_level = self.next_level
                    self.manager.set(GameState())
            elif choice_key == "level_complete.replay":
                if self.manager:
                    from scripts.settings import settings

                    settings.selected_level = self.current_level
                    self.manager.set(GameState())
            elif choice_key == "level_complete.menu":
                if self.manager:
                    self.manager.set(MenuState())
            self.enter = False

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        # Background
        if self.bg:
            try:
                bg_scaled = pygame.transform.scale(self.bg, surface.get_size())
                surface.blit(bg_scaled, (0, 0))
            except Exception:
                surface.fill((0, 0, 0))
        else:
            surface.fill((0, 0, 0))

        # Title
        UI.render_menu_title(surface, self.loc.translate("level_complete.title"), surface.get_width() // 2, 80)

        # Stats
        y_start = 320
        color = "#FFD700" if self.new_best else UI.GAME_UI_COLOR

        UI.render_menu_msg(
            surface,
            self.loc.translate("level_complete.time", self.time_str),
            surface.get_width() // 2,
            y_start,
            color=color,
        )

        if self.new_best:
            UI.render_menu_msg(
                surface,
                self.loc.translate("level_complete.new_best"),
                surface.get_width() // 2,
                y_start - 80,
                color="#FFD700",
            )
            UI.render_menu_msg(
                surface,
                self.loc.translate("level_complete.old_best", self.old_best_str),
                surface.get_width() // 2,
                y_start + 40,
                color=color,
            )
        else:
            UI.render_menu_msg(
                surface,
                self.loc.translate("level_complete.best", self.best_time_str),
                surface.get_width() // 2,
                y_start + 40,
                color=color,
            )

        # Widget
        self.widget.render(surface, surface.get_width() // 2, 420)

        # Hints
        UI.render_menu_ui_element(surface, self.loc.translate("menu.enter_hint"), 20, surface.get_height() - 40)
