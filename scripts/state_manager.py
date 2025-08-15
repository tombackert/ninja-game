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
from scripts.ui_widgets import ScrollableListWidget
from scripts.logger import get_logger

_state_log = get_logger("state")


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

    # New action-based hook (Issue 11). States migrating to InputRouter
    # should override this instead of `handle`.
    def handle_actions(self, actions: Sequence[str]) -> None:  # pragma: no cover
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
        self.list_widget = ScrollableListWidget(
            self.options, visible_rows=6, spacing=50, font_size=30
        )
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

        self._game = Game()
        self._accum = 0.0  # basic accumulator if we later add fixed timestep

    @property
    def game(self):  # convenience
        return self._game

    def handle_actions(self, actions: Sequence[str]) -> None:
        self.request_pause = False
        for act in actions:
            if act == "pause_toggle":
                self.request_pause = True

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
        # Delegate full frame composition to unified Renderer (Issue 14).
        from scripts.renderer import Renderer

        if not hasattr(self, "_renderer"):
            # Lazy construct; avoids cost during test discovery when GameState unused.
            self._renderer = Renderer()
        self._renderer.render(self._game, surface)


class PauseState(State):
    name = "PauseState"

    def __init__(self) -> None:
        self._ticks = 0
        self.closed = False
        self.return_to_menu = False
        self._underlying: State | None = None  # set in on_enter

    def on_enter(self, previous: "State | None") -> None:  # capture underlying
        self._underlying = previous

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act == "pause_close":
                self.closed = True
            elif act == "pause_menu":
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


# ---------------- Additional Menu Sub-States (Issue 12) -----------------


class LevelsState(State):
    name = "LevelsState"

    def __init__(self) -> None:
        from scripts.displayManager import DisplayManager
        from scripts.ui import UI
        from scripts.level_cache import list_levels
        from scripts.settings import settings

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.levels = list_levels()
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
        self.message_timer = 0
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
            if self.settings.is_level_playable(lvl):
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
            icon = (
                "data/images/padlock-o.png"
                if self.settings.is_level_playable(lvl)
                else "data/images/padlock-c.png"
            )
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
        from scripts.displayManager import DisplayManager
        from scripts.ui import UI
        from scripts.collectableManager import CollectableManager
        from scripts.settings import settings

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.cm = CollectableManager(None)
        self.options_raw = list(self.cm.ITEMS.keys())
        # Build formatted options with aligned prices
        max_len = max(len(o) for o in self.options_raw)
        self.options = [
            f"{o.ljust(max_len)}  ${self.cm.ITEMS[o]:<6}" for o in self.options_raw
        ]
        self.widget = ScrollableListWidget(
            self.options, visible_rows=5, spacing=50, font_size=30
        )
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
            icon = (
                "data/images/padlock-o.png"
                if self.cm.is_purchaseable(item_name)
                else "data/images/padlock-c.png"
            )
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
        from scripts.displayManager import DisplayManager
        from scripts.ui import UI
        from scripts.collectableManager import CollectableManager
        from scripts.settings import settings

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.cm = CollectableManager(None)
        self.weapons = list(self.cm.WEAPONS)
        self.skins = list(self.cm.SKINS)
        self.weapon_widget = ScrollableListWidget(
            [w for w in self.weapons], visible_rows=4, spacing=50, font_size=30
        )
        self.skin_widget = ScrollableListWidget(
            [s for s in self.skins], visible_rows=4, spacing=50, font_size=30
        )
        self.active_panel = 0  # 0 weapons, 1 skins
        self.request_back = False
        self.enter = False
        self.message: str | None = None
        self.message_timer = 0.0

    def handle_actions(self, actions: Sequence[str]) -> None:
        for a in actions:
            if a == "menu_up":
                (
                    self.weapon_widget if self.active_panel == 0 else self.skin_widget
                ).move_up()
            elif a == "menu_down":
                (
                    self.weapon_widget if self.active_panel == 0 else self.skin_widget
                ).move_down()
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
            icon = (
                "data/images/padlock-o.png"
                if self.cm.is_purchaseable(name)
                else "data/images/padlock-c.png"
            )
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
            icon = (
                "data/images/padlock-o.png"
                if self.cm.is_purchaseable(name)
                else "data/images/padlock-c.png"
            )
            UI.render_ui_img(
                surface,
                icon,
                surface.get_width() // 2 + 600,
                330 + (i * self.skin_widget.spacing),
                0.15,
            )
        UI.render_menu_ui_element(surface, f"Coins: ${self.cm.coins}", 20, 20)
        UI.render_menu_ui_element(
            surface, f"Weapon: {self.cm.WEAPONS[self.settings.selected_weapon]}", 20, 40
        )
        UI.render_menu_ui_element(
            surface, f"Skin: {self.cm.SKINS[self.settings.selected_skin]}", 20, 60
        )
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
        from scripts.ui import UI
        from scripts.settings import settings

        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self._ui = UI
        self.settings = settings
        self.widget = ScrollableListWidget([], visible_rows=2, spacing=50, font_size=30)
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
            elif a == "options_right":
                if self.widget.selected_index == 0:
                    self.settings.music_volume = self.settings.music_volume + 0.1
                    pygame.mixer.music.set_volume(self.settings.music_volume)
                elif self.widget.selected_index == 1:
                    self.settings.sound_volume = self.settings.sound_volume + 0.1

    def update(self, dt: float) -> None:
        # Refresh options list each frame to reflect current values
        self.widget.options = [
            f"Music Volume: {int(self.settings.music_volume * 100):3d}%",
            f"Sound Volume: {int(self.settings.sound_volume * 100):3d}%",
        ]

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, "Options", surface.get_width() // 2, 160)
        self.widget.render(surface, surface.get_width() // 2, 260)
        UI.render_menu_ui_element(surface, "ESC back", 20, surface.get_height() - 40)
