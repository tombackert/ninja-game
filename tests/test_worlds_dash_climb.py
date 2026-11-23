"""The rating plays as players play: no dash wall climb (docs/level-building-process-brainstorm.md, step 3)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

from tools.worlds import physics as ph  # noqa: E402
from tools.worlds import route  # noqa: E402
from tools.worlds import windows as W  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402
from tools.worlds.planner import Waypoint, dash_climb_press, dash_climbs, plan_segment  # noqa: E402


def _block(h: int) -> ph.Terrain:
    """Flat ground with a sheer block `h` rows tall and 3 wide."""
    s = {(x, y) for x in range(-10, 40) for y in (20, 21)}
    s |= {(x, y) for x in range(15, 18) for y in range(20 - h, 20)}
    return ph.Terrain(s)


def _standing(solids, tx=10):
    s = ph.spawn_state(tx * 16, 19 * 16 + 1)
    for _ in range(60):
        s, _down, _dead = ph.step(s, 0, solids)
    return s


def _on_the_wall(solids):
    """Sliding down the block's west face, holding toward it."""
    s = ph.spawn_state(15 * 16 - ph.PW, 15 * 16)
    for _ in range(8):
        s, _down, _dead = ph.apply_frame(s, 1, False, False, solids)
    assert s[ph.WALL]
    return s


def test_a_wall_jump_during_an_active_dash_is_the_trick():
    solids = _block(8)
    wall = _on_the_wall(solids)
    assert not dash_climb_press(wall, False, solids)  # a plain wall jump
    assert dash_climb_press(wall, True, solids)  # with a dash pressed in the same frame
    dashing = wall[: ph.DASH] + (55,) + wall[ph.DASH + 1 :]
    assert dash_climb_press(dashing, False, solids)
    cooling = wall[: ph.DASH] + (40,) + wall[ph.DASH + 1 :]
    assert not dash_climb_press(cooling, False, solids)  # the dash is over: the push-off applies
    assert not dash_climb_press(_standing(solids), True, solids)  # a jump off the ground


def test_the_planner_climbs_a_tall_block_only_with_the_trick():
    solids = _block(6)
    s = _standing(solids)
    goal = Waypoint(15, 13, 17, 13, ground=True)
    full = plan_segment(s, goal, solids, weight=5.0, max_expand=20000, kill_y=solids.kill_y)
    assert full.ok and dash_climbs(s, full.frames, solids) > 0
    player = plan_segment(s, goal, solids, weight=5.0, max_expand=20000, kill_y=solids.kill_y, no_dash_climb=True)
    assert not player.ok


def test_a_low_block_is_climbed_without_the_trick():
    solids = _block(3)
    s = _standing(solids)
    goal = Waypoint(15, 16, 17, 16, ground=True)
    choice = W.most_forgiving(s, [goal], solids, dash_climb=False, nodes=4000)
    assert choice is not None and dash_climbs(s, choice.frames, solids) == 0


def test_seeds_that_use_the_trick_are_left_out():
    solids = _block(6)
    s = _standing(solids)
    goal = Waypoint(15, 13, 17, 13, ground=True)
    trick = plan_segment(s, goal, solids, weight=5.0, max_expand=20000, kill_y=solids.kill_y).frames
    assert W.most_forgiving(s, [goal], solids, seeds=[trick], dash_climb=False, nodes=2000) is None
    with_it = W.most_forgiving(s, [goal], solids, seeds=[trick], dash_climb=True, nodes=2000)
    assert with_it is not None


def _tall_block_level(h: int) -> Level:
    lv = Level(996, "stone")
    lv.rect(-10, 20, 40, 21)
    lv.rect(15, 20 - h, 17, 19)
    lv.spawn(10, 19)
    lv.wp(15, 19 - h, 17, 19 - h, ground=True, label="block top")
    lv.wp(25, 19, 27, 19, ground=True, label="beyond")
    return lv


def test_an_element_that_needs_the_trick_is_flagged_and_rated_with_it(monkeypatch):
    # a smaller budget for the deep search, so the test stays quick
    monkeypatch.setattr(route, "TRIES", tuple((n, {**kw, "max_expand": 3000}) for n, kw in route.TRIES))
    lv = _tall_block_level(6)
    r = W.profile_built(lv, dash_climb=False)
    assert r is not None
    assert r["trick_elements"] == ["block top"]
    full = W.profile_built(lv, dash_climb=True)
    assert full["trick_elements"] == []


def test_the_rating_plays_without_the_trick_by_default():
    assert W.DASH_CLIMB is False
