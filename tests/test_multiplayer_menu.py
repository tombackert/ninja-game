"""Tests for the multiplayer host/join menu flow (MP-08)."""

from __future__ import annotations

import os

import pygame
import pytest

os.environ["NINJA_GAME_TESTING"] = "1"

from scripts.multiplayer_menu import (
    DEFAULT_PORT,
    JoinGameState,
    MultiplayerMenuState,
    parse_address,
)


@pytest.fixture(autouse=True)
def init_pygame():
    pygame.init()
    pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((320, 180))
    yield


class TestParseAddress:
    def test_plain_ip_uses_default_port(self):
        assert parse_address("192.168.1.20") == ("192.168.1.20", DEFAULT_PORT)

    def test_ip_with_port(self):
        assert parse_address("192.168.1.20:9999") == ("192.168.1.20", 9999)

    def test_hostname_with_port(self):
        assert parse_address("my-mac.local:7777") == ("my-mac.local", 7777)

    def test_empty_falls_back_to_localhost(self):
        assert parse_address("") == ("127.0.0.1", DEFAULT_PORT)

    def test_whitespace_stripped(self):
        assert parse_address("  10.0.0.5 ") == ("10.0.0.5", DEFAULT_PORT)


class TestMultiplayerMenuState:
    def test_select_host(self):
        state = MultiplayerMenuState()
        # First entry is "Host Game"
        state.handle_actions(["menu_select"])
        state.update(0.016)
        assert state.next_action == "host"

    def test_select_join(self):
        state = MultiplayerMenuState()
        state.handle_actions(["menu_down", "menu_select"])
        state.update(0.016)
        assert state.next_action == "join"

    def test_select_back(self):
        state = MultiplayerMenuState()
        state.handle_actions(["menu_down", "menu_down", "menu_select"])
        state.update(0.016)
        assert state.next_action is None
        assert state.request_back

    def test_escape_goes_back(self):
        state = MultiplayerMenuState()
        state.handle_actions(["menu_quit"])
        assert state.request_back


class TestJoinGameState:
    def test_default_text(self):
        state = JoinGameState()
        assert state.text == "127.0.0.1"

    def test_typing_and_backspace(self):
        state = JoinGameState(initial="10.0.0")
        events = [
            pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_PERIOD, "unicode": "."}),
            pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_5, "unicode": "5"}),
        ]
        state.handle(events)
        assert state.text == "10.0.0.5"

        state.handle([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_BACKSPACE, "unicode": ""})])
        assert state.text == "10.0.0."

    def test_enter_produces_join_request(self):
        state = JoinGameState(initial="192.168.0.7:8888")
        state.handle_actions(["menu_select"])
        assert state.join_request == ("192.168.0.7", 8888)

    def test_escape_requests_back(self):
        state = JoinGameState()
        state.handle_actions(["menu_quit"])
        assert state.request_back

    def test_rejects_invalid_characters(self):
        state = JoinGameState(initial="1.2.3.4")
        state.handle([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_SPACE, "unicode": " "})])
        assert state.text == "1.2.3.4"


class TestMenuStateMultiplayerEntry:
    def test_menu_has_multiplayer_option(self):
        from scripts.state_manager import MenuState

        menu = MenuState()
        assert "menu.multiplayer" in menu.options_keys

    def test_selecting_multiplayer_sets_next_state(self):
        from scripts.state_manager import MenuState

        menu = MenuState()
        idx = menu.options_keys.index("menu.multiplayer")
        menu.list_widget.selected_index = idx
        menu.enter = True
        menu.update(0.016)
        assert menu.next_state == "Multiplayer"
