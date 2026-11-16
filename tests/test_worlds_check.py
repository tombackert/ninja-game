"""The one-screen level check (tools/worlds/check.py) on a tiny level, twice: the second run is cached."""

import os
import sys
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

import pygame  # noqa: E402
import pytest  # noqa: E402

from scripts.tilemap import Tilemap  # noqa: E402
from tools.worlds import cache as C  # noqa: E402
from tools.worlds import check as CK  # noqa: E402
from tools.worlds import route  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402

MAP_ID = 9004


def _build():
    """Level 9004 - Test Steps (stone).

    Three ledges over the void, a banner on the second."""
    lv = Level(MAP_ID, "stone")
    lv.rect(0, 20, 10, 23)
    lv.rect(14, 20, 24, 23)
    lv.rect(28, 19, 40, 23)
    lv.spawn(3, 19)
    lv.wp(15, 19, 17, 19, ground=True, label="second ledge")
    lv.checkpoint(19, 19)
    lv.wp(30, 18, 32, 18, ground=True, label="third ledge")
    lv.flag(38, 18)
    lv.wp(38, 18, label="flag")
    return lv


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    maps = tmp_path / "maps"
    maps.mkdir()
    mod = types.ModuleType(f"tools.worlds.levels.level_{MAP_ID}")
    mod.__doc__ = _build.__doc__
    mod.build = _build
    monkeypatch.setitem(sys.modules, mod.__name__, mod)
    monkeypatch.setattr(Level, "save", lambda self, maps_dir=None: str(_save(self, maps)))
    load = Tilemap.load

    def redirected(self, path, *a, **k):
        target = str(maps / f"{MAP_ID}.json") if path.endswith(f"/{MAP_ID}.json") else path
        result = load(self, target, *a, **k)
        self.loaded_path = path
        return result

    monkeypatch.setattr(Tilemap, "load", redirected)
    monkeypatch.setattr(route, "PLANS_DIR", str(tmp_path / "plans"))
    monkeypatch.setattr(CK, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(C, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(CK, "PHYSICS_FRAMES", 1500)
    import tools.worlds.assess as A

    monkeypatch.setattr(A, "_map_data", lambda n: __import__("json").load(open(maps / f"{n}.json"))["map_data"])
    pygame.init()
    return tmp_path


def _save(lv, maps):
    import json

    path = maps / f"{lv.map_id}.json"
    path.write_text(json.dumps(lv.to_json()))
    return path


def _stores(root):
    return C.Store("route", C.route_store().version, str(root / "cache")), C.Store(
        "element", C.element_store().version, str(root / "cache")
    )


def test_the_check_fits_on_a_screen_and_the_second_run_is_cached(sandbox, monkeypatch):
    stores = _stores(sandbox)
    monkeypatch.setattr(C, "route_store", lambda root=None: stores[0])
    monkeypatch.setattr(C, "element_store", lambda root=None: stores[1])
    lines, report = CK.run_check(MAP_ID, jobs=1, shortcuts=True)
    text = "\n".join(lines)
    assert len(lines) <= 16
    assert lines[0].startswith("level 9004 Test Steps") and "check 1 of this level" in lines[0]
    assert "route      OK" in text and "physics    OK" in text and "banner     OK" in text
    assert "shortcuts" in text and "rating" in text
    assert report["route"]["guides"] == 0
    assert os.path.exists(sandbox / "out" / str(MAP_ID) / "elements.txt")
    first = (stores[0].hits, stores[1].hits)
    lines2, report2 = CK.run_check(MAP_ID, jobs=1, shortcuts=False)
    assert "check 2 of this level" in lines2[0]
    assert stores[0].hits - first[0] == len(_build().route)  # every segment from the cache
    assert stores[1].hits - first[1] == report2["rating"]["elements"]  # every element too
    assert report2["rating"]["first_clear"] == report["rating"]["first_clear"]
