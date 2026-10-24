"""Tests for the multiplayer host/join menu flow (MP-08)."""

from __future__ import annotations

import os

import pygame
import pytest

os.environ["NINJA_GAME_TESTING"] = "1"

from scripts.multiplayer_menu import (
    DEFAULT_PORT,
    FriendsState,
    JoinGameState,
    MultiplayerMenuState,
    parse_address,
)
from scripts.network import online


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

    def test_select_friends(self):
        state = MultiplayerMenuState()
        state.handle_actions(["menu_down", "menu_select"])
        state.update(0.016)
        assert state.next_action == "friends"

    def test_select_join(self):
        state = MultiplayerMenuState()
        state.handle_actions(["menu_down", "menu_down", "menu_select"])
        state.update(0.016)
        assert state.next_action == "join"

    def test_select_back(self):
        state = MultiplayerMenuState()
        state.handle_actions(["menu_down", "menu_down", "menu_down", "menu_select"])
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


def _type(state, text):
    state.handle([pygame.event.Event(pygame.KEYDOWN, {"key": 0, "unicode": ch}) for ch in text])


def _key(state, key):
    state.handle([pygame.event.Event(pygame.KEYDOWN, {"key": key, "unicode": ""})])


class TestFriendsState:
    @pytest.fixture(autouse=True)
    def fresh_identity(self, tmp_path, monkeypatch):
        monkeypatch.setattr(online, "ONLINE_FILE", str(tmp_path / "online.json"))

    def test_add_a_friend_by_code(self):
        state = FriendsState()
        state.handle_actions(["menu_select"])  # the only row: "+ Add friend"
        assert state.adding
        _type(state, "k7hm2xra")
        state.handle_actions(["menu_select"])
        assert not state.adding
        assert online.Identity.load().friends == [{"code": "K7HM-2XRA", "name": ""}]
        assert state.selected == 0

    def test_typing_w_and_s_does_not_move_the_selection(self):
        state = FriendsState()
        state.handle_actions(["menu_select"])
        _type(state, "ws")
        assert state.text == "WS"

    def test_invalid_and_own_codes_are_refused(self):
        state = FriendsState()
        state.handle_actions(["menu_select"])
        _type(state, "hello")
        state.handle_actions(["menu_select"])
        assert state.adding and "Not a friend code" in state.message
        state.text = state.identity.code
        state.handle_actions(["menu_select"])
        assert state.adding and state.message == "That is your own code"

    def test_join_only_a_friend_who_is_hosting(self):
        state = FriendsState()
        state.identity.add_friend("K7HM-2XRA", "Max")
        state.handle_actions(["menu_select"])
        assert state.join_request is None
        assert state.message == "Max is not hosting right now"
        state.status = {"K7HM-2XRA": {"hosting": True, "name": "Max", "level": 3}}
        state.handle_actions(["menu_select"])
        assert state.join_request == ("K7HM-2XRA", "Max")

    def test_delete_asks_once_then_removes(self):
        state = FriendsState()
        state.identity.add_friend("K7HM-2XRA", "Max")
        _key(state, pygame.K_DELETE)
        assert len(state.identity.friends) == 1 and "Max" in state.message
        _key(state, pygame.K_DELETE)
        assert state.identity.friends == []

    def test_escape_cancels_adding_then_goes_back(self):
        state = FriendsState()
        state.handle_actions(["menu_select", "menu_quit"])
        assert not state.adding and not state.request_back
        state.handle_actions(["menu_quit"])
        assert state.request_back

    def test_renders(self):
        state = FriendsState()
        state.identity.add_friend("K7HM-2XRA", "Max")
        state.status = {"K7HM-2XRA": {"hosting": True, "name": "Max", "level": 3}}
        state.render(pygame.Surface((1280, 720)))
