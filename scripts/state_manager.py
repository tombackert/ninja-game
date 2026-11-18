"""State management foundation (Issue 10).

This module introduces a minimal stack based state manager used to drive
high-level application states (Menu, Game, Pause, Store, etc.). Each state
handles events and updates and renders itself; `app.py` runs the loop.

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
from scripts.ui_widgets import BackButton, PointerRouter, ScrollableListWidget

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

    # Mouse (see ui_widgets.PointerRouter) --------------------------
    def pointer_widgets(self) -> Sequence[ScrollableListWidget]:
        """The lists the mouse can point at; none by default."""
        return ()

    def pointer_select(self, widget: ScrollableListWidget, index: int) -> None:
        """The pointer is on row `index` of `widget` (hover or press)."""
        widget.select(index)

    def pointer_activate(self, widget: ScrollableListWidget, button: int) -> None:
        """A row of `widget` was clicked (it is already selected); the left button confirms it."""
        if button == 1:
            self.handle_actions(["menu_select"])

    def pointer_scroll(self, widget: ScrollableListWidget, steps: int) -> None:
        """The wheel turned `steps` rows (positive = down) over or beside `widget`."""
        widget.step(steps)

    # A submenu's clickable "back" (bottom left); None where Esc does not go back
    back: BackButton | None = None

    def pointer_back(self) -> None:
        """The back button or the mouse's thumb back button: same as Esc."""
        if self.back is not None:
            self.handle_actions(["menu_quit"])


class StateManager:
    """Stack-based state manager.

    Provides push/pop semantics and a `set` convenience to replace the
    current stack with a single state. Only the top state receives loop
    callbacks. This design allows overlay states (Pause) to be pushed on
    top of an active game state without discarding it.
    """

    def __init__(self) -> None:
        self._stack: List[State] = []
        self.pointer = PointerRouter()
        self._pointer_state: State | None = None  # the state the pointer last worked on
        _state_log.debug("StateManager init (empty stack)")

    # Introspection -------------------------------------------------
    @property
    def current(self) -> State | None:
        return self._stack[-1] if self._stack else None

    def stack_size(self) -> int:
        return len(self._stack)

    def find(self, state_type: type) -> State | None:
        """Topmost state on the stack of the given type (None if absent)."""
        for state in reversed(self._stack):
            if isinstance(state, state_type):
                return state
        return None

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
            if self.current is not self._pointer_state:
                self._pointer_state = self.current
                self.pointer.reset()
            self.pointer.process(self.current, events)
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
            "menu.multiplayer",
            "menu.levels",
            "menu.store",
            "menu.accessories",
            "menu.options",
            "menu.quit",
        ]
        # Translate initially
        self.options = [self.loc.translate(k) for k in self.options_keys]

        self.list_widget = ScrollableListWidget(self.options, visible_rows=7, spacing=50, font_size=30)
        self.selected = 0  # legacy compatibility (to be removed)
        self.enter = False
        self.quit_requested = False
        self.start_game = False
        self.next_state: str | None = None  # for submenu transitions
        self._ui = UI

    def pointer_widgets(self):
        return (self.list_widget,)

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
            elif key == "menu.multiplayer":
                self.next_state = "Multiplayer"
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


def opaque_surface(size: tuple[int, int]) -> pygame.Surface:
    """A buffer without an alpha channel, for composing a screen's backdrop.

    A plain `pygame.Surface(size)` takes the window's format, which on macOS
    is ARGB: blending a translucent overlay onto it leaves the alpha below
    255, and outlined text blitted over such pixels shows its whole box
    (the window ignores the alpha). 24 bits have no alpha to lose.
    """
    return pygame.Surface(size, 0, 24)


def fresh_game_state(level) -> "GameState":
    """A new run of `level` from its start, with full lives and a fresh timer.

    A named map (str, app.py --map) is loaded by name; a campaign level is
    selected in the settings first, as the menu's Play does.
    """
    if isinstance(level, str):
        return GameState(level=level)
    from scripts.settings import settings

    settings.selected_level = level
    return GameState()


class GameState(State):
    name = "GameState"

    def __init__(self, level=None) -> None:
        from game import Game

        # Underlying Game object (entities, systems, assets)
        self._game = Game(fullscreen=False)
        if level is not None:
            # A map outside the campaign, by name (data/maps/<name>.json; app.py --map):
            # the menu and the settings only know numbered levels
            self._game.level = level
            self._game.load_level(level)
        # Death log (scripts/death_log.py): only when app.main() switched it on
        from scripts import death_log

        log = death_log.current()
        if log is not None:
            log.bind(self._game)
        # Allow renderer to query state flags (performance HUD toggle) without tight coupling
        try:
            setattr(self._game, "state_ref", self)
        except Exception:
            pass
        self.level_complete_capture = None  # Store clean snapshot for level end
        self._accum = 0.0  # placeholder for future fixed timestep accumulator
        self._initialized_audio = False
        self.request_pause = False
        self.game_over = False  # the last life is gone: GameOverState took over
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
            from scripts import death_log

            # (a game over already ended the attempt with its death line)
            if not self._game.endpoint and not self.game_over:
                death_log.record_quit(self._game)
        except Exception:  # pragma: no cover - logging never blocks leaving
            pass
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

        Level flow, camera and death/respawn, then one `Game.step()`.
        Visual layering & HUD composition live in `Renderer`.
        """
        g = self._game
        # Update internal clock to track FPS (Issue 50)
        g.clock.tick()

        # Update Audio Service (Ducking)
        g.audio.update()

        # If a PauseState render is freezing this frame, skip simulation changes.
        if getattr(g, "_paused_freeze", False):
            return

        replay_mgr = getattr(g, "replay", None)

        # --- Core time & housekeeping ---
        g.timer.update(g.level)

        # --- Level completion (endpoint is set by Game.step's flag check) ---
        from scripts import death_log
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
                death_log.record_clear(g)

                # Identify next level
                levels = list_levels()
                try:
                    current_level_index = levels.index(g.level)
                except ValueError:
                    current_level_index = 0

                next_level = None
                if g.level not in levels:
                    pass  # a named map outside the campaign: nothing comes after it, nothing unlocks
                elif current_level_index < len(levels) - 1:
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
            g.update_camera()

        # --- Death / respawn handling ---
        # Every death ends here, so the death log writes its line here, once
        # per death; the places where a death starts only name the cause.
        # (Note: legacy attribute 'lifes' renamed to 'lives' internally; we access both defensively.)
        player_lives_attr = getattr(g.player, "lives", getattr(g.player, "lifes", 0))
        if player_lives_attr < 1:
            g.dead += 1
            death_log.set_cause(g, "out_of_lives")  # unless R or a fall named one first
        if g.dead:
            g.dead += 1
            if g.dead >= DEAD_ANIM_FADE_START:
                g.transition = min(TRANSITION_MAX, g.transition + 1)
            if g.dead > RESPAWN_DEAD_THRESHOLD and player_lives_attr >= 1:
                # (load_level starts the replay recording over: nothing to abort here)
                death_log.record_death(g, restart=False)
                g.load_level(g.level, player_lives_attr, respawn=True)
            if g.dead > RESPAWN_DEAD_THRESHOLD and player_lives_attr < 1:
                death_log.record_death(g, restart=True)
                if self.manager:
                    self.game_over = True
                    self.manager.set(GameOverState(level=g.level))
                    return
                # Without a state manager (tests, headless drivers) the level starts over
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

        # --- World simulation (shared with TrainingEnv and prediction) ---
        g.step()

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
        from scripts.localization import LocalizationService

        self.loc = LocalizationService.get()
        self._ticks = 0
        self.closed = False
        self.return_to_menu = False
        self.restart_requested = False  # app.py starts the level over (fresh_game_state)
        self.quit_requested = False
        self._underlying: State | None = None  # set in on_enter
        self._set_options(["menu.resume", "menu.restart", "level_complete.menu"])
        self.bg: pygame.Surface | None = None
        # Background image (menu backdrop) for pause overlay decoration
        try:
            self.bg = pygame.image.load("data/images/background-big.png")
        except Exception:  # pragma: no cover - asset optional in tests
            pass
        # Darkening overlay and faded menu background, built once per size
        self._veil: tuple[pygame.Surface, pygame.Surface | None] | None = None
        # The darkened game frame. A paused single-player game does not
        # change, so it is composed once instead of re-rendered every frame.
        self._backdrop: pygame.Surface | None = None

    def _set_options(self, keys: list[str]) -> None:
        from scripts.ui_widgets import ScrollableListWidget

        self.options_keys = keys
        self.widget = ScrollableListWidget(
            [self.loc.translate(k) for k in keys], visible_rows=3, spacing=60, font_size=30
        )

    @property
    def can_restart(self) -> bool:
        """Only a single-player level can start over (a multiplayer world is shared)."""
        return self._underlying is None or isinstance(self._underlying, GameState)

    def on_enter(self, previous: "State | None") -> None:  # capture underlying
        self._underlying = previous
        self.pause_start_ticks = pygame.time.get_ticks()
        if not self.can_restart:
            self._set_options([k for k in self.options_keys if k != "menu.restart"])

    def on_exit(self, next_state: "State | None") -> None:
        # Calculate pause duration and offset the game timer so elapsed time remains correct
        if hasattr(self, "pause_start_ticks") and self._underlying and hasattr(self._underlying, "game"):
            duration = pygame.time.get_ticks() - self.pause_start_ticks
            if hasattr(self._underlying.game, "timer"):
                self._underlying.game.timer.adjust_for_pause(duration)

    def pointer_widgets(self):
        return (self.widget,)

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
            elif act == "pause_restart" and self.can_restart:  # R
                self.restart_requested = True
                self.closed = True
            elif act == "menu_select":
                # Use index to match key logic
                idx = self.widget.selected_index
                key = self.options_keys[idx]
                if key == "menu.resume":
                    self.closed = True
                elif key == "menu.restart":
                    self.restart_requested = True
                    self.closed = True
                elif key == "level_complete.menu":
                    self.return_to_menu = True
                    self.closed = True

    def update(self, dt: float) -> None:
        self._ticks += 1
        # Keep network connections alive while paused (multiplayer): the
        # underlying state is frozen, but heartbeats/snapshots must continue
        # or the server drops the client after its timeout.
        if self._underlying and hasattr(self._underlying, "network_idle_update"):
            self._underlying.network_idle_update()

    def render(self, surface: pygame.Surface) -> None:
        # Multiplayer keeps its world running underneath: redraw it every frame
        live = hasattr(self._underlying, "network_idle_update")
        if self._backdrop is None or self._backdrop.get_size() != surface.get_size():
            # Composed in an opaque buffer: on the window surface (per-pixel
            # alpha 0 on macOS) the overlay would replace the game picture
            # instead of darkening it
            self._backdrop = pygame.Surface(surface.get_size())
            self._render_backdrop(self._backdrop)
        elif live:
            self._render_backdrop(self._backdrop)
        else:
            # The game is not drawn, but a frame is shown: keep the perf HUD's
            # frame intervals continuous (resuming is measured from here)
            renderer = getattr(self._underlying, "_renderer", None)
            if renderer is not None:
                renderer.perf_hud.note_frame()
        surface.blit(self._backdrop, (0, 0))
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

    def _render_backdrop(self, surface: pygame.Surface) -> None:
        """The underlying game frame, darkened, with the menu background faintly on top."""
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
        size = surface.get_size()
        if self._veil is None or self._veil[0].get_size() != size:
            # Semi-transparent overlay
            overlay = pygame.Surface(size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))  # semi-transparent darkening
            # Optional faint menu background blended in
            bg_scaled = None
            if self.bg:
                try:
                    bg_scaled = pygame.transform.scale(self.bg, size)
                    bg_scaled.set_alpha(60)
                except Exception:  # pragma: no cover
                    bg_scaled = None
            self._veil = (overlay, bg_scaled)
        overlay, bg_scaled = self._veil
        surface.blit(overlay, (0, 0))
        if bg_scaled:
            surface.blit(bg_scaled, (0, 0))


# ---------------- Additional Menu Sub-States (Issue 12) -----------------


class LevelsState(State):
    """Level select: the level names on the left, the selected level's
    preview, chapter, setting and best time on the right.

    A locked level's preview is pixelated and dimmed under a padlock: the
    colours tell the world, the level itself stays a surprise.
    """

    name = "LevelsState"

    VISIBLE_ROWS = 9
    ROW_SPACING = 52
    THUMB_SCALE = 2  # thumbnails are 320x180 game pixels -> 640x360 on the 1280x720 menu

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
        from scripts.level_info import level_name

        self.widget = ScrollableListWidget(
            [level_name(lvl) for lvl in self.levels],
            visible_rows=self.VISIBLE_ROWS,
            spacing=self.ROW_SPACING,
            font_size=24,
        )
        self.widget.selected_index = self.index
        self.widget._ensure_visible()
        self.best_times = self._load_best_times()
        self._thumbs: dict = {}  # (level, locked) -> scaled preview surface
        self.message: str | None = None
        self.message_timer: float = 0.0
        self.back: BackButton = BackButton(self.loc.translate("menu.back"))
        self.request_back = False
        self.enter = False

    @staticmethod
    def _load_best_times() -> dict:
        import json

        from scripts.timer import BEST_TIMES_FILE

        try:
            with open(BEST_TIMES_FILE) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        times = {}
        for key, val in data.items():
            t = val.get("time") if isinstance(val, dict) else val
            if isinstance(t, (int, float)):
                times[key] = t
        return times

    def _best_time_text(self, level) -> str:
        t = self.best_times.get(str(level))
        if t is None:
            return "--:--.--"
        t = int(t)
        return f"{t // 60000 % 60:02}:{t // 1000 % 60:02}.{t % 1000 // 10:02}"

    def _thumbnail(self, level, locked: bool, size: tuple[int, int]) -> pygame.Surface:
        key = (level, locked, size)
        if key not in self._thumbs:
            from scripts.level_info import thumbnail_path

            path = thumbnail_path(level)
            surf = pygame.Surface(size)
            if path is None:
                surf.fill((24, 26, 44))
            else:
                img = pygame.image.load(path)
                if locked:  # only the colours of the world show through
                    img = pygame.transform.scale(img, (img.get_width() // 10, img.get_height() // 10))
                surf = pygame.transform.scale(img, size)
                if locked:
                    surf.fill((90, 90, 110), special_flags=pygame.BLEND_RGB_MULT)
            self._thumbs[key] = surf
        return self._thumbs[key]

    def pointer_widgets(self):
        return (self.widget,)

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
            from scripts.level_info import level_name

            lvl = self.levels[self.widget.selected_index]
            # Use tracker authoritative unlock state
            if self.progress.is_unlocked(lvl):
                self.settings.selected_level = lvl
                self.message = self.loc.translate("menu.selected", level_name(lvl))
            else:
                self.message = self.loc.translate("menu.locked")
            self.message_timer = 1.0  # seconds
            self.enter = False
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def render(self, surface: pygame.Surface) -> None:
        from scripts.level_info import level_info, level_name

        UI = self._ui
        W, H = surface.get_size()
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("menu.select_level"), W // 2, 60)

        # Level list (left): padlock, name; the selection in the highlight colour
        font = UI.get_font(self.widget.font_size)
        list_x, list_y = int(W * 0.03), 150
        self.widget.clear_hit_rects()
        for i in range(self.widget.visible_rows):
            idx = self.widget._scroll_offset + i
            if idx >= len(self.levels):
                break
            lvl = self.levels[idx]
            y = list_y + i * self.widget.spacing
            unlocked = self.progress.is_unlocked(lvl)
            icon = "data/images/padlock-o.png" if unlocked else "data/images/padlock-c.png"
            UI.render_ui_img(surface, icon, list_x + 14, y, 0.14)
            if idx == self.widget.selected_index:
                color = UI.SELECTOR_COLOR
            else:
                color = UI.PM_COLOR if unlocked else "#5A6B80"
            text_y = y - font.get_height() // 2
            text_rect = UI.draw_text_with_outline(
                surface, font, self.widget.options[idx], list_x + 40, text_y, color, scale=3
            )
            # The padlock belongs to the row too
            self.widget.record_row(idx, text_rect.union(pygame.Rect(list_x, text_rect.top, 1, text_rect.height)))
        # scroll hints
        if self.widget._scroll_offset > 0:
            UI.render_menu_ui_element(surface, "...", list_x + 40, list_y - 50)
        if self.widget._scroll_offset + self.widget.visible_rows < len(self.levels):
            last_y = list_y + self.widget.visible_rows * self.widget.spacing
            UI.render_menu_ui_element(surface, "...", list_x + 40, last_y - 30)

        # Preview (right)
        if self.levels:
            lvl = self.levels[self.widget.selected_index]
            info = level_info(lvl)
            unlocked = self.progress.is_unlocked(lvl)
            tw, th = 320 * self.THUMB_SCALE * W // 1280, 180 * self.THUMB_SCALE * H // 720
            tx, ty = W - tw - int(W * 0.02), 120
            frame = pygame.Rect(tx - 4, ty - 4, tw + 8, th + 8)
            pygame.draw.rect(surface, (22, 24, 48), frame)
            pygame.draw.rect(surface, UI.SELECTOR_COLOR if unlocked else "#5A6B80", frame, 3)
            surface.blit(self._thumbnail(lvl, not unlocked, (tw, th)), (tx, ty))
            if not unlocked:
                UI.render_ui_img(surface, "data/images/padlock-c.png", tx + tw // 2, ty + th // 2, 0.5)
            cx = tx + tw // 2
            y = ty + th + 30
            if info.chapter:
                chapter = f"Chapter {info.chapter}: {info.chapter_name}"
                UI.draw_text_with_outline(surface, UI.get_font(15), chapter, cx, y, UI.PM_COLOR, center=True, scale=2)
                y += 30
            if info.setting:
                for line in self._wrap(info.setting, UI.get_font(15), tw):
                    UI.draw_text_with_outline(
                        surface, UI.get_font(15), line, cx, y, UI.GAME_UI_COLOR, center=True, scale=2
                    )
                    y += 24
            best = f"{self.loc.translate('level_complete.best', self._best_time_text(lvl))}"
            UI.draw_text_with_outline(surface, UI.get_font(15), best, cx, y + 8, UI.PM_COLOR, center=True, scale=2)

        UI.render_menu_ui_element(
            surface,
            f"{self.loc.translate('menu.current')}: {level_name(self.settings.selected_level)}",
            20,
            20,
        )
        self.back.render(surface)
        if self.message:
            UI.render_menu_msg(surface, self.message, W // 2, H - 60)

    @staticmethod
    def _wrap(text: str, font, width: int) -> list[str]:
        lines: list[str] = []
        for word in text.split():
            if lines and font.size(lines[-1] + " " + word)[0] <= width:
                lines[-1] += " " + word
            else:
                lines.append(word)
        return lines


class _ItemMenuState(State):
    """Store and accessories: a hub with the categories (weapons, gear,
    skins), each opening its own page laid out like the level select: the
    items on the left, the selected one's stage and details on the right.

    Esc / back leaves a category page for the hub, and the hub for the main
    menu. Subclasses list a category's items and say what ENTER does.
    """

    CATEGORIES = ("weapons", "gear", "skins")
    VISIBLE_ROWS = 8
    ROW_SPACING = 52
    STAGE_SCALE = 6  # stage of 96x56 game pixels -> 576x336
    LOCKED_COLOR = "#5A6B80"
    DIM_UNOWNED = False  # grey out what you don't own (only where it can't be used)
    title_key = ""

    def __init__(self) -> None:
        from scripts.collectableManager import CollectableManager
        from scripts.displayManager import DisplayManager
        from scripts.localization import LocalizationService
        from scripts.settings import settings
        from scripts.skin_preview import SkinPreview
        from scripts.ui import UI

        self.loc = LocalizationService.get()
        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.cm = CollectableManager(None)
        self.widget = ScrollableListWidget(
            [self.loc.translate(f"accessories.{c}") for c in self.CATEGORIES],
            visible_rows=len(self.CATEGORIES),
            spacing=90,
            font_size=30,
        )
        self.category: str | None = None  # None: the hub
        self.items: list[str] = []
        self.item_widget = ScrollableListWidget(
            [], visible_rows=self.VISIBLE_ROWS, spacing=self.ROW_SPACING, font_size=24
        )
        self.preview = SkinPreview()
        self.message: str | None = None
        self.message_timer = 0.0
        self.back: BackButton = BackButton(self.loc.translate("menu.back"))
        self.request_back = False
        self.enter = False

    # Subclass hooks ------------------------------------------------
    def items_of(self, category: str) -> list[str]:
        raise NotImplementedError

    def initial_index(self, category: str) -> int:
        return 0

    def activate(self, name: str) -> None:
        raise NotImplementedError

    def row_info(self, name: str) -> tuple[str, object]:
        """Text and colour at the right end of an item's row."""
        raise NotImplementedError

    def status(self, name: str) -> tuple[str, object]:
        """The selected item's status line (price, owned, equipped)."""
        raise NotImplementedError

    def hub_info(self, category: str) -> str:
        """Small line under a category on the hub."""
        raise NotImplementedError

    # Shared helpers ------------------------------------------------
    def owned(self, name: str) -> bool:
        return self.cm.get_amount(name) > 0

    def label(self, name: str) -> str:
        """Short name for the list; the card shows the full one."""
        return name

    def open_category(self, category: str) -> None:
        self.category = category
        self.items = self.items_of(category)
        self.item_widget.set_options([self.label(n) for n in self.items])
        self.item_widget.select(self.initial_index(category))

    def say(self, text: str, seconds: float = 1.5) -> None:
        self.message = text
        self.message_timer = seconds

    # State ---------------------------------------------------------
    def _active(self) -> ScrollableListWidget:
        return self.item_widget if self.category else self.widget

    def pointer_widgets(self):
        return (self._active(),)

    def handle_actions(self, actions: Sequence[str]) -> None:
        for a in actions:
            if a == "menu_up":
                self._active().move_up()
            elif a == "menu_down":
                self._active().move_down()
            elif a == "menu_select":
                self.enter = True
            elif a in ("menu_back", "menu_quit"):
                if self.category:
                    self.category = None
                    self.message = None
                else:
                    self.request_back = True

    def update(self, dt: float) -> None:
        self.preview.update(dt)
        if self.enter:
            self.enter = False
            if self.category is None:
                self.open_category(self.CATEGORIES[self.widget.selected_index])
            elif self.items:
                self.activate(self.items[self.item_widget.selected_index])
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        W, H = surface.get_size()
        UI.render_menu_bg(surface, self.display, self.bg)
        if self.category is None:
            self._render_hub(surface)
        else:
            self._render_page(surface)
        UI.render_menu_ui_element(surface, self.loc.translate("accessories.coins", self.cm.coins), 20, 20)
        self.back.render(surface)
        if self.message:
            UI.render_menu_msg(surface, self.message, W // 2, H - 60)

    def _render_hub(self, surface: pygame.Surface) -> None:
        UI = self._ui
        W, H = surface.get_size()
        UI.render_menu_title(surface, self.loc.translate(self.title_key), W // 2, 170)
        top = 300
        self.widget.render(surface, W // 2, top)
        font = UI.get_font(15)
        for i, category in enumerate(self.CATEGORIES):
            UI.draw_text_with_outline(
                surface,
                font,
                self.hub_info(category),
                W // 2,
                top + i * self.widget.spacing + 34,
                UI.GAME_UI_COLOR,
                center=True,
                scale=2,
            )
        UI.draw_text_with_outline(
            surface,
            UI.get_font(15),
            self.loc.translate("store.hub_hint"),
            W // 2,
            H - 32,
            UI.GAME_UI_COLOR,
            center=True,
            scale=2,
        )

    def _render_page(self, surface: pygame.Surface) -> None:
        UI = self._ui
        W, H = surface.get_size()
        UI.render_menu_title(surface, self.loc.translate(f"accessories.{self.category}"), W // 2, 60)

        # Items (left): padlock, name, and at the row's end its price or state
        font = UI.get_font(self.item_widget.font_size)
        info_font = UI.get_font(15)
        list_x, list_y, list_w = int(W * 0.03), 150, 560
        widget = self.item_widget
        widget.clear_hit_rects()
        for i in range(widget.visible_rows):
            idx = widget._scroll_offset + i
            if idx >= len(self.items):
                break
            name = self.items[idx]
            y = list_y + i * widget.spacing
            owned = self.owned(name)
            icon = "data/images/padlock-o.png" if owned else "data/images/padlock-c.png"
            UI.render_ui_img(surface, icon, list_x + 14, y, 0.14)
            selected = idx == widget.selected_index
            dim = self.DIM_UNOWNED and not owned
            color = UI.SELECTOR_COLOR if selected else (self.LOCKED_COLOR if dim else UI.PM_COLOR)
            text_rect = UI.draw_text_with_outline(
                surface, font, widget.options[idx], list_x + 40, y - font.get_height() // 2, color, scale=3
            )
            info, info_color = self.row_info(name)
            if info:
                surf_w = info_font.size(info)[0]
                UI.draw_text_with_outline(
                    surface,
                    info_font,
                    info,
                    list_x + list_w - surf_w,
                    y - info_font.get_height() // 2,
                    UI.SELECTOR_COLOR if selected else info_color,
                    scale=2,
                )
            row = text_rect.union(pygame.Rect(list_x, text_rect.top, list_w, text_rect.height))
            widget.record_row(idx, row)
        if widget._scroll_offset > 0:
            UI.render_menu_ui_element(surface, "...", list_x + 40, list_y - 50)
        if widget._scroll_offset + widget.visible_rows < len(self.items):
            UI.render_menu_ui_element(surface, "...", list_x + 40, list_y + widget.visible_rows * widget.spacing - 30)

        if not self.items:
            return
        name = self.items[widget.selected_index]
        self._render_card(surface, name)

    def _render_card(self, surface: pygame.Surface, name: str) -> None:
        """Stage in a frame like the level preview, details underneath."""
        from scripts.collectableManager import ITEM_DESCRIPTIONS, ITEM_ICONS
        from scripts.skin_preview import STAGE, wrap_text

        UI = self._ui
        W, H = surface.get_size()
        sw, sh = STAGE[0] * self.STAGE_SCALE, STAGE[1] * self.STAGE_SCALE
        sx, sy = W - sw - int(W * 0.04), 120
        owned = self.owned(name)
        frame = pygame.Rect(sx - 4, sy - 4, sw + 8, sh + 8)
        pygame.draw.rect(surface, (22, 24, 48), frame)
        pygame.draw.rect(surface, UI.SELECTOR_COLOR if owned else self.LOCKED_COLOR, frame, 3)

        skin = self.cm.SKIN_INFO.get(name)
        if skin is not None:
            self.preview.set_skin(skin.path)
            title, text, held = skin.title, skin.description, None
        else:
            # Weapons and gear: the equipped skin shows them off
            self.preview.set_skin(self.cm.SKIN_PATHS[self.settings.selected_skin], showcase=False)
            title, text = name, ITEM_DESCRIPTIONS.get(name, "")
            held = ITEM_ICONS.get(name) if self.category == "weapons" else None
        extra = self._stage_extra(name)
        self.preview.render_stage(surface, pygame.Rect(sx, sy, sw, sh), held=held, extra=extra)

        cx = sx + sw // 2
        y = sy + sh + 34
        UI.draw_text_with_outline(surface, UI.get_font(24), title, cx, y, UI.PM_COLOR, center=True, scale=3)
        y += 38
        status, color = self.status(name)
        UI.draw_text_with_outline(surface, UI.get_font(15), status, cx, y, color, center=True, scale=2)
        y += 32
        font = UI.get_font(15)
        for line in wrap_text(font, text, sw):
            UI.draw_text_with_outline(surface, font, line, cx, y, UI.GAME_UI_COLOR, center=True, scale=2)
            y += 24

    def _stage_extra(self, name: str):
        """Gear shown on the stage the way it looks in a level."""
        if name == "Shield":

            def bubble(stage, feet):
                # Player._render_shield_bubble around the hitbox center
                r = 13
                b = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(b, (120, 200, 255, 60), (r, r), r)
                pygame.draw.circle(b, (170, 220, 250, 150), (r, r), r, 1)
                stage.blit(b, (feet[0] - r, feet[1] - 8 - r))

            return bubble
        if name == "Coin Magnet":
            from scripts.skin_preview import _load_image

            def coins(stage, feet):
                coin = _load_image("collectables/coin/0.png")
                for dx, dy in ((-26, -24), (16, -28), (26, -12)):
                    stage.blit(coin, (feet[0] + dx, feet[1] + dy))

            return coins
        return None


class StoreState(_ItemMenuState):
    name = "StoreState"
    title_key = "store.title"

    def items_of(self, category: str) -> list[str]:
        kind = {"weapons": "weapon", "gear": "gear", "skins": "skin"}[category]
        return [n for n, idef in self.cm._ITEM_DEFS.items() if idef.category == kind]

    def stackable(self, name: str) -> bool:
        idef = self.cm.get_item_def(name)
        return idef is not None and idef.category != "skin" and idef.increment > 1 or name == "Shield"

    def row_info(self, name: str):
        UI = self._ui
        if self.owned(name) and not self.stackable(name):
            return self.loc.translate("store.owned"), UI.GAME_UI_COLOR
        return f"${self.cm.ITEMS[name]}", UI.PM_COLOR

    def status(self, name: str):
        UI = self._ui
        price = self.cm.ITEMS[name]
        if self.stackable(name):
            return self.loc.translate("store.stack_status", price, self.cm.get_amount(name)), UI.PM_COLOR
        if self.owned(name):
            return self.loc.translate("store.owned"), UI.GAME_UI_COLOR
        return self.loc.translate("store.buy_status", price), UI.SELECTOR_COLOR

    def hub_info(self, category: str) -> str:
        items = [n for n in self.items_of(category) if not self.stackable(n)]
        owned = sum(1 for n in items if self.owned(n))
        return self.loc.translate("store.owned_count", owned, len(items))

    def activate(self, name: str) -> None:
        title = self.cm.display_name(name)
        result = self.cm.buy_collectable(name)
        if result == "success":
            self.say(self.loc.translate("store.buy_success", title, self.cm.ITEMS[name]))
        elif result == "not enough coins":
            self.say(self.loc.translate("store.not_enough"))
        elif result == "not purchaseable":
            self.say(self.loc.translate("store.not_purchaseable"))
        elif result == "already owned":
            self.say(self.loc.translate("store.already_owned", title))
        else:
            self.say(result)


class AccessoriesState(_ItemMenuState):
    name = "AccessoriesState"
    title_key = "accessories.title"
    DIM_UNOWNED = True

    def _slots(self, category: str):
        """(names, settings attribute) of an equip slot."""
        return {
            "weapons": (self.cm.WEAPONS, "selected_weapon"),
            "gear": (self.cm.GEAR, "selected_gear"),
            "skins": (self.cm.SKINS, "selected_skin"),
        }[category]

    def items_of(self, category: str) -> list[str]:
        return list(self._slots(category)[0])

    def equipped(self, category: str) -> str:
        names, attr = self._slots(category)
        return names[getattr(self.settings, attr)]

    def initial_index(self, category: str) -> int:
        return getattr(self.settings, self._slots(category)[1])

    def row_info(self, name: str):
        if name == self.equipped(self.category):
            return self.loc.translate("accessories.status_equipped"), self._ui.GAME_UI_COLOR
        return "", None

    def status(self, name: str):
        UI = self._ui
        if name == self.equipped(self.category):
            return self.loc.translate("accessories.status_equipped"), UI.GAME_UI_COLOR
        if self.owned(name):
            return self.loc.translate("accessories.status_owned"), UI.SELECTOR_COLOR
        return self.loc.translate("accessories.status_locked", self.cm.ITEMS[name]), self.LOCKED_COLOR

    def hub_info(self, category: str) -> str:
        return self.cm.display_name(self.equipped(category))

    def activate(self, name: str) -> None:
        names, attr = self._slots(self.category)
        title = self.cm.display_name(name)
        if self.owned(name):
            setattr(self.settings, attr, names.index(name))
            self.say(self.loc.translate("accessories.equipped", title), 1.0)
        else:
            self.say(self.loc.translate("accessories.locked", title), 1.0)


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
        self.widget = ScrollableListWidget([], visible_rows=6, spacing=50, font_size=30)
        self.back: BackButton = BackButton(self.loc.translate("menu.back"))
        self.request_back = False
        self.enter = False

    def pointer_widgets(self):
        return (self.widget,)

    def pointer_activate(self, widget, button: int) -> None:
        """Left click steps the value forward, right click back (like the arrow keys)."""
        self.handle_actions(["options_right" if button == 1 else "options_left"])

    def handle_actions(self, actions: Sequence[str]) -> None:
        from scripts.settings import CAMERA_STYLES

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
                elif idx == 4:
                    step = -1 if a == "options_left" else 1
                    i = CAMERA_STYLES.index(self.settings.camera_style)
                    self.settings.camera_style = CAMERA_STYLES[(i + step) % len(CAMERA_STYLES)]
                elif idx == 5:
                    # app.py switches the window when the setting changes
                    self.settings.fullscreen = not self.settings.fullscreen

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
            self.loc.translate("options.camera", self.settings.camera_style.upper()),
            self.loc.translate(
                "options.fullscreen",
                self.loc.translate("options.on") if self.settings.fullscreen else self.loc.translate("options.off"),
            ),
        ]

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("options.title"), surface.get_width() // 2, 160)
        self.widget.render(surface, surface.get_width() // 2, 260)
        self.back.render(surface)


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

    def pointer_widgets(self):
        return (self.widget,)

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
                    self.manager.set(fresh_game_state(self.current_level))
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
        from scripts.level_info import level_name

        UI.render_menu_subtitle(surface, level_name(self.current_level), surface.get_width() // 2, 150)

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


class GameOverState(State):
    """Shown when the last life is gone: try the level again or go to the menu.

    Input is ignored for a moment after it appears, so a jump or a click
    from the last seconds of play does not pick an option by accident.
    """

    name = "GameOverState"
    INPUT_DELAY = 0.6  # seconds

    def __init__(self, level) -> None:
        from scripts.localization import LocalizationService
        from scripts.ui import UI

        self.loc = LocalizationService.get()
        self.level = level
        self._ui = UI
        self.options_keys = ["game_over.retry", "level_complete.menu"]
        self.widget = ScrollableListWidget(
            [self.loc.translate(k) for k in self.options_keys], visible_rows=2, spacing=50, font_size=30
        )
        self.bg: pygame.Surface | None = None
        try:
            self.bg = pygame.image.load("data/images/background-big.png")
        except Exception:  # pragma: no cover - asset optional in tests
            pass
        self._backdrop: pygame.Surface | None = None  # background + red veil, built once per size
        self._age = 0.0
        self.enter = False

    @property
    def accepts_input(self) -> bool:
        return self._age >= self.INPUT_DELAY

    def pointer_widgets(self):
        return (self.widget,)

    def handle_actions(self, actions: Sequence[str]) -> None:
        if not self.accepts_input:
            return
        for act in actions:
            if act == "menu_up":
                self.widget.move_up()
            elif act == "menu_down":
                self.widget.move_down()
            elif act == "menu_select":
                self.enter = True
            elif act in ("menu_quit", "menu_back"):
                self.widget.selected_index = self.options_keys.index("level_complete.menu")
                self.enter = True

    def update(self, dt: float) -> None:
        self._age += dt
        if not self.enter:
            return
        self.enter = False
        if self.manager is None:
            return
        if self.options_keys[self.widget.selected_index] == "game_over.retry":
            self.manager.set(fresh_game_state(self.level))
        else:
            self.manager.set(MenuState())

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        size = surface.get_size()
        if self._backdrop is None or self._backdrop.get_size() != size:
            self._backdrop = opaque_surface(size)
            if self.bg is not None:
                self._backdrop.blit(pygame.transform.scale(self.bg, size), (0, 0))
            veil = pygame.Surface(size, pygame.SRCALPHA)
            veil.fill((60, 0, 0, 170))
            self._backdrop.blit(veil, (0, 0))
        surface.blit(self._backdrop, (0, 0))

        from scripts.level_info import level_name

        cx = size[0] // 2
        UI.draw_text_with_outline(
            surface=surface,
            font=UI.get_font(50),
            text=self.loc.translate("game_over.title"),
            x=cx,
            y=140,
            text_color=(220, 40, 40),
            center=True,
            scale=3,
        )
        UI.render_menu_subtitle(surface, level_name(self.level), cx, 240)
        UI.render_menu_msg(surface, self.loc.translate("game_over.subtitle"), cx, 310)
        self.widget.render(surface, cx, 400)
        UI.render_menu_ui_element(surface, self.loc.translate("menu.enter_hint"), 20, size[1] - 40)
