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


# --- route from a replay ----------------------------------------------------------


def _snap(x_tile, y_px, dead=0):
    return {"players": [{"pos": [x_tile * 16, y_px]}], "dead_count": dead}


STAND19 = 20 * 16 - 15  # feet on row 20: standing on air tile row 19
STAND18 = 19 * 16 - 15


def _replay(with_death: bool) -> dict:
    path = [(3, STAND19, 0), (9, STAND19, 0)]
    if with_death:  # off the first ledge into the void, back at the spawn
        path += [(12, STAND19 + 40, 0), (12, STAND19 + 90, 1), (3, STAND19, 1), (9, STAND19, 1)]
    path += [(12, STAND19 - 30, 0), (16, STAND19, 0), (22, STAND19, 0), (26, STAND18 - 20, 0)]
    path += [(31, STAND18, 0), (37, STAND18, 0)]
    dead_from = 3 if with_death else len(path)
    snaps = {}
    for i, (x, y, d) in enumerate(path):
        snaps[str(i * 10)] = _snap(x, y, 1 if with_death and i >= dead_from else d)
    return {"snapshots": snaps}


def test_a_replay_gives_stops_where_the_run_stood(editor_map):
    ml = MapLevel.load(MAP_ID)
    r = draft.replay_route(ml, _replay(False))
    assert [(w.x0, w.y0, w.x1, w.y1, w.ground) for w in r[:-1]] == [
        (8, 19, 10, 19, True),
        (15, 19, 17, 19, True),
        (21, 19, 23, 19, True),
        (30, 18, 32, 18, True),
    ]
    assert r[-1] == Waypoint(38, 18, 38, 18, False, "flag")  # (37, 18) is at the flag: no stop of its own
    assert draft.replay_route(ml, _replay(True)) == r  # the stops before the death are taken again
    res = route.plan_route(ml.solids(), ml.spawn_px, r, ml.kill_y(), verbose=False)
    assert res.ok


# --- the editor's route mode --------------------------------------------------------


@pytest.fixture
def layer(editor_map):
    import pygame

    from tools.worlds.editor_route import RouteLayer

    pygame.init()
    tm = Tilemap(None)
    tm.load(str(editor_map), load_entities=False)
    saved = []
    lay = RouteLayer(tm, str(MAP_ID), lambda: saved.append(tm.save(str(editor_map))))
    lay.toggle_active()
    lay.saved = saved
    return lay


def _event(kind, **kw):
    import pygame

    return pygame.event.Event(kind, **kw)


def test_route_mode_draws_selects_orders_and_deletes_waypoints(layer):
    import pygame

    down, up, key = pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.KEYDOWN
    assert layer.handle_event(_event(down, button=1), (15, 19))  # drag a box over the second ledge
    assert layer.handle_event(_event(up, button=1), (17, 19))
    layer.handle_event(_event(down, button=1), (38, 18))
    layer.handle_event(_event(up, button=1), (38, 18))
    assert [(w.x0, w.y0, w.x1, w.y1, w.ground) for w in layer.route] == [(15, 19, 17, 19, True), (38, 18, 38, 18, True)]
    assert layer.selected == 1
    layer.handle_event(_event(key, key=pygame.K_f, mod=0), None)  # the flag box is no ground waypoint
    assert not layer.route[1].ground
    layer.handle_event(_event(down, button=1), (31, 18))  # a stop on the third ledge, after the first box
    layer.handle_event(_event(up, button=1), (31, 18))
    assert layer.selected == 2
    layer.handle_event(_event(key, key=pygame.K_COMMA, mod=0), None)  # one place earlier: before the flag
    assert [w.x0 for w in layer.route] == [15, 31, 38] and layer.selected == 1
    layer.handle_event(_event(down, button=1), (16, 19))  # a click on a box selects it
    assert layer.selected == 0
    layer.handle_event(_event(key, key=pygame.K_u, mod=0), None)
    assert layer.route[0].guide
    layer.handle_event(_event(down, button=3), (31, 18))  # right click deletes
    assert [w.x0 for w in layer.route] == [15, 38]
    assert not layer.handle_event(_event(key, key=pygame.K_a, mod=0), None)  # scrolling stays the editor's


def test_route_mode_drafts_plans_and_saves_the_plan(layer):
    import pygame

    surf = pygame.Surface((640, 360), pygame.SRCALPHA)
    font = pygame.font.Font(None, 10)
    layer.draft()
    assert [w.label for w in layer.route] == ["checkpoint", "flag"]
    layer.draft()  # a route is there: not replaced without Shift
    assert "Shift+N" in layer.status
    layer.render(surf, (0, 200), font, (5, 19))
    layer.plan(wait=True)
    assert layer.saved == [True]
    assert layer.status.startswith("OK"), layer.status
    assert layer.trail and layer.failed_at is None
    plan = route.load_plan(MAP_ID)
    assert plan["waypoints"] == layer.route
    assert route_from_json(MapLevel.load(MAP_ID).data["map_data"]["route"]) == layer.route  # saved with the map
    layer.render(surf, (0, 200), font, (5, 19))  # with the planned path
    layer.add((5, 22), (5, 22))  # inside the rock of the first ledge: nobody gets there
    layer.move(-1)
    layer.plan(wait=True)
    assert layer.status.startswith("UNREACHED") and layer.failed_at is not None
