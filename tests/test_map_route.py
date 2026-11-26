"""The route as part of the map (map_data.route, tools/worlds/mapfile.py):
saved and loaded with and without it, and planned from the map file alone."""

import json
import os
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

import pytest  # noqa: E402

from scripts.tilemap import Tilemap  # noqa: E402
from tools.worlds import build, draft, route  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402
from tools.worlds.mapfile import MapLevel, route_from_json, route_to_json  # noqa: E402
from tools.worlds.planner import Waypoint  # noqa: E402

MAP_ID = 9011


def _build() -> Level:
    """Three ledges over the void, a banner on the second, the flag on the third."""
    lv = Level(MAP_ID, "stone")
    lv.rect(0, 20, 10, 23)
    lv.rect(14, 20, 24, 23)
    lv.rect(28, 19, 40, 23)
    lv.spawn(3, 19)
    lv.coins(5, 19, 8)
    lv.enemy(22, 19, "gunner")
    lv.wp(15, 19, 17, 19, ground=True, label="second ledge")
    lv.checkpoint(19, 19)
    lv.wp(30, 18, 32, 18, ground=True, label="third ledge", guide=True)
    lv.flag(38, 18)
    lv.wp(38, 18, label="flag")
    return lv


def _read(path) -> dict:
    with open(path) as f:
        return json.load(f)


def test_waypoints_round_trip_with_all_fields():
    wps = [Waypoint(1, 2, 3, 4, True, "a", False), Waypoint(5.5, 6, 5.5, 6, False, "b", True)]
    rows = route_to_json(wps)
    assert rows[0] == {"x0": 1, "y0": 2, "x1": 3, "y1": 4, "ground": True, "label": "a", "guide": False}
    assert route_from_json(json.loads(json.dumps(rows))) == wps
    assert route_from_json([{"x0": 1, "y0": 2, "x1": 1, "y1": 2}]) == [Waypoint(1, 2, 1, 2)]
    assert route_from_json(None) == []
    with pytest.raises(ValueError):
        route_from_json([{"x0": 1, "y0": 2, "x1": 1, "y1": 2, "speed": 3}])


def test_a_built_level_saves_its_route_compactly(tmp_path):
    lv = _build()
    path = lv.save(str(tmp_path))
    text = open(path).read()
    assert ", " not in text and ": " not in text  # compact JSON
    assert route_from_json(json.loads(text)["map_data"]["route"]) == lv.route


def test_tilemap_keeps_the_route_through_load_and_save(tmp_path):
    path = _build().save(str(tmp_path))
    before = _read(path)["map_data"]["route"]
    tm = Tilemap(None)
    tm.load(path, load_entities=False)
    assert tm.route == before
    out = tmp_path / "saved.json"
    assert tm.save(str(out))
    assert _read(out)["map_data"]["route"] == before
    assert ", " not in out.read_text()


def test_tilemap_loads_and_saves_a_map_without_a_route(tmp_path):
    lv = _build()
    lv.route = []
    path = lv.save(str(tmp_path))
    assert "route" not in _read(path)["map_data"]
    tm = Tilemap(None)
    tm.load(path, load_entities=False)
    assert tm.route == [] and tm.tilemap
    out = tmp_path / "saved.json"
    assert tm.save(str(out))
    assert "route" not in _read(out)["map_data"]


def test_map_level_reads_what_the_planner_needs(tmp_path):
    lv = _build()
    lv.save(str(tmp_path))
    ml = MapLevel.load(MAP_ID, str(tmp_path))
    assert ml.route == lv.route
    assert ml.spawn_tile == lv.spawn_tile and ml.flag_tile == (38, 18)
    assert ml.checkpoint_tiles == [(19, 19)]
    a, b = ml.solids(), lv.solids()
    assert set(a) == set(b) and dict(a.water) == dict(b.water) and dict(a.lethal) == dict(b.lethal)


def test_the_plan_from_the_map_file_is_the_plan_from_the_level(tmp_path):
    lv = _build()
    lv.save(str(tmp_path))
    ml = MapLevel.load(MAP_ID, str(tmp_path))
    solids = lv.solids()
    from_level = route.plan_route(
        solids,
        (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16),
        lv.route,
        (max(y for _, y in solids) + 4) * 16,
        verbose=False,
    )
    from_map = route.plan_route(ml.solids(), ml.spawn_px, ml.route, ml.kill_y(), verbose=False)
    assert from_level.ok and from_map.ok
    assert from_map.frames == from_level.frames
    assert from_map.segments == from_level.segments


@pytest.fixture
def editor_map(tmp_path, monkeypatch):
    """A map with no level script, as the editor leaves it, in a scratch data/maps."""
    monkeypatch.chdir(tmp_path)
    maps = tmp_path / "data" / "maps"
    maps.mkdir(parents=True)
    lv = _build()
    lv.save(str(maps))
    data = _read(maps / f"{MAP_ID}.json")
    del data["map_data"]["route"]
    (maps / f"{MAP_ID}.json").write_text(json.dumps(data, separators=(",", ":")))
    monkeypatch.setattr(route, "PLANS_DIR", str(tmp_path / "plans"))
    return maps / f"{MAP_ID}.json"


def _args(**kw):
    base = {"no_plan": False, "assess": False, "preview": None, "hearts": False, "scale": 0.5}
    return types.SimpleNamespace(**{**base, **kw})


def test_the_draft_runs_over_the_checkpoints_to_the_flag(editor_map):
    ml = MapLevel.load(MAP_ID)
    assert ml.route == []
    assert draft.draft_route(ml) == [
        Waypoint(18, 19, 20, 19, True, "checkpoint"),
        Waypoint(38, 18, 38, 18, False, "flag"),
    ]
    assert draft.main(["draft", str(MAP_ID)]) == 0
    assert draft.main(["draft", str(MAP_ID)]) == 1  # a route is there: not replaced without --force
    assert draft.main(["insert", str(MAP_ID), "1", "30", "18", "32", "18", "--ground", "--label", "third"]) == 0
    labels = [w.label for w in MapLevel.load(MAP_ID).route]
    assert labels == ["checkpoint", "third", "flag"]
    assert draft.main(["delete", str(MAP_ID), "1"]) == 0
    assert [w.label for w in MapLevel.load(MAP_ID).route] == ["checkpoint", "flag"]


def test_an_editor_map_is_planned_from_its_file_and_left_as_it_is(editor_map):
    assert build.process_level(MAP_ID, _args()) == 1  # no route yet
    draft.main(["draft", str(MAP_ID)])
    before = editor_map.read_bytes()
    assert MAP_ID in build.routed_maps()
    assert build.process_level(MAP_ID, _args()) == 0
    assert editor_map.read_bytes() == before  # planning never rewrites an editor map
    plan = route.load_plan(MAP_ID)
    assert plan["waypoints"] == MapLevel.load(MAP_ID).route
    assert plan["frames"] > route.LEAD_IN


def test_hearts_go_into_an_editor_map_only_when_asked(editor_map, monkeypatch):
    from tools.worlds import hearts

    draft.main(["draft", str(MAP_ID)])
    monkeypatch.setattr(build, "HEART_LEVELS", (MAP_ID,))  # listed, but an editor map still needs --hearts
    place = hearts.place
    monkeypatch.setattr(hearts, "place", lambda lv, f, s: place(lv, f, s, budget=1e-9))  # wherever one fits
    before = editor_map.read_bytes()
    assert build.process_level(MAP_ID, _args()) == 0
    assert editor_map.read_bytes() == before
    assert build.process_level(MAP_ID, _args(hearts=True)) == 0
    assert MapLevel.load(MAP_ID).hearts()
    assert ", " not in editor_map.read_text()
