"""Checkpoints (banners that move the respawn point) and the fall that ends at the kill line."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402
import pytest  # noqa: E402

from game import Game  # noqa: E402
from scripts.checkpoints import FURLED, HOISTED, find_checkpoints, touch  # noqa: E402
from scripts.constants import AIR_TIME_FATAL, FALL_KILL_DEPTH, RESPAWN_DEAD_THRESHOLD  # noqa: E402
from scripts.tilemap import Tilemap  # noqa: E402
from tools.worlds import physics as ph  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402

MAP_ID = 9001
GROUND = 20


def _build() -> Level:
    """Ground, a pit, ground with two checkpoints, the flag."""
    lv = Level(MAP_ID, "sand")
    lv.rect(0, GROUND, 10, GROUND + 3)
    lv.rect(14, GROUND, 50, GROUND + 3)
    lv.spawn(2, GROUND - 1)
    lv.checkpoint(20, GROUND - 1)
    lv.checkpoint(35, GROUND - 1)
    lv.decor(5, GROUND + 9, 0)  # far below: decor does not hold anyone
    lv.flag(48, GROUND - 1)
    return lv


@pytest.fixture
def g(tmp_path, monkeypatch):
    """A game whose map MAP_ID is the level built above."""
    _build().save(str(tmp_path))
    load = Tilemap.load

    def redirected(self, path, *a, **k):
        target = str(tmp_path / f"{MAP_ID}.json") if path.endswith(f"/{MAP_ID}.json") else path
        result = load(self, target, *a, **k)
        self.loaded_path = path
        return result

    monkeypatch.setattr(Tilemap, "load", redirected)
    pygame.init()
    game = Game()
    game.load_level(MAP_ID)
    return game


def _walk_to(g, x_px, limit=600):
    """Run east from past the pit until x_px."""
    g.player.pos = [15 * 16.0, (GROUND - 1) * 16.0]
    g.movement = [False, True]
    for _ in range(limit):
        g.step()
        if g.player.pos[0] >= x_px:
            break
    g.movement = [False, False]


def _die(g):
    """Fall out of the level: step until dead, then respawn as GameState does."""
    p = g.player
    p.pos = [12 * 16.0, (GROUND - 2) * 16.0]  # over the pit
    p.velocity = [0, 0]
    frames = 0
    while not g.dead:
        g.step()
        frames += 1
        assert frames < AIR_TIME_FATAL
    g.load_level(MAP_ID, p.lives, respawn=True)
    return frames


def test_the_kill_line_lies_under_the_lowest_solid_tile(g):
    assert g.tilemap.kill_y == (GROUND + 3 + FALL_KILL_DEPTH) * 16


def test_a_fall_out_of_the_level_ends_long_before_the_air_time_runs_out(g):
    frames = _die(g)
    assert frames < AIR_TIME_FATAL / 4
    assert frames + RESPAWN_DEAD_THRESHOLD < 2 * 60


def test_the_replica_ends_the_fall_at_the_same_line():
    lv = _build()
    terrain = lv.solids()
    assert terrain.kill_y == (GROUND + 3 + FALL_KILL_DEPTH) * 16
    s = ph.spawn_state(12 * 16, (GROUND - 2) * 16)
    for frame in range(AIR_TIME_FATAL):
        s, _down, dead = ph.apply_frame(s, 0, False, False, terrain)
        if dead:
            break
    assert dead and frame < AIR_TIME_FATAL / 4 and s[ph.Y] > terrain.kill_y


def test_banners_are_found_west_to_east_with_their_respawn_points(g):
    assert [cp.respawn for cp in g.checkpoints] == [(20 * 16, (GROUND - 1) * 16), (35 * 16, (GROUND - 1) * 16)]
    assert all(cp.tile["variant"] == FURLED for cp in g.checkpoints)


def test_touching_a_banner_hoists_it_and_moves_the_respawn_point(g):
    _walk_to(g, 21 * 16)
    first = g.checkpoints[0]
    assert first.hoisted and not g.checkpoints[1].hoisted
    assert g.player.respawn_pos == list(first.respawn)


def test_an_earlier_banner_touched_again_does_not_move_the_respawn_point_back(g):
    _walk_to(g, 36 * 16)
    assert g.player.respawn_pos == list(g.checkpoints[1].respawn)
    g.player.pos = [20 * 16.0, (GROUND - 1) * 16.0]
    g.step()
    assert g.player.respawn_pos == list(g.checkpoints[1].respawn)


def test_a_respawn_comes_back_at_the_checkpoint_and_the_banner_stays_hoisted(g):
    _walk_to(g, 21 * 16)
    _die(g)
    assert g.player.pos == list(g.checkpoints[0].respawn)
    assert g.checkpoints[0].hoisted


def test_a_new_start_of_the_level_furls_the_banners_and_starts_at_the_spawn(g):
    _walk_to(g, 21 * 16)
    g.load_level(MAP_ID)
    assert not any(cp.hoisted for cp in g.checkpoints)
    assert g.player.respawn_pos == [2 * 16, (GROUND - 1) * 16]


def test_each_player_keeps_their_own_checkpoints():
    class P:
        def __init__(self, x):
            self.pos = [x, 0]
            self.respawn_pos = [0, 0]

        def rect(self):
            return pygame.Rect(int(self.pos[0]), int(self.pos[1]), 8, 15)

    tm = Tilemap(None)
    tm.offgrid_tiles = [{"type": "checkpoint", "variant": 0, "pos": [100, 0]}]
    cps = find_checkpoints(tm)
    a, b = P(100), P(100)
    assert touch(cps, a) is cps[0]
    assert touch(cps, a) is None  # once per player
    assert touch(cps, b) is cps[0]  # the other player still gets it
    assert cps[0].tile["variant"] == HOISTED
    assert a.respawn_pos == b.respawn_pos == [100, 16]


def test_the_server_respawns_a_player_at_their_last_checkpoint(tmp_path, monkeypatch):
    from scripts.network.headless_game import HeadlessGame

    _build().save(str(tmp_path))
    load = Tilemap.load
    monkeypatch.setattr(
        Tilemap,
        "load",
        lambda self, path, *a, **k: load(
            self, str(tmp_path / f"{MAP_ID}.json") if str(MAP_ID) in path else path, *a, **k
        ),
    )
    pygame.init()
    hg = HeadlessGame(MAP_ID)
    walker, stayer = hg.add_player(1), hg.add_player(2)
    walker.pos = [20 * 16.0, (GROUND - 1) * 16.0]
    hg.simulate_tick()
    assert walker.respawn_pos == list(hg.checkpoints[0].respawn)
    for p in (walker, stayer):
        p.pos = [12 * 16.0, (GROUND - 2) * 16.0]  # over the pit
    for _ in range(AIR_TIME_FATAL // 4):
        hg.simulate_tick()
    # back at their respawn points (and settled on the ground there since)
    assert walker.pos[0] == hg.checkpoints[0].respawn[0] and abs(walker.pos[1] - hg.checkpoints[0].respawn[1]) < 16
    assert stayer.pos[0] == 2 * 16 and abs(stayer.pos[1] - (GROUND - 1) * 16) < 16


def test_the_builder_puts_the_banner_offgrid_standing_on_the_ground():
    lv = _build()
    banners = [t for t in lv.offgrid if t["type"] == "checkpoint"]
    assert banners[0]["pos"] == [20 * 16, (GROUND - 2) * 16]
    with pytest.raises(ValueError):
        lv.checkpoint(3, GROUND)  # inside the ground
