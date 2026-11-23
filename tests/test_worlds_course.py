"""Element library, composer, calibration course and the climb scan (cheap parts)."""

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

import pytest  # noqa: E402

from tools.worlds import compose as CP  # noqa: E402
from tools.worlds import course as CO  # noqa: E402
from tools.worlds import library as L  # noqa: E402
from tools.worlds import physics as ph  # noqa: E402
from tools.worlds import shortcuts as SC  # noqa: E402
from tools.worlds import windows as W  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402

# --- the library's test levels ----------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(L.KINDS))
def test_every_element_type_builds_a_test_level_with_a_route(kind):
    lv = L.test_level(kind)
    assert lv.spawn_tile is not None and lv.route
    assert lv.route[-1].ground  # it ends standing
    lv.to_json()  # no objects in rock, no leaking water


def test_a_gap_is_a_void_between_two_ledges():
    lv = L.test_level("gap", gap=7, dh=1)
    solids = lv.solids()
    assert (L.ENTRY - 1, L.FLOOR) in solids and (L.ENTRY, L.FLOOR) not in solids
    assert (L.ENTRY + 7, L.FLOOR - 1) in solids  # the landing, a row higher
    assert lv.route[0].y1 == L.FLOOR - 2


def test_measuring_reads_the_cache_back(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LIB_DIR", str(tmp_path))
    calls = []

    def fake(kind, **params):
        calls.append(params)
        return {"kind": kind, "params": params, "ok": True, "narrowest": 7}

    monkeypatch.setattr(L, "measure", fake)
    first = L.grid("gap", [{"gap": 3}, {"gap": 4}])
    again = L.grid("gap", [{"gap": 4}, {"gap": 3}])
    assert len(calls) == 2 and [r["params"] for r in again] == [{"gap": 4}, {"gap": 3}]
    assert first[0]["narrowest"] == 7


# --- the composer ---------------------------------------------------------------------------------


def _el(label, seconds, widths=(), fatal=None):
    return CP.Composed(label, seconds, [CP.Press(w) for w in widths], list(fatal or [1.0] * len(widths)))


def test_the_composer_combines_like_first_clear():
    els = [_el("walk", 3.0), _el("gap", 2.0, (25, 6), (0.0, 1.0)), _el("chimney", 4.0, (4, 8), (1.0, 0.5))]
    p = CP.predict(els, [1])
    fc = W.first_clear(els, W.PROFILES["expert"], [1])
    assert p["expert"]["minutes"] == fc["minutes"]
    parts = p["expert"]["parts_s"]
    assert parts["played_safe_x_pace"] == round(9.0 * W.PROFILES["expert"]["pace"], 1)
    assert parts["retries"] >= 0 and parts["restarts"] >= 0
    assert abs(sum(parts.values()) - fc["minutes"] * 60) < 0.5
    assert p["exposed_per_half"] == [0, 3] and p["le4_per_half"] == [0, 1]


def test_balance_prices_the_target_in_length_or_presses():
    els = [_el(f"e{i}", 3.0, (25,)) for i in range(20)]
    b = CP.balance(els, [10], 3.0)
    assert b["minutes"] < 3.0
    assert b["length_s"] > 0 and b["presses_per_half"] > 0
    longer, cuts = CP._with(els, [10], extra_s=b["length_s"])
    assert W.first_clear(longer, W.PROFILES["expert"], cuts)["minutes"] >= 3.0 - 0.01


def test_an_outline_is_read_from_the_library(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LIB_DIR", str(tmp_path))
    L.save(
        "gap",
        {
            L._point_key({"gap": 8}): {
                "ok": True,
                "elements": [{"seconds": 2.5, "widths": [25, 5], "fatal": [0.0, 1.0], "trick": False}],
            }
        },
    )
    outline = {"elements": [{"walk": 2.0}, {"banner": True}, {"kind": "gap", "gap": 8, "repeat": 2, "label": "chasm"}]}
    els, cuts = CP.elements_of(outline)
    assert [e.label for e in els] == ["walk", "chasm #1", "chasm #2"] and cuts == [1]
    assert els[1].narrowest == 5
    with pytest.raises(KeyError):
        CP.elements_of({"elements": [{"kind": "gap", "gap": 9}]})


def test_stamp_chains_elements_with_banners_and_ledges():
    lv = Level(950, "stone")
    lv.rect(0, 30, 9, 33)
    lv.spawn(3, 29)
    x, y = CP.stamp(lv, [{"banner": True}, {"kind": "gap", "gap": 4, "label": "g"}, {"walk": 1.0}], 10, 30)
    assert x > 20 and y == 30
    assert any(t["type"] == "checkpoint" for t in lv.offgrid)
    assert [w.label for w in lv.route] == ["g out", "walk"]


# --- the calibration course --------------------------------------------------------------------------


def _line(event, cps, session="s1", **kw):
    return {"event": event, "checkpoints": cps, "session": session, "map": "m", **kw}


def test_deaths_and_passes_per_element_from_the_log():
    lines = [
        _line("death", [0]),  # missed element 0
        _line("death", [0]),
        _line("death", [0, 1]),  # passed 0, missed 1
        _line("clear", [0, 1, 2]),  # passed everything
        _line("death", [0], session="s2"),  # a new session: missed 0
        _line("quit", [0, 1], session="s2"),  # passed 0, left on 1
        _line("death", [0], map="old"),  # another map version: left out
    ]
    cs = CO.counts(lines, 3, ["a", "b", "c"], map_hash="m")
    assert [(c.deaths, c.passes) for c in cs] == [(3, 2), (1, 1), (0, 1)]


def test_a_restart_ends_the_run():
    lines = [_line("death", [0, 1, 2], restart=True), _line("death", [0])]
    cs = CO.counts(lines, 3)
    assert [(c.deaths, c.passes) for c in cs] == [(1, 1), (0, 1), (1, 0)]


def test_the_fit_finds_the_sigma_and_lapse_the_data_came_from():
    rng = random.Random(4)
    true_sigma, true_lapse = 0.8, 0.04
    els, cs = [], []
    for k, w in enumerate((2, 3, 4, 6, 8, 13) * 3):
        el = _el(f"e{k}", 2.0, (25, w), (0.0, 1.0))
        q = CO.death_chance(el.presses(), true_sigma, true_lapse)
        d = sum(1 for _ in range(400) if rng.random() < q)
        els.append(el)
        cs.append(CO.Count(k, el.label, d, 400 - d))
    res = CO.fit(els, cs, ["gap"] * 9 + ["chimney"] * 9)
    j = res["joint"]
    assert j["sigma_range"][0] <= true_sigma <= j["sigma_range"][1]
    assert j["lapse_range"][0] <= true_lapse <= j["lapse_range"][1]
    assert res["family_test"]["p"] > 0.01  # one family, split in two: no need for own parameters
    assert [b["windows"] for b in res["bands"]][:2] == ["1-2", "3-4"]


def test_chi2_tail():
    assert abs(CO.chi2_sf(3.84, 1) - 0.05) < 0.002
    assert abs(CO.chi2_sf(5.99, 2) - 0.05) < 0.002


# --- the climb scan ------------------------------------------------------------------------------------


def test_a_sheer_wall_is_climbable_and_a_capped_one_is_not():
    floor = {(x, y) for x in range(0, 30) for y in (20, 21)}
    wall = {(10, y) for y in range(12, 20)}
    assert (10, -1, 12, 19) in SC.climbable_faces(ph.Terrain(floor | wall))
    cap = {(9, 11), (8, 11)}  # an overhang over the air west of it
    faces = SC.climbable_faces(ph.Terrain(floor | wall | cap))
    assert (10, -1, 12, 19) not in faces
    low = {(10, y) for y in range(17, 20)}
    assert not [f for f in SC.climbable_faces(ph.Terrain(floor | low)) if f[0] == 10]


def test_a_skip_that_saves_time_is_proven():
    lv = Level(997, "stone")
    lv.rect(0, 20, 40, 23)
    lv.spawn(10, 19)
    lv.wp(2, 19, 3, 19, ground=True, label="west end")  # the route goes west first
    lv.wp(30, 19, 32, 19, ground=True, label="east")
    f = SC.probe_skip(SC.from_level(lv), -1, 1)
    assert f.verdict == SC.PROVEN and f.found_s < f.designed_s * SC.SHORTER


def _room():
    lv = Level(998, "stone")
    lv.rect(0, 20, 30, 23)
    lv.rect(9, 14, 21, 14)  # a ceiling over the room
    lv.rect(15, 15, 15, 18)  # a wall with a door under it
    lv.rect(8, 10, 8, 19)
    lv.rect(22, 10, 22, 19)
    lv.spawn(11, 19)
    lv.wp(12, 19, 13, 19, ground=True, label="west room")
    lv.wp(18, 19, 20, 19, ground=True, label="east room")
    lv.obstacle("door", 15, 19, 15, 19, "west room", "east room", area=(9, 15, 21, 19))
    return lv


def test_an_obstacle_with_no_way_round_is_refuted():
    r = SC.from_level(_room())
    assert SC.probe_obstacle(r, r.obstacles[0]).verdict == SC.REFUTED


def test_an_obstacle_with_a_way_round_is_proven():
    lv = _room()
    lv.carve(15, 15, 15, 15)  # a second gap high in the wall
    lv.rect(16, 16, 17, 16)  # a step east of it: up, through and down
    r = SC.from_level(lv)
    f = SC.probe_obstacle(r, r.obstacles[0], nodes=40000)
    assert f.verdict in (SC.PROVEN, SC.NOT_PROVEN)
    assert SC.tile_path(r.states[r.arrivals[0]], r.waypoints[1], r.solids, frozenset({(15, 19)}), (9, 15, 21, 19))


def test_the_place_decides_when_a_banner_was_jumped_past():
    xs = [100, 500, 900]  # banner 0, 1, 2 (px)
    lines = [
        {"event": "death", "pos": [300, 0], "checkpoints": [], "session": "s", "map": "m"},  # in element 0
        {
            "event": "death",
            "pos": [700, 0],
            "checkpoints": [0],
            "session": "s",
            "map": "m",
        },  # in 1: banner 1 not touched
        {"event": "clear", "pos": [1200, 0], "checkpoints": [0, 2], "session": "s", "map": "m"},
    ]
    cs = CO.counts(lines, 3, map_hash="m", banner_xs=xs)
    assert [(c.deaths, c.passes) for c in cs] == [(1, 1), (1, 1), (0, 1)]


def test_a_capped_crag_has_no_face_to_climb_over():
    from tools.worlds.kits.mars import tooth

    plain, capped = Level(951, "mars"), Level(952, "mars")
    for lv, cap in ((plain, 0), (capped, 4)):
        lv.rect(0, 28, 40, 30)
        tooth(lv, 20, 28, 6, cap=cap)
    assert any(f[0] == 20 and f[1] == -1 for f in SC.climbable_faces(plain.solids()))
    assert not any(f[1] == -1 and 16 <= f[0] <= 20 for f in SC.climbable_faces(capped.solids()))
    assert (16, 21) in capped.solid and (16, 22) in capped.solid  # two rows thick, four tiles out
