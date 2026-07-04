"""Multiplayer menu states (MP-08).

Host/join flow:
- ``MultiplayerMenuState``: choose between hosting and joining.
- Hosting spawns the dedicated server as a subprocess on this machine
  (level = currently selected level) and enters the game as first player.
  The HUD shows the LAN address other players can join.
- ``JoinGameState``: enter the host's address (ip[:port]) and connect.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from typing import Optional, Sequence, Tuple

import pygame

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
    return os.environ.get("NINJA_PLAYER_NAME") or os.environ.get("USER", "Player")


def start_host_server(level: int, port: int = DEFAULT_PORT) -> subprocess.Popen:
    """Spawn the dedicated server subprocess for a hosted game."""
    return subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port), "--level", str(level)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


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
        self.options_keys = ["mp.host", "mp.join", "mp.back"]
        self.widget = ScrollableListWidget(
            [self.loc.translate(k) for k in self.options_keys],
            visible_rows=3,
            spacing=50,
            font_size=30,
        )
        self.enter = False
        self.request_back = False
        # Consumed by app.py: "host" | "join"
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


__all__ = [
    "MultiplayerMenuState",
    "JoinGameState",
    "start_host_server",
    "get_lan_ip",
    "default_player_name",
    "parse_address",
    "DEFAULT_PORT",
]
