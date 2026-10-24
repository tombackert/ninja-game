"""Multiplayer menu states (MP-08).

Host/join flow:
- ``MultiplayerMenuState``: host, join a friend, join by address; shows
  this installation's friend code.
- Hosting spawns the dedicated server as a subprocess on this machine
  (level = currently selected level) and enters the game as first player.
  The server registers at the rendezvous so friends find it by code; the
  HUD shows the code and the LAN address.
- ``FriendsState``: friends by code, who of them is hosting; add a friend.
- ``JoiningState``: finds the friend's game through the rendezvous and
  punches a direct path to it (scripts/network/online.py).
- ``JoinGameState``: enter the host's address (ip[:port]) and connect
  (remembers the last one).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pygame

from scripts.network.online import Background, Identity, JoinOnline, call_rendezvous, normalize_code
from scripts.state_manager import State
from scripts.ui_widgets import ScrollableListWidget

DEFAULT_PORT = 7777


def get_lan_ip() -> str:
    """Best-effort LAN IP discovery (no packets are actually sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def default_player_name() -> str:
    return os.environ.get("NINJA_PLAYER_NAME") or os.environ.get("USER") or "Player"


def start_host_server(level: int, port: int = DEFAULT_PORT, name: str = "") -> subprocess.Popen:
    """Spawn the dedicated server subprocess for a hosted game (online: friends join by code)."""
    cmd = [sys.executable, "server.py", "--port", str(port), "--level", str(level), "--parent-pid", str(os.getpid())]
    if name:
        cmd += ["--online", "--name", name]
    return subprocess.Popen(cmd, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_address(text: str) -> Tuple[str, int]:
    """Parse 'host' or 'host:port' into an address tuple."""
    text = text.strip()
    if ":" in text:
        host, _, port_str = text.rpartition(":")
        try:
            return host or "127.0.0.1", int(port_str)
        except ValueError:
            return text, DEFAULT_PORT
    return text or "127.0.0.1", DEFAULT_PORT


class MultiplayerMenuState(State):
    """Submenu: Host Game / Join Game / Back."""

    name = "MultiplayerMenuState"

    def __init__(self) -> None:
        from scripts.displayManager import DisplayManager
        from scripts.localization import LocalizationService
        from scripts.ui import UI

        self.loc = LocalizationService.get()
        self._ui = UI
        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self.options_keys = ["mp.host", "mp.friends", "mp.join", "mp.back"]
        self.code = Identity.load().code
        self.widget = ScrollableListWidget(
            [self.loc.translate(k) for k in self.options_keys],
            visible_rows=4,
            spacing=50,
            font_size=30,
        )
        self.enter = False
        self.request_back = False
        # Consumed by app.py: "host" | "friends" | "join"
        self.next_action: Optional[str] = None
        self.error: Optional[str] = None

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act == "menu_up":
                self.widget.move_up()
            elif act == "menu_down":
                self.widget.move_down()
            elif act == "menu_select":
                self.enter = True
            elif act in ("menu_back", "menu_quit"):
                self.request_back = True

    def update(self, dt: float) -> None:
        if self.enter:
            key = self.options_keys[self.widget.selected_index]
            if key == "mp.host":
                self.next_action = "host"
            elif key == "mp.friends":
                self.next_action = "friends"
            elif key == "mp.join":
                self.next_action = "join"
            else:
                self.request_back = True
            self.enter = False

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("mp.title"), surface.get_width() // 2, 200)
        self.widget.render(surface, surface.get_width() // 2, 300)
        UI.render_menu_ui_element(
            surface, self.loc.translate("mp.your_code").format(code=self.code), 20, surface.get_height() - 100
        )
        if self.error:
            UI.render_menu_ui_element(surface, self.error, surface.get_width() // 2 - 120, surface.get_height() - 70)
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("menu.enter_hint"),
            surface.get_width() // 2 - 120,
            surface.get_height() - 40,
        )


class JoinGameState(State):
    """Text entry for the host address, then connect."""

    name = "JoinGameState"

    def __init__(self, initial: str = "") -> None:
        from scripts.displayManager import DisplayManager
        from scripts.localization import LocalizationService
        from scripts.ui import UI

        self.loc = LocalizationService.get()
        self._ui = UI
        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")
        self.text = initial or "127.0.0.1"
        self.request_back = False
        # Consumed by app.py: (host, port) once Enter is pressed
        self.join_request: Optional[Tuple[str, int]] = None

    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif e.unicode and (e.unicode.isalnum() or e.unicode in ".:-_"):
                if len(self.text) < 40:
                    self.text += e.unicode

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act == "menu_select" and self.text.strip():
                self.join_request = parse_address(self.text)
            elif act == "menu_quit":
                self.request_back = True

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, self.loc.translate("mp.join_title"), surface.get_width() // 2, 200)
        # Address input box
        font = UI.get_font(30)
        UI.draw_text_with_outline(
            surface=surface,
            font=font,
            text=self.text + "_",
            x=surface.get_width() // 2,
            y=320,
            center=True,
            scale=3,
        )
        UI.render_menu_ui_element(
            surface,
            self.loc.translate("mp.join_hint"),
            surface.get_width() // 2 - 160,
            surface.get_height() - 40,
        )


class _MenuScreen(State):
    """Background, title and hint shared by the online menu screens."""

    def __init__(self) -> None:
        from scripts.displayManager import DisplayManager
        from scripts.localization import LocalizationService
        from scripts.ui import UI

        self.loc = LocalizationService.get()
        self._ui = UI
        self.dm = DisplayManager()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)
        self.bg = pygame.image.load("data/images/background-big.png")

    def _render_frame(self, surface: pygame.Surface, title: str, hint: str) -> None:
        UI = self._ui
        UI.render_menu_bg(surface, self.display, self.bg)
        UI.render_menu_title(surface, title, surface.get_width() // 2, 120)
        UI.render_menu_ui_element(surface, hint, 20, surface.get_height() - 40)

    def _line(self, surface: pygame.Surface, text: str, y: int, color=None) -> None:
        """One centered line of menu text."""
        UI = self._ui
        font = UI.get_font(15)
        width = font.size(text)[0] * 2  # rendered at scale 2
        UI.draw_text_with_outline(
            surface=surface,
            font=font,
            text=text,
            x=surface.get_width() // 2 - width // 2,
            y=y,
            text_color=color or UI.GAME_UI_COLOR,
            scale=2,
        )


class FriendsState(_MenuScreen):
    """Friends by code: who is hosting right now; Enter joins, the last row adds a friend.

    Typing a code needs letters, so only the arrow keys move the selection
    here (W/S would be part of a code). Delete or Backspace on a friend
    asks once, the second press removes it.
    """

    name = "FriendsState"
    STATUS_POLL_S = 3.0

    def __init__(self) -> None:
        super().__init__()
        self.identity = Identity.load()
        self.status: Dict[str, Dict[str, Any]] = {}  # code -> {"hosting", "name", "level", "version"}
        self.status_error = ""
        self._call: Optional[Background] = None
        self._next_poll = 0.0
        self.selected = 0
        self.adding = False
        self.text = ""
        self.message = ""
        self._confirm_remove: Optional[str] = None
        self.request_back = False
        # Consumed by app.py: (friend code, friend name)
        self.join_request: Optional[Tuple[str, str]] = None

    @property
    def rows(self) -> List[Optional[Dict[str, str]]]:
        """The friends, then None for the "add friend" row."""
        return [*self.identity.friends, None]

    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if self.adding:
                if e.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                elif e.unicode and (e.unicode.isalnum() or e.unicode == "-") and len(self.text) < 12:
                    self.text += e.unicode.upper()
            elif e.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                friend = self.rows[self.selected]
                if friend is None:
                    continue
                if self._confirm_remove == friend["code"]:
                    self.identity.remove_friend(friend["code"])
                    self.selected = min(self.selected, len(self.rows) - 1)
                    self._confirm_remove = None
                    self.message = ""
                else:
                    self._confirm_remove = friend["code"]
                    self.message = self.loc.translate("mp.remove_confirm").format(name=_friend_label(friend))

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act == "menu_quit":
                if self.adding:
                    self.adding = False
                    self.message = ""
                else:
                    self.request_back = True
            elif act == "menu_select":
                self._select()
            elif act in ("menu_up", "menu_down") and not self.adding:
                step = -1 if act == "menu_up" else 1
                self.selected = (self.selected + step) % len(self.rows)
                self._confirm_remove = None
                self.message = ""

    def _select(self) -> None:
        if self.adding:
            code = normalize_code(self.text)
            if code is None:
                self.message = self.loc.translate("mp.code_invalid")
            elif code == self.identity.code:
                self.message = self.loc.translate("mp.code_own")
            elif not self.identity.add_friend(code):
                self.message = self.loc.translate("mp.code_known")
            else:
                self.adding = False
                self.text = ""
                self.message = ""
                self.selected = len(self.identity.friends) - 1
                self._next_poll = 0.0  # ask for the new friend's status now
            return
        friend = self.rows[self.selected]
        if friend is None:
            self.adding = True
            self.text = ""
            self.message = ""
            return
        status = self.status.get(friend["code"], {})
        if status.get("hosting"):
            self.join_request = (friend["code"], status.get("name") or _friend_label(friend))
        else:
            self.message = self.loc.translate("mp.not_hosting").format(name=_friend_label(friend))

    def update(self, dt: float) -> None:
        now = time.monotonic()
        if self._call is not None and self._call.done:
            call, self._call = self._call, None
            if call.error is not None:
                self.status_error = self.loc.translate("mp.rendezvous_unreachable")
            else:
                self.status_error = ""
                self.status = call.result.get("friends", {})
                for code, st in self.status.items():
                    if st.get("name"):
                        self.identity.set_friend_name(code, st["name"])
        codes = [f["code"] for f in self.identity.friends]
        if self._call is None and codes and now >= self._next_poll:
            self._next_poll = now + self.STATUS_POLL_S
            self._call = Background(call_rendezvous, "/v1/status", {"codes": codes})

    def render(self, surface: pygame.Surface) -> None:
        UI = self._ui
        hint = self.loc.translate("mp.add_hint" if self.adding else "mp.friends_hint")
        self._render_frame(surface, self.loc.translate("mp.friends_title"), hint)
        self._line(surface, self.loc.translate("mp.your_code").format(code=self.identity.code), 200)
        y = 260
        for i, friend in enumerate(self.rows):
            if friend is None:
                text = self.loc.translate("mp.add_friend")
                if self.adding:
                    text = "> " + self.text + "_"
            else:
                status = self.status.get(friend["code"])
                if status is None:
                    state = "..."
                elif status.get("hosting"):
                    state = self.loc.translate("mp.hosting_level").format(level=status.get("level", 0))
                else:
                    state = self.loc.translate("mp.offline")
                text = f"{_friend_label(friend)}  {state}"
            color = UI.SELECTOR_COLOR if i == self.selected else UI.PM_COLOR
            self._line(surface, text, y, color)
            y += 40
        for text in (self.message, self.status_error):
            if text:
                self._line(surface, text, y + 20)
                y += 36


class JoiningState(_MenuScreen):
    """Shows the way to a friend's game: rendezvous, then punching; Enter retries a failure."""

    name = "JoiningState"

    def __init__(self, code: str, friend_name: str) -> None:
        super().__init__()
        self.code = code
        self.friend_name = friend_name
        self.request_back = False
        # Consumed by app.py once a path answers: (transport, (host, port), path kind)
        self.result: Optional[Tuple[Any, Tuple[str, int], str]] = None
        self.session = JoinOnline(Identity.load(), code, default_player_name())

    def handle_actions(self, actions: Sequence[str]) -> None:
        for act in actions:
            if act == "menu_quit":
                self.session.cancel()
                self.request_back = True
            elif act == "menu_select" and self.session.phase == "failed":
                self.session = JoinOnline(Identity.load(), self.code, default_player_name())

    def update(self, dt: float) -> None:
        self.session.update()
        if self.session.phase == "connected" and self.session.result is not None:
            transport, addr = self.session.result
            self.result = (transport, addr, self.session.path_kind)

    def render(self, surface: pygame.Surface) -> None:
        phase = self.session.phase
        hint = self.loc.translate("mp.retry_hint" if phase == "failed" else "mp.cancel_hint")
        self._render_frame(surface, self.loc.translate("mp.joining_title"), hint)
        name = self.session.host_name or self.friend_name
        if phase == "failed":
            text = self.loc.translate("mp.join_failed").format(name=name, error=self.session.error)
        else:
            text = self.loc.translate("mp.phase_" + phase).format(name=name)
        self._line(surface, text, 300)


def _friend_label(friend: Dict[str, str]) -> str:
    return friend.get("name") or friend["code"]


__all__ = [
    "MultiplayerMenuState",
    "FriendsState",
    "JoiningState",
    "JoinGameState",
    "start_host_server",
    "get_lan_ip",
    "default_player_name",
    "parse_address",
    "DEFAULT_PORT",
]
