"""The level editor's window: painting, undo, zoom, the palette and route mode (editor.py)."""

import json

import pygame
import pytest

from scripts import editor_ui as ui

MAP = "3"


@pytest.fixture
def ed(tmp_path, monkeypatch):
    import editor as editor_mod
    from scripts.settings import settings

    monkeypatch.setattr(settings, "save_settings", lambda *a, **k: None)
    e = editor_mod.Editor(MAP)
    e.screen = pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    e.map_path = str(tmp_path / "3.json")  # saves go to a scratch file, the map stays as it is
    e.center_on_map()
    e.draw()
    yield e
    pygame.display.quit()


def _ev(kind, **kw):
    return pygame.event.Event(kind, **kw)


def _screen_of_tile(e, tile):
    """Screen px over the middle of a tile."""
    v = e.layout()["view"]
    x, y = e.to_screen(tile[0] * 16 + 8, tile[1] * 16 + 8)
    return v.x + x, v.y + y


def _click(e, pos, button=1):
    e.handle_event(_ev(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    e.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    e.handle_event(_ev(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def _key(e, key, mod=0):
    return e.handle_event(_ev(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _empty_tile(e):
    v = e.layout()["view"]
    for ty in range(-40, 40):
        for tx in range(-40, 40):
            pos = _screen_of_tile(e, (tx, ty))
            if v.inflate(-40, -40).collidepoint(pos) and f"{tx};{ty}" not in e.tilemap.tilemap:
                return (tx, ty), pos
    raise AssertionError("no empty tile in view")


def test_a_palette_click_picks_the_tile_and_painting_undoes_and_redoes(ed):
    cell = next((r, tip) for r, _a, tip in ed.buttons if tip.startswith("Spawner · Turret"))
    _click(ed, cell[0].center)
    assert (ed.tile_group, ed.tile_variant) == ("spawners", 3)

    tile, pos = _empty_tile(ed)
    _click(ed, pos)
    assert ed.tilemap.tilemap[f"{tile[0]};{tile[1]}"]["type"] == "spawners"
    assert ed.unsaved and len(ed.undo_stack) == 1
    ed.draw()  # the new spawner is drawn as its character

    _key(ed, pygame.K_z, pygame.KMOD_META)
    assert f"{tile[0]};{tile[1]}" not in ed.tilemap.tilemap
    _key(ed, pygame.K_z, pygame.KMOD_META | pygame.KMOD_SHIFT)
    assert f"{tile[0]};{tile[1]}" in ed.tilemap.tilemap

    _click(ed, pos, button=3)  # right click erases
    assert f"{tile[0]};{tile[1]}" not in ed.tilemap.tilemap
    assert len(ed.undo_stack) == 2


def test_a_stroke_fills_the_tiles_between_two_mouse_positions(ed):
    ed.select("stone", 4)
    (tx, ty), pos = _empty_tile(ed)
    ed.handle_event(_ev(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(1, 0, 0)))
    ed.handle_event(_ev(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    far = (pos[0] + 5 * 16 * ed.zoom, pos[1])
    ed.handle_event(_ev(pygame.MOUSEMOTION, pos=far, rel=(0, 0), buttons=(1, 0, 0)))
    ed.update(0)
    ed.handle_event(_ev(pygame.MOUSEBUTTONUP, pos=far, button=1))
    assert all(ed.tilemap.tilemap[f"{tx + i};{ty}"]["variant"] == 4 for i in range(6))
    assert len(ed.undo_stack) == 1  # one stroke, one undo step


def test_zoom_goes_out_to_the_whole_map_and_back_with_a_click_on_the_zoom(ed):
    assert ed.zoom == ui.DEFAULT_ZOOM
    _key(ed, pygame.K_0)  # whole map
    b = ui.map_bounds(ed.tilemap)
    v = ed.layout()["view"]
    assert b.w * ed.zoom <= v.w and b.h * ed.zoom <= v.h
    ed.draw()
    zoom_button = next(r for r, _a, tip in ed.buttons if tip.startswith("Click: default zoom"))
    s = ed.layout()["status"]
    assert zoom_button.right > s.right - 20 and s.collidepoint(zoom_button.center)  # bottom right corner
    _click(ed, zoom_button.center)
    assert ed.zoom == ui.DEFAULT_ZOOM

    before = ed.world_at((v.x + 100, v.y + 80))
    ed.mouse = (v.x + 100, v.y + 80)
    ed.handle_event(_ev(pygame.MOUSEWHEEL, x=0, y=1, precise_x=0.0, precise_y=1.0, flipped=False))
    assert ed.zoom > ui.DEFAULT_ZOOM
    after = ed.world_at((v.x + 100, v.y + 80))
    assert abs(after[0] - before[0]) < 1 and abs(after[1] - before[1]) < 1  # zoomed at the mouse


def test_the_window_can_be_resized(ed):
    ed.screen = pygame.display.set_mode((1100, 700), pygame.RESIZABLE)
    ed.handle_event(_ev(pygame.VIDEORESIZE, size=(1100, 700), w=1100, h=700))
    lay = ed.layout()
    assert lay["status"].bottom == 700 and lay["view"].right <= 1100
    ed.draw()
    _key(ed, pygame.K_h)  # the key panel hides, the map gets its room
    assert ed.layout()["view"].right == 1100


def test_route_mode_edits_waypoints_with_undo_and_saves(ed, tmp_path):
    _key(ed, pygame.K_r)
    assert ed.route_layer.active
    n = len(ed.route_layer.route)
    _tile, pos = _empty_tile(ed)
    _click(ed, pos)  # a click on empty map: a one-tile waypoint
    assert len(ed.route_layer.route) == n + 1
    ed.draw()
    _key(ed, pygame.K_z, pygame.KMOD_CTRL)
    assert len(ed.route_layer.route) == n
    _key(ed, pygame.K_o)
    saved = json.loads((tmp_path / "3.json").read_text())
    assert len(saved["map_data"].get("route", [])) == n and not ed.unsaved
