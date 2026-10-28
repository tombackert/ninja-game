"""Water world: the water layer, swimming, breath and currents."""

import json
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402
import pytest  # noqa: E402

from game import Game  # noqa: E402
from scripts.constants import (  # noqa: E402
    AIR_TIME_FATAL,
    BREATH_FRAMES,
    JUMP_VELOCITY,
    SWIM_STROKE_COOLDOWN,
    SWIM_STROKE_VELOCITY,
    WATER_DASH_SPEED,
    WATER_DRAG,
    WATER_GRAVITY,
)
from scripts.snapshot import SnapshotService  # noqa: E402
from scripts.tilemap import Tilemap  # noqa: E402
from scripts.water import DEPTH_ALPHA, WATER_COLOR, water_from_rows, water_to_rows  # noqa: E402

SURFACE = 10  # first water row of the pool
FLOOR = 40


def _solid(x, y):
    return {"type": "reef", "variant": 1, "pos": [x, y]}


@pytest.fixture
def g():
    pygame.init()
    game = Game()
    game.enemies.clear()
    return game


def pool(g, flow=0, surface=SURFACE):
    """Walled pool 20 tiles wide, water from row `surface` down to the floor."""
    tm = g.tilemap
    tm.tilemap = {f"{x};{FLOOR}": _solid(x, FLOOR) for x in range(0, 22)}
    for y in range(0, FLOOR):
        tm.tilemap[f"0;{y}"] = _solid(0, y)
        tm.tilemap[f"21;{y}"] = _solid(21, y)
    tm.water = {(x, y): flow for x in range(1, 21) for y in range(surface, FLOOR)}
    tm._water_renderer = None
    g.flags = []
    p = g.player
    p.pos = [160.0, (SURFACE + 5) * 16.0]  # well under the surface
    p.velocity = [0, 0]
    p.air_time = 0
    p.dashing = 0
    return p


def steps(g, n, right=False):
    g.movement = [False, right]
    for _ in range(n):
        g.step()


def test_map_rows_round_trip():
    water = {(3, 5): 0, (4, 5): 0, (5, 5): 1, (6, 5): 1, (3, 6): 0, (9, 6): 3}
    rows = water_to_rows(water)
    assert rows == [[5, 3, 4, 0], [5, 5, 6, 1], [6, 3, 3, 0], [6, 9, 9, 3]]
    assert water_from_rows(rows) == water


def test_map_file_keeps_the_water_layer(g, tmp_path):
    pool(g, flow=4)
    path = str(tmp_path / "pool.json")
    g.tilemap.save(path)
    loaded = Tilemap(g)
    loaded.load(path, load_entities=False)
    assert loaded.water == g.tilemap.water
    assert loaded.water_at((5 * 16 + 3, SURFACE * 16)) == 4
    assert loaded.water_at((5 * 16, (SURFACE - 1) * 16)) is None


def test_dry_maps_are_saved_without_a_water_layer(g, tmp_path):
    path = str(tmp_path / "dry.json")
    g.tilemap.save(path)
    with open(path) as f:
        assert "water" not in json.load(f)["map_data"]


def test_sinks_slowly_and_never_falls_to_death(g):
    p = pool(g)
    p.breath = 10**6  # only the fall timer matters here
    terminal = WATER_GRAVITY / (1 - WATER_DRAG)
    for _ in range(AIR_TIME_FATAL + 60):
        steps(g, 1)
        assert p.air_time == 0
        assert p.velocity[1] <= terminal + 1e-9
    assert g.dead == 0
    assert p.collisions["down"]  # sank to the floor


def test_holding_breath_runs_out_and_drowns(g):
    p = pool(g)
    steps(g, BREATH_FRAMES - 1)
    assert g.dead == 0 and p.breath == 1
    steps(g, 1)
    assert g.dead > 0


def test_breath_refills_with_the_head_above_the_surface(g):
    p = pool(g)
    steps(g, 100)
    assert p.breath == BREATH_FRAMES - 100
    p.pos = [160.0, SURFACE * 16.0 - 4]  # center in the water, eyes above it
    p.velocity = [0, 0]
    steps(g, 1)
    assert p.breath == BREATH_FRAMES


def test_drowning_respawns_with_full_breath(g):
    p = pool(g)
    p.respawn_pos = [32.0, (SURFACE - 3) * 16.0]
    steps(g, BREATH_FRAMES)
    g.load_level(g.level, p.lives, respawn=True)
    assert p.breath == BREATH_FRAMES and p.swim_cooldown == 0


def test_swim_stroke_and_its_cooldown(g):
    p = pool(g)
    steps(g, 5)
    assert p.jump() is True
    assert p.velocity[1] == SWIM_STROKE_VELOCITY
    assert not p.jump()  # still recovering from the stroke
    steps(g, SWIM_STROKE_COOLDOWN)
    assert p.jump() is True


def test_strokes_rise_and_never_use_up_the_jump(g):
    p = pool(g)
    p.pos[1] = (SURFACE + 20) * 16.0  # deep enough to stay under for 10 strokes
    y0 = p.pos[1]
    for _ in range(10):
        p.jump()
        steps(g, SWIM_STROKE_COOLDOWN)
    assert p.pos[1] < y0 - 5 * 16
    assert p.jumps == 1


def test_leaps_out_with_the_head_above_the_surface(g):
    p = pool(g)
    p.pos = [160.0, SURFACE * 16.0 - 4]
    p.jumps = 1
    assert p.jump() is True
    assert p.velocity[1] == JUMP_VELOCITY and p.jumps == 0
    steps(g, 30)
    assert p.pos[1] < (SURFACE - 2) * 16  # well clear of the water


def test_moves_and_dashes_slower_in_water(g):
    p = pool(g)
    x0 = p.pos[0]
    steps(g, 10, right=True)
    assert p.pos[0] == pytest.approx(x0 + 7.0)
    p.dash()
    steps(g, 1)
    assert p.velocity[0] == pytest.approx(WATER_DASH_SPEED - 0.1)  # after this frame's friction


@pytest.mark.parametrize("flow,dx,dy", [(1, 5.0, None), (2, -5.0, None), (3, None, "up"), (4, None, "down")])
def test_currents_carry_the_player(g, flow, dx, dy):
    p = pool(g, flow=flow)
    p.breath = 10**6
    x0, y0 = p.pos
    steps(g, 10)
    if dx is not None:
        assert p.pos[0] == pytest.approx(x0 + dx)
    if dy == "up":
        assert p.pos[1] < y0 - 8
    if dy == "down":
        assert p.pos[1] > y0 + 10


def test_enemies_sink_slowly_in_water(g):
    from scripts.entities import Enemy

    pool(g)
    e = Enemy(g, (40.0, (SURFACE + 2) * 16.0), (8, 15), 99)
    for _ in range(30):
        e.update(g.tilemap, (0, 0))
    assert 0 < e.velocity[1] <= WATER_GRAVITY / (1 - WATER_DRAG) + 1e-9


def test_swimming_plays_the_swim_animation_and_breathes_out_bubbles(g):
    p = pool(g)
    steps(g, 2)
    assert p.action == "swim"
    steps(g, 60)
    assert any(part.type == "bubble" for part in g.particles)


def test_plunging_in_splashes(g):
    p = pool(g)
    p.pos = [160.0, (SURFACE - 4) * 16.0]
    p.velocity = [0, 3.0]
    before = len(g.particles)
    for _ in range(30):
        steps(g, 1)
        if p.water is not None:
            break
    assert len(g.particles) >= before + 8


def test_snapshots_carry_breath_and_stroke_cooldown(g):
    p = pool(g)
    steps(g, 50)
    p.jump()
    snap = SnapshotService.deserialize(SnapshotService.serialize(SnapshotService.capture(g)))
    assert snap.players[0].breath == BREATH_FRAMES - 50
    assert snap.players[0].swim_cooldown == SWIM_STROKE_COOLDOWN
    p.breath, p.swim_cooldown = 1, 0
    SnapshotService.restore(g, snap)
    assert p.breath == BREATH_FRAMES - 50 and p.swim_cooldown == SWIM_STROKE_COOLDOWN


def test_server_respawns_a_drowned_player():
    from scripts.network.headless_game import HeadlessGame

    hg = HeadlessGame(level=0)
    player = hg.add_player(1)
    hg.tilemap.water = {(x, y): 0 for x in range(-50, 50) for y in range(-60, 60)}
    lives = player.lives
    player.pos = [player.respawn_pos[0], player.respawn_pos[1] + 0.0]
    for _ in range(BREATH_FRAMES):
        hg.simulate_tick()
    assert player.lives == lives - 1
    assert player.breath == BREATH_FRAMES


def test_water_is_drawn_over_the_level_with_a_crest_only_under_open_air(g):
    pool(g)
    g.tilemap.tilemap["5;9"] = _solid(5, 9)  # a ceiling over one water tile
    surf = pygame.Surface((640, 360), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    g.tilemap.render_water(surf, (0, 0), tick=0)
    deep = surf.get_at((100, (SURFACE + 8) * 16 + 8))
    assert deep.a == DEPTH_ALPHA[-1] and abs(deep.b - WATER_COLOR[2]) <= 1
    assert surf.get_at((100, SURFACE * 16 + 10)).a == DEPTH_ALPHA[0]
    crest_rows = [surf.get_at((x, SURFACE * 16 + 1)).a for x in range(16, 320)]
    assert max(crest_rows) > DEPTH_ALPHA[0]  # the wave crest
    under_ceiling = [surf.get_at((x, SURFACE * 16 + 1)).a for x in range(80, 96)]
    assert set(under_ceiling) == {DEPTH_ALPHA[0]}
    assert surf.get_at((100, (SURFACE - 1) * 16)).a == 0  # air stays clear
