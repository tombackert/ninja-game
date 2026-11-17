"""Fullscreen: a saved setting, toggled from Options, GPU-scaled at 1280x720."""

import json
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402

from scripts.displayManager import WINDOW_SIZE, apply_window_mode  # noqa: E402
from scripts.settings import Settings, settings  # noqa: E402


def test_fullscreen_is_saved_and_loaded(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings()
    s.SETTINGS_FILE = str(path)
    s._fullscreen = False
    s.fullscreen = True

    assert json.loads(path.read_text())["fullscreen"] is True
    loaded = Settings()
    loaded.SETTINGS_FILE = str(path)
    loaded.load_settings()
    assert loaded.fullscreen is True


def test_window_mode_keeps_the_game_surface():
    pygame.init()
    window = apply_window_mode(False)
    assert window.get_size() == WINDOW_SIZE
    assert not window.get_flags() & pygame.FULLSCREEN

    full = apply_window_mode(True)
    assert full.get_size() == WINDOW_SIZE  # the GPU scales it to the screen
    assert full.get_flags() & pygame.FULLSCREEN

    assert apply_window_mode(False).get_size() == WINDOW_SIZE


def test_options_entry_toggles_fullscreen(monkeypatch):
    from scripts.state_manager import OptionsState

    pygame.init()
    apply_window_mode(False)
    monkeypatch.setattr(settings, "_fullscreen", False)
    monkeypatch.setattr(settings, "flush", lambda: None)  # keep the real settings file
    state = OptionsState()
    state.update(0)
    entry = next(i for i, text in enumerate(state.widget.options) if text.startswith("Fullscreen"))
    state.widget.selected_index = entry

    state.handle_actions(["options_right"])
    state.update(0)

    assert settings.fullscreen is True
    assert state.widget.options[entry].startswith("Fullscreen: ON")
