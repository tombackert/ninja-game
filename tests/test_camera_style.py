"""Camera styles: "classic" always re-centers, "calm" holds still more often."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

from game import Game  # noqa: E402
from scripts.constants import CALM_CAMERA_BAND_Y, CALM_CAMERA_DEADZONE_X  # noqa: E402
from scripts.settings import Settings, settings  # noqa: E402


def _game(monkeypatch, style):
    # Set the private field: the setter would write the real settings file
    monkeypatch.setattr(settings, "_camera_style", style)
    g = Game()
    g.load_level(0)
    return g


def _center(g):
    r = g.player.rect()
    return r.centerx - g.BASE_W / 2, r.centery - g.BASE_H / 2


def test_classic_eases_a_thirtieth_per_frame(monkeypatch):
    g = _game(monkeypatch, "classic")
    cx, cy = _center(g)
    g.scroll = [cx - 30.0, cy + 60.0]
    g.update_camera()
    assert g.scroll == [cx - 29.0, cy + 58.0]


def test_calm_holds_still_while_player_is_in_the_box(monkeypatch):
    g = _game(monkeypatch, "calm")
    g.player.collisions["down"] = True
    cx, cy = _center(g)
    g.scroll = [cx + CALM_CAMERA_DEADZONE_X - 1, cy]
    for _ in range(100):
        g.update_camera()
    assert g.scroll == [cx + CALM_CAMERA_DEADZONE_X - 1, cy]


def test_calm_follows_to_the_box_edge_and_stops_exactly(monkeypatch):
    g = _game(monkeypatch, "calm")
    g.player.collisions["down"] = True
    cx, cy = _center(g)
    g.scroll = [cx - 100.0, cy - 20.0]
    for _ in range(300):
        g.update_camera()
    assert g.scroll == [cx - CALM_CAMERA_DEADZONE_X, cy]


def test_calm_ignores_small_jumps_but_follows_long_falls(monkeypatch):
    g = _game(monkeypatch, "calm")
    cx, cy = _center(g)
    g.player.collisions["down"] = False
    g.scroll = [cx, cy - CALM_CAMERA_BAND_Y + 1]  # player within the band
    g.update_camera()
    assert g.scroll[1] == cy - CALM_CAMERA_BAND_Y + 1
    g.scroll = [cx, cy - CALM_CAMERA_BAND_Y - 20]  # player far below center
    g.update_camera()
    assert g.scroll[1] > cy - CALM_CAMERA_BAND_Y - 20


def test_camera_style_is_saved_and_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    s = Settings()
    assert s.camera_style == "classic"
    s.camera_style = "calm"
    s.camera_style = "wobbly"  # unknown styles are ignored
    assert Settings().camera_style == "calm"
