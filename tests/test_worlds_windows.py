"""tools.worlds.windows and tools.worlds.calibrate: timing windows, the most
forgiving way through an element, the time to a first clear and replays
played back in the physics replica."""

import json

import pytest

from tools.worlds import physics as ph
from tools.worlds import windows as W
from tools.worlds.builder import Level
from tools.worlds.calibrate import human_run, human_elements, visits

# --- programs and their presses ------------------------------------------------------


def test_events_are_jump_dash_presses_and_direction_changes():
    frames = [(0, False, False), (1, False, False), (1, True, False), (1, False, True), (0, False, False)]
    assert W.events(frames) == [
        W.Event(1, "move"),
        W.Event(2, "jump"),
        W.Event(3, "dash"),
        W.Event(4, "move"),
    ]


def test_a_press_moves_alone_or_with_everything_after_it():
    frames = [(1, False, False)] * 3 + [(1, True, False)] + [(1, False, False)] * 3 + [(0, False, False)]
    jump = W.Event(3, "jump")
    alone = W.shifted(frames, jump, 2, carry=False)
    assert [i for i, f in enumerate(alone) if f[1]] == [5]
    assert alone[-1] == (0, False, False) and len(alone) == len(frames)
    carried = W.shifted(frames, jump, 2, carry=True)
    assert [i for i, f in enumerate(carried) if f[1]] == [5]
    assert len(carried) == len(frames) + 2 and carried[-1] == (0, False, False)
    early = W.shifted(frames, jump, -2, carry=True)
    assert [i for i, f in enumerate(early) if f[1]] == [1] and len(early) == len(frames) - 2


def test_a_direction_change_moves_without_crossing_another():
    frames = [(1, False, False)] * 4 + [(0, False, False)] * 2 + [(-1, False, False)] * 4
    stop = W.Event(4, "move")
    assert [f[0] for f in W.shifted(frames, stop, 1, False)] == [1] * 5 + [0] + [-1] * 4
    assert [f[0] for f in W.shifted(frames, stop, -2, False)] == [1] * 2 + [0] * 4 + [-1] * 4
    assert W.shifted(frames, stop, 3, False) is None  # would swallow the turn at frame 6


# --- windows on tiny levels ----------------------------------------------------------


def _gap_level(gap: int) -> Level:
    """Ground, a gap of `gap` tiles, ground again."""
    lv = Level(995, "sand")
    lv.rect(0, 20, 9, 30)
    lv.rect(10 + gap, 20, 30 + gap, 30)
    lv.spawn(3, 19)
    lv.wp(12 + gap, 19, 14 + gap, 19, ground=True, label="far side")
    return lv


def _run_and_jump(start, edge_frames: int, total: int = 140) -> list:
    return [(1, False, False)] * edge_frames + [(1, True, False)] + [(1, False, False)] * (total - edge_frames - 1)


def _settled(lv: Level) -> tuple:
    solids = lv.solids()
    s = ph.spawn_state(lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
    for _ in range(40):
        s, _down, _dead = ph.apply_frame(s, 0, False, False, solids)
    return W.settle(s, lv.route[0], solids) or s


def test_a_wider_gap_leaves_a_narrower_window_for_the_jump():
    widths = []
    for gap, jump_at in ((2, 106), (4, 110)):  # the edge is at x 160, 112 frames from the spawn
        lv = _gap_level(gap)
        start = _settled(lv)
        ws = W.press_windows(start, _run_and_jump(start, jump_at, 200), lv.route, lv.solids())
        assert ws is not None
        jump = next(w for w in ws if w.event.kind == "jump")
        assert jump.lo <= 0 <= jump.hi
        widths.append(jump.width)
    assert widths[0] == W.FREE > widths[1]


def test_starting_to_run_from_standing_still_is_free():
    lv = _gap_level(2)
    start = _settled(lv)
    assert W.stationary(start, lv.solids())
    ws = W.press_windows(start, _run_and_jump(start, 100), lv.route, lv.solids())
    first = ws[0]
    assert first.event == W.Event(0, "move") and first.width == W.FREE


def test_a_program_that_misses_has_no_windows():
    lv = _gap_level(5)
    start = _settled(lv)
    assert W.press_windows(start, [(1, False, False)] * 200, lv.route, lv.solids()) is None


def test_a_player_over_the_void_cannot_be_saved_one_over_the_ground_can():
    lv = _gap_level(12)
    solids = lv.solids()
    s = ph.spawn_state(16 * 16, 18 * 16)
    over_void = s[: ph.VY] + (4.0, 30, 0) + s[ph.WALL :]  # falling fast, the jump used up
    assert not W.saved(over_void, solids)
    assert W.saved(_settled(lv), solids)


def test_the_most_forgiving_program_leaves_at_least_as_much_room_as_the_fastest():
    lv = _gap_level(4)
    solids = lv.solids()
    start = _settled(lv)
    fastest = W.plan_segment(start, lv.route[0], solids).frames
    fast = W.press_windows(start, fastest, lv.route, solids)
    best = W.most_forgiving(start, lv.route, solids, nodes=4000)
    assert best is not None
    assert W.narrowest(best.windows) >= W.narrowest(fast)


# --- elements and the time to a first clear ---------------------------------------------


def test_ground_waypoints_split_the_route_into_elements():
    assert W.element_spans([True, False, False, True, True]) == [(0, 0), (1, 3), (4, 4)]
    assert W.element_spans([False, False]) == [(0, 1)]


def test_a_press_with_a_wide_window_never_misses():
    assert W.p_hit(W.FREE, 2.0) == 1.0
    assert W.p_hit(2, 1.0) < W.p_hit(4, 1.0) < W.p_hit(8, 1.0) < 1.0
    assert W.p_hit(4, 2.0) < W.p_hit(4, 1.0)
    hit, die = W.element_odds([(3, 1.0), (W.FREE, 1.0)], 1.0)
    assert die == pytest.approx(1 - hit)
    hit, die = W.element_odds([(3, 0.0)], 1.0)
    assert die == 0 and hit < 1


def _element(label, seconds, widths, fatal=1.0):
    ws = [W.Window(W.Event(i, "jump"), -(w // 2), w - w // 2 - 1, False) for i, w in enumerate(widths)]
    return W.Element(label, label, 0, 0, True, [(0, False, False)] * int(seconds * 60), ws, [fatal] * len(ws), 0)


def test_first_clear_without_tight_presses_is_one_clean_run():
    els = [_element("a", 10, [W.FREE]), _element("b", 20, [W.FREE])]
    fc = W.first_clear(els, {"sigma": 1.0, "pace": 1.5})
    assert fc["deaths"] == 0 and fc["first_try"] == 1.0
    assert fc["minutes"] == pytest.approx(30 * 1.5 / 60, abs=0.01)


def test_tight_presses_cost_deaths_and_a_banner_before_them_saves_time():
    els = [_element("walk", 30, [W.FREE])] + [_element(f"jump {i}", 1, [3]) for i in range(4)]
    prof = {"sigma": 1.0, "pace": 1.0}
    without = W.first_clear(els, prof)
    with_banner = W.first_clear(els, prof, cuts=[1])
    assert without["deaths_without_p"] > 0.5
    assert with_banner["minutes_without_p"] < without["minutes_without_p"]
    harmless = W.first_clear([_element("walk", 30, [W.FREE])] + [_element("j", 1, [3], 0.0)] * 4, prof)
    assert harmless["deaths"] == 0 and harmless["minutes"] < without["minutes"]


def test_window_profile_counts_elements_by_their_narrowest_window():
    els = [_element("a", 1, [1]), _element("b", 1, [4, 9]), _element("c", 1, [7]), _element("d", 1, [W.FREE])]
    assert W.window_profile(els) == {"le2": 1, "le4": 1, "le8": 1, "le12": 0, "free": 1}


def test_a_profile_of_an_unsaved_level():
    lv = _gap_level(3)
    lv.wp(25, 19, 27, 19, ground=True, label="end")
    r = W.profile_built(lv)
    assert r["elements"] == 2
    assert set(r["first_clear"]) == set(W.PROFILES)
    assert sum(r["windows"].values()) == 2
    assert r["first_clear"]["expert"]["minutes"] > 0
    assert 0 <= r["exposed"] <= sum(len(e[3]) for e in r["element_list"])


# --- replays played back in the replica ----------------------------------------------------


def _record(lv: Level, frames: list, kinds: dict, tmp_path) -> str:
    """A replay file as the game writes it: key events per tick (Space and Up both
    'jump'; `kinds` says which ones are dashes) and a snapshot every 10 ticks."""
    solids = lv.solids()
    s = _settled(lv)
    inputs, snaps = [], {}
    held = 0
    for t, (m, j, d) in enumerate(frames):
        if t % 10 == 0:
            snaps[str(t)] = {
                "players": [
                    {
                        "pos": [s[ph.X], s[ph.Y]],
                        "velocity": [s[ph.VX], s[ph.VY]],
                        "air_time": s[ph.AIR],
                        "jumps": s[ph.JUMPS],
                        "wall_slide": s[ph.WALL],
                        "dashing": s[ph.DASH],
                        "flip": s[ph.FLIP],
                        "lives": 3,
                        "breath": s[ph.BREATH],
                        "swim_cooldown": s[ph.SWIM],
                    }
                ]
            }
        acts = []
        if m != held:
            if held:
                acts.append("stop_right" if held > 0 else "stop_left")
            if m:
                acts.append("right" if m > 0 else "left")
            held = m
        if j or d:
            acts.append("jump")
        inputs.append({"tick": t, "inputs": acts})
        s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
    path = tmp_path / "replay.json"
    path.write_text(json.dumps({"duration_frames": len(frames), "inputs": inputs, "snapshots": snaps}))
    return str(path)


def test_a_replay_is_played_back_exactly_with_dashes_told_from_jumps(tmp_path):
    lv = _gap_level(5)  # too wide to jump: a dash carries the player over
    solids = lv.solids()
    frames = [(0, False, False)] * 12 + [(1, False, False)] * 80 + [(1, True, False)] + [(1, False, False)] * 15
    frames += [(1, False, True)] + [(1, False, False)] * 60
    path = _record(lv, frames, {}, tmp_path)
    run = human_run(995, path, solids)
    assert run.fidelity[0] == run.fidelity[1] > 10
    assert [i for i, f in enumerate(run.frames) if f[2]] == [108]  # the second "jump" was Space
    assert [i for i, f in enumerate(run.frames) if f[1]] == [92]
    v = visits(run, lv.route)
    assert v[0] is not None
    (piece,) = human_elements(run, lv.route, [(0, 0)], solids)
    assert piece.frames == v[0] and piece.narrowest is not None


def test_the_profile_fit_reproduces_a_sessions_first_tries_and_lost_minutes():
    from tools.worlds.calibrate import LAPSES, SIGMAS, Observation, fit_precision

    def level(tight: int):
        els = [_element("walk", 50, [W.FREE])] + [_element(f"gap {i}", 2, [3, 13]) for i in range(tight)]
        return {"elements": els, "boxes": [], "solids": None, "humans": []}

    data = {1: level(0), 2: level(2), 3: level(6), 4: level(10)}
    # clean first tries on the easy two; the hard two cost 30 s and 60 s of failed attempts
    obs = [
        Observation(1, "expert", 50.0, 52.0, True, 0, 0),
        Observation(2, "expert", 54.0, 56.0, True, 0, 0),
        Observation(3, "expert", 62.0, 94.0, False, 0, 0),
        Observation(4, "expert", 70.0, 132.0, False, 0, 0),
    ]
    fit = fit_precision(data, obs, "expert", {"pace": 1.0})
    assert fit["sigma"] in SIGMAS and fit["lapse"] in LAPSES
    assert fit["first_tries"][1] == 2 and abs(fit["first_tries"][0] - 2) < 0.6
    assert fit["minutes_lost"][1] == 1.5 and abs(fit["minutes_lost"][0] - 1.5) < 0.5
