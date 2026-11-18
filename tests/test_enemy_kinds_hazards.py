"""Enemy kinds (scripts/enemy_kinds.py, scripts/ai/behaviors.py) and level
hazards (scripts/hazards.py): behavior, deaths by touch, the planner's view
and the level builder's API."""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()

import scripts.collectableManager as cm_module  # noqa: E402
from game import Game  # noqa: E402
from scripts.ai.behaviors import TURRET_WINDUP, _cluster_clear  # noqa: E402
from scripts.enemy_kinds import (  # noqa: E402
    GUNNER,
    JUMPER,
    KINDS,
    PATROL,
    SPAWNER_IDS,
    TURRET,
    kind_for_variant,
)
from scripts.constants import STOMP_BOUNCE_VELOCITY  # noqa: E402
from scripts.entities import SHOT_POSE_FRAMES, Enemy  # noqa: E402
from scripts.hazards import (  # noqa: E402
    CRUMBLE_DELAY,
    CRUMBLE_RETURN,
    FLAME_REACH,
    HazardSystem,
    flame_state,
)
from scripts.settings import settings  # noqa: E402
from scripts.tilemap import Tilemap  # noqa: E402
from tools.worlds import physics as ph  # noqa: E402
from tools.worlds import roster  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402

FLOOR = 20  # floor row of the test arenas


@pytest.fixture()
def game(tmp_path, monkeypatch):
    monkeypatch.setattr(cm_module, "DATA_FILE", str(tmp_path / "collectables.json"))
    g = Game()
    g.load_level(0)
    arena(g)
    return g


def arena(g, extra=None):
    """A flat stone floor on row FLOOR, x 0..39, plus `extra` tiles; the
    player stands on it at x tile 5, no enemies."""
    tm = {}
    for x in range(40):
        tm[f"{x};{FLOOR}"] = {"type": "stone", "variant": 1, "pos": [x, FLOOR]}
    for (x, y), tile in (extra or {}).items():
        tm[f"{x};{y}"] = {"pos": [x, y], **tile}
    g.tilemap.tilemap = tm
    g.tilemap.offgrid_tiles = []
    g.tilemap.kill_y = g.tilemap.kill_line()
    g.hazards = HazardSystem(g.tilemap)
    g.enemies = []
    g.projectiles.clear()
    g.dead = 0
    p = g.player
    p.pos = [5 * 16 + 4, FLOOR * 16 - 15]
    p.velocity = [0, 0]
    p.dashing = 0
    p.collisions = {"up": False, "down": True, "right": False, "left": False}
    return g


def enemy_at(g, tx, kind, flip=False):
    e = Enemy(g, (tx * 16 + 4, FLOOR * 16 - 15), (8, 15), 900 + len(g.enemies), kind=kind)
    e.flip = flip
    e.collisions = {"up": False, "down": True, "right": False, "left": False}
    g.enemies.append(e)
    return e


# --- kinds ----------------------------------------------------------------------------------


def test_spawner_variant_names_the_kind():
    assert kind_for_variant(1) is GUNNER
    assert [kind_for_variant(v).name for v in (2, 3, 4, 5, 6)] == ["patrol", "turret", "chaser", "jumper", "thrower"]
    assert kind_for_variant(99) is GUNNER  # unknown: the classic enemy
    assert SPAWNER_IDS == [("spawners", v) for v in range(7)]


def test_game_spawns_each_kind_from_its_spawner(game):
    g = game
    for i, variant in enumerate((1, 2, 3, 4, 5, 6)):
        g.tilemap.tilemap[f"{10 + i * 3};{FLOOR - 1}"] = {
            "type": "spawners",
            "variant": variant,
            "pos": [10 + i * 3, FLOOR - 1],
        }
    spawners = g.tilemap.extract(SPAWNER_IDS)
    kinds = [g._spawn_enemy(s, i).kind.name for i, s in enumerate(spawners)]
    assert sorted(kinds) == sorted(KINDS)


def _pixels(surface):
    return pygame.image.tobytes(surface, "RGB")


def test_each_kind_has_its_own_character(game):
    gunner = {_pixels(img) for img in game.assets["enemy/idle"].images}
    seen = set()
    for kind in KINDS:
        if kind == "gunner":
            continue
        for action in ("idle", "run"):
            frames = game.assets[f"enemy/{kind}/{action}"].images
            assert all(img.get_size() == (14, 18) for img in frames)
            assert len({_pixels(img) for img in frames}) > 1, f"{kind} {action} does not move"
        first = _pixels(game.assets[f"enemy/{kind}/idle"].images[0])
        assert first not in gunner and first not in seen  # not a copy of another kind
        seen.add(first)


def test_turret_scans_locks_on_and_recoils(game):
    e = enemy_at(game, 39, "turret")
    game.player.pos[0] = 39 * 16 - TURRET.sight_x - 40  # out of sight
    e.update(game.tilemap)
    assert e.action == "idle"
    game.player.pos[0] = 30 * 16  # in sight
    e.update(game.tilemap)
    assert e.action == "alert"
    for _ in range(TURRET_WINDUP):
        e.update(game.tilemap)
    assert e.since_shot == 0 and e.action == "shoot"
    assert e.animation.images == game.assets["enemy/turret/shoot"].images
    for _ in range(SHOT_POSE_FRAMES):
        e.update(game.tilemap)
    assert e.action == "alert"


def test_a_kind_without_an_animation_shows_its_idle(game):
    jumper = enemy_at(game, 12, "jumper")
    jumper.set_action("alert")
    assert jumper.animation.images == game.assets["enemy/jumper/idle"].images
    gunner = enemy_at(game, 14, "gunner")
    gunner.set_action("shoot")
    assert gunner.animation.images == game.assets["enemy/idle"].images


def test_one_hop_plays_once_and_a_shot_pose_does_not_loop(game):
    assert not game.assets["enemy/jumper/run"].loop
    assert not game.assets["enemy/thrower/shoot"].loop
    assert game.assets["enemy/patrol/run"].loop


@pytest.mark.parametrize("level", [0, 30])
def test_bullet_speed_is_the_kinds_not_the_levels(game, level):
    old = settings._selected_level
    settings._selected_level = level
    try:
        e = enemy_at(game, 12, "gunner")
        e.policy = type("P", (), {"decide": lambda self, ent, ctx: {"shoot": True, "shoot_direction": 1}})()
        e.update(game.tilemap)
        shots = list(game.projectiles)
        assert len(shots) == 1 and shots[0]["vel"][0] == GUNNER.bullet_speed
    finally:
        settings._selected_level = old


def test_unarmed_kinds_never_fire(game):
    e = enemy_at(game, 12, "patrol")
    e.policy = type("P", (), {"decide": lambda self, ent, ctx: {"shoot": True, "shoot_direction": 1}})()
    e.update(game.tilemap)
    assert len(list(game.projectiles)) == 0


def test_patrol_walks_edge_to_edge_without_stopping(game):
    g = arena(game, {(x, FLOOR): {"type": "stone", "variant": 1} for x in range(40)})
    for x in range(14, 40):  # a platform x 0..13
        del g.tilemap.tilemap[f"{x};{FLOOR}"]
    e = enemy_at(g, 8, "patrol")
    turned = 0
    for _ in range(1000):
        before = e.flip
        e.update(g.tilemap)
        turned += e.flip != before
        assert e.rect().centerx < 14 * 16  # never walks off the edge
    assert turned >= 2


def test_turret_fires_on_a_fixed_beat(game):
    e = enemy_at(game, 15, "turret")
    shots = []
    for frame in range(1, 400):
        before = len(list(game.projectiles))
        e.update(game.tilemap)
        if len(list(game.projectiles)) > before:
            shots.append(frame)
    assert shots[0] == TURRET_WINDUP + 1
    assert {b - a for a, b in zip(shots, shots[1:])} == {TURRET.fire_period}
    assert e.flip  # faces the player (to its left)


def test_turret_is_silent_out_of_sight(game):
    e = enemy_at(game, 39, "turret")
    game.player.pos[0] = 39 * 16 - TURRET.sight_x - 40
    for _ in range(300):
        e.update(game.tilemap)
    assert len(list(game.projectiles)) == 0


def test_a_cluster_spreads_its_shots(game):
    a = enemy_at(game, 12, "gunner")
    b = enemy_at(game, 13, "gunner")
    far = enemy_at(game, 30, "gunner")
    assert _cluster_clear(b)
    a.since_shot = 0
    assert not _cluster_clear(b)
    assert _cluster_clear(far)


def test_chaser_wakes_runs_at_the_player_and_stops_at_the_edge(game):
    g = arena(game)
    for x in range(20, 40):  # floor x 0..19
        del g.tilemap.tilemap[f"{x};{FLOOR}"]
    e = enemy_at(g, 15, "chaser")
    g.player.pos[0] = 7 * 16  # 8 tiles away, in sight
    e.update(g.tilemap)
    assert e.awake and e.pos[0] < 15 * 16 + 4
    g.player.pos[0] = 30 * 16  # over the gap to the right
    for _ in range(200):
        e.update(g.tilemap)
    assert e.rect().right <= 20 * 16 + 8  # waits at the edge


def test_jumper_hops_and_turns_before_a_gap(game):
    g = arena(game)
    e = enemy_at(g, 10, "jumper")
    ys = []
    for _ in range(240):
        e.update(g.tilemap)
        ys.append(e.pos[1])
    assert min(ys) < FLOOR * 16 - 15 - 16  # hops higher than a tile
    for x in range(12, 40):  # now a gap right after x 11
        g.tilemap.tilemap.pop(f"{x};{FLOOR}", None)
    e.pos = [10 * 16 + 4, FLOOR * 16 - 15]
    e.velocity = [0, 0]
    e.flip = False
    e.cooldown = 0
    e.collisions["down"] = True
    for _ in range(400):
        e.update(g.tilemap)
        assert e.pos[1] < FLOOR * 16  # never falls into the gap
    assert JUMPER.hop_velocity < 0


def test_touch_kinds_hurt_unless_dashing(game):
    p = game.player
    e = enemy_at(game, 5, "patrol")
    e.pos = list(p.pos)
    assert p.touch_damage() == ("enemy", e.rect().centerx)
    p.dashing = 60
    assert p.touch_damage() is None
    p.dashing = 0
    e.kind = GUNNER  # bullets, not touch
    assert p.touch_damage() is None
    assert PATROL.contact and not GUNNER.contact


def test_touching_a_patrol_costs_a_life_not_a_respawn(game):
    p = game.player
    e = enemy_at(game, 5, "patrol")
    e.pos = [p.pos[0] + 6, p.pos[1]]  # just right of the player
    lives, pos = p.lives, list(p.pos)
    game.step()
    assert not game.dead
    assert p.lives == lives - 1
    assert p.invulnerable > 0 and p.velocity[0] < 0 and p.velocity[1] < 0  # thrown left and up
    assert abs(p.pos[0] - pos[0]) < 16  # still where it happened
    for _ in range(30):  # blinking: touching it again costs nothing
        e.pos = list(p.pos)
        game.step()
    assert p.lives == lives - 1


def test_a_shield_takes_a_touch_hit(game):
    p = game.player
    game.cm.shield = 1
    p.shield_ready = True
    assert p.take_hit("enemy", p.rect().centerx + 4)
    assert game.cm.shield == 0 and p.invulnerable > 0
    assert not p.take_hit("enemy", p.rect().centerx + 4)  # still blinking


def test_bullets_miss_a_blinking_player(game):
    p = game.player
    lives = p.lives
    p.invulnerable = 30
    r = p.rect()
    game.projectiles.spawn(r.centerx, r.centery, 0.0, "enemy")
    game.projectiles.update(game.tilemap, [p], [])
    assert p.lives == lives
    p.invulnerable = 0
    game.projectiles.update(game.tilemap, [p], [])
    assert p.lives == lives - 1 and p.invulnerable > 0


def drop_onto(g, e, vy=3.0):
    """Put the player just above enemy `e`, falling."""
    p = g.player
    p.pos = [e.pos[0], e.pos[1] - 16]
    p.velocity = [0, vy]
    p.collisions = {"up": False, "down": False, "right": False, "left": False}
    return p


@pytest.mark.parametrize("kind", ["patrol", "gunner", "turret", "chaser", "jumper", "thrower"])
def test_landing_on_an_enemy_kills_it_and_bounces(game, kind):
    e = enemy_at(game, 8, kind)
    p = drop_onto(game, e)
    lives, coins = p.lives, game.cm.coins
    game.step()
    assert e not in game.enemies
    assert p.lives == lives and p.invulnerable == 0
    assert p.velocity[1] == STOMP_BOUNCE_VELOCITY
    assert game.cm.coins == coins + 1


def test_a_bounce_is_lighter_than_a_jump(game):
    e = enemy_at(game, 8, "patrol")
    p = drop_onto(game, e)
    game.step()
    top = p.pos[1]
    for _ in range(40):
        game.step()
        top = min(top, p.pos[1])
    bounce = e.pos[1] - 16 - top
    assert 0 < bounce < 16 * 2  # up a little, less than a jump's height


def test_jumping_up_into_a_patrol_is_a_hit_not_a_stomp(game):
    e = enemy_at(game, 8, "patrol")
    e.pos[1] -= 40  # up in the air (it does not fall far in one frame)
    p = game.player
    p.pos = [e.pos[0], e.pos[1] + 6]  # head inside its feet, going up
    p.velocity = [0, -3]
    p.collisions = {"up": False, "down": False, "right": False, "left": False}
    lives = p.lives
    game.step()
    assert e in game.enemies
    assert p.lives == lives - 1


def test_a_predicting_client_bounces_but_leaves_the_kill_to_the_server(game):
    game.predicting = True
    e = enemy_at(game, 8, "patrol")
    p = drop_onto(game, e)
    lives, coins = p.lives, game.cm.coins
    game.step()
    assert e in game.enemies and e.stomped
    assert p.velocity[1] == STOMP_BOUNCE_VELOCITY
    for _ in range(5):  # rising out of it: the stomped enemy does not hurt
        game.step()
    assert p.lives == lives and game.cm.coins == coins


def test_the_server_credits_the_stomper():
    from scripts.network.headless_game import HeadlessGame

    hg = HeadlessGame(level=0)
    p = hg.add_player(1)
    p.pos[1] -= 48  # in the air above its spawn
    e = Enemy(hg, (p.pos[0], p.pos[1] + 16), (8, 15), 999, kind="patrol")
    hg.enemies = [e]
    hg.collectables = {}
    p.velocity = [0, 3.0]
    p.air_time = 5
    hg.simulate_tick()
    assert e not in hg.enemies
    assert p.mp_coins == 1 and p.velocity[1] == STOMP_BOUNCE_VELOCITY


# --- hazards --------------------------------------------------------------------------------


def test_spikes_hurt_on_their_points_only(game):
    g = arena(game, {(7, FLOOR - 1): {"type": "spikes", "variant": 0}})
    hz = g.hazards
    assert hz.lethal(pygame.Rect(7 * 16 + 4, FLOOR * 16 - 15, 8, 15), 0) == "spikes"
    assert hz.lethal(pygame.Rect(7 * 16 + 4, FLOOR * 16 - 15 - 9, 8, 15), 0) is None  # above the points
    p = g.player
    lives = p.lives
    p.pos[0] = 7 * 16 - 9
    g.movement = [False, True]
    for _ in range(30):
        g.step()
        if p.lives < lives:
            break
    assert p.lives == lives - 1 and not g.dead and p.velocity[1] < 0  # thrown up, off the points


def test_flame_beat():
    assert flame_state(0) == "burn"
    assert flame_state(47) == "burn"
    assert flame_state(48) == "off"
    assert flame_state(100) == "warn"
    assert flame_state(10, period=60, on=20, phase=50) == "burn"  # (10 + 50) % 60 == 0


def test_flame_reaches_three_tiles_and_stops_at_rock(game):
    g = arena(
        game,
        {
            (10, FLOOR - 1): {"type": "flamejet", "variant": 0},  # fires up
            (20, FLOOR - 1): {"type": "flamejet", "variant": 0},
            (20, FLOOR - 3): {"type": "stone", "variant": 1},  # a ceiling 2 tiles up
        },
    )
    jets = {j.pos[0]: j for j in g.hazards.jets}
    assert len(jets[10].cells) == FLAME_REACH
    assert jets[20].cells == [(20, FLOOR - 2)]
    above = pygame.Rect(10 * 16 + 4, (FLOOR - 3) * 16, 8, 15)
    assert g.hazards.lethal(above, 0) == "flame"
    assert g.hazards.lethal(above, 60) is None  # off


def test_crumbling_block_falls_and_comes_back(game):
    g = arena(game, {(5, FLOOR): {"type": "crumble", "variant": 0}})
    hz = g.hazards
    p = g.player
    hz.update([p])
    assert g.tilemap.tilemap[f"5;{FLOOR}"]["variant"] == 1  # cracked
    for _ in range(CRUMBLE_DELAY):
        hz.update([p])
    assert f"5;{FLOOR}" not in g.tilemap.tilemap
    p.collisions["down"] = False
    p.pos[1] = FLOOR * 16  # inside the hole: it must not close on the player
    for _ in range(CRUMBLE_RETURN + 5):
        hz.update([p])
    assert f"5;{FLOOR}" not in g.tilemap.tilemap
    p.pos[1] = 0
    hz.update([p])
    assert g.tilemap.tilemap[f"5;{FLOOR}"]["variant"] == 0


def test_respawn_restores_fallen_blocks(game):
    g = arena(game, {(5, FLOOR): {"type": "crumble", "variant": 0}})
    for _ in range(CRUMBLE_DELAY + 1):
        g.hazards.update([g.player])
    assert f"5;{FLOOR}" not in g.tilemap.tilemap
    g.hazards.restore()
    assert g.tilemap.tilemap[f"5;{FLOOR}"]["variant"] == 0


def test_hazard_tiles_are_solid_where_they_should_be():
    tm = Tilemap(None)
    for i, t in enumerate(("crumble", "flamejet", "spikes")):
        tm.tilemap[f"{i};0"] = {"type": t, "variant": 0, "pos": [i, 0]}
    assert tm.solid_check((0, 0)) and tm.solid_check((16, 0))
    assert not tm.solid_check((32, 0))


# --- the planner's model --------------------------------------------------------------------


def test_planner_physics_dies_on_spikes():
    tiles = {f"{x};10": {"type": "stone", "variant": 1, "pos": [x, 10]} for x in range(20)}
    tiles["8;9"] = {"type": "spikes", "variant": 0, "pos": [8, 9]}
    terrain = ph.solids_from_map(tiles)
    assert (8, 9) in terrain.lethal and (8, 9) not in terrain
    s = ph.spawn_state(5 * 16, 10 * 16 - 15)
    dead = False
    for _ in range(80):
        s, _down, dead = ph.step(s, 1, terrain)
        if dead:
            break
    assert dead and 7 * 16 < s[ph.X] < 9 * 16
    # the same walk on the same floor without the spikes lives
    calm = ph.Terrain(set(terrain))
    assert not calm.lethal
    s = ph.spawn_state(5 * 16, 10 * 16 - 15)
    for _ in range(80):
        s, _down, dead = ph.step(s, 1, calm)
        assert not dead


def test_terrain_copy_keeps_spikes():
    t = ph.Terrain({(0, 1)}, None, {(0, 0): [(0, 9, 16, 7)]})
    assert ph.Terrain(t, {}).lethal == t.lethal


# --- builder and cast -----------------------------------------------------------------------


def test_builder_writes_kinds_and_hazards():
    lv = Level(99, "stone")
    lv.rect(0, 10, 30, 10)
    lv.spawn(1, 9)
    lv.enemy(5, 9, "turret")
    lv.enemy(20, 9)  # cast picks
    lv.spikes(8, 9, 9)
    lv.spikes(12, 11, facing="down")
    lv.crumble(14, 10, 15)
    lv.flamejet(25, 10, "up", period=90, on=30, phase=15)
    tm = lv.to_json()["map_data"]["tilemap"]
    assert tm["5;9"]["variant"] == TURRET.variant
    assert tm["20;9"]["variant"] == KINDS[roster.cast(99, lv.is_solid, 20, 9)].variant
    assert tm["8;9"] == {"type": "spikes", "variant": 0, "pos": [8, 9]}
    assert tm["12;11"]["variant"] == 1
    assert tm["14;10"] == {"type": "crumble", "variant": 0, "pos": [14, 10]}
    assert tm["25;10"] == {"type": "flamejet", "variant": 0, "pos": [25, 10], "period": 90, "on": 30, "phase": 15}
    terrain = lv.solids()
    assert (14, 10) in terrain and (25, 10) in terrain and (8, 9) in terrain.lethal
    assert lv.stats()["enemies"] == 2
    with pytest.raises(ValueError):
        lv.flamejet(26, 10, on=200, period=100)
    with pytest.raises(ValueError):
        lv.enemy(1, 1, "dragon")


def test_cast_follows_intro_and_spot():
    def flat(x, y):  # endless floor at row 10
        return y == 10

    def ledge(x, y):  # a 2-tile ledge
        return y == 10 and x in (0, 1)

    assert {roster.cast(0, flat, x, 9) for x in range(200)} == {"patrol"}
    assert roster.cast(0, ledge, 0, 9) == "patrol"  # no turret (or gunner) in level 0 yet
    assert roster.cast(1, ledge, 0, 9) == "gunner"
    assert roster.cast(20, ledge, 0, 9) == "turret"
    cast40 = {roster.cast(40, flat, x, 9) for x in range(400)}
    assert cast40 == set(KINDS)
    assert roster.cast(17, flat, 33, 9) == roster.cast(17, flat, 33, 9)  # stable


def test_enemies_burn_in_flames_and_walk_around_spikes(game):
    g = arena(
        game, {(10, FLOOR - 1): {"type": "flamejet", "variant": 0}, (20, FLOOR - 1): {"type": "spikes", "variant": 0}}
    )
    burning = enemy_at(g, 10, "patrol")
    burning.pos[1] -= 16  # stands on the nozzle, in its flame
    walker = enemy_at(g, 18, "patrol")
    g.player.pos[0] = 2 * 16
    g.step()
    assert burning not in g.enemies and walker in g.enemies
    for _ in range(300):
        walker.update(g.tilemap)
        assert walker.rect().right <= 20 * 16  # turns before the spikes


# --- thrower --------------------------------------------------------------------------------


@pytest.mark.parametrize("dx,dy", [(120, 0), (-150, 0), (90, -25), (200, 80), (-60, 30)])
def test_thrown_star_comes_down_on_the_target(dx, dy):
    from scripts.ai.behaviors import throw_velocity
    from scripts.enemy_kinds import THROWER

    vx, vy = throw_velocity(THROWER, dx, dy)
    x = y = 0.0
    while y < dy or vy < 0:  # until it falls through the target's height
        vy += THROWER.throw_gravity
        x += vx
        y += vy
    assert abs(x - dx) < 4


def test_thrower_does_not_throw_out_of_reach():
    from scripts.ai.behaviors import throw_velocity
    from scripts.enemy_kinds import THROWER

    assert throw_velocity(THROWER, 0, -200) is None  # far above
    assert throw_velocity(THROWER, 90, -40) is None  # above the top of its arc
    assert throw_velocity(THROWER, 400, 0) is None  # too far


def test_thrower_paces_and_throws_stars_on_a_beat(game):
    from scripts.ai.behaviors import TURRET_WINDUP
    from scripts.enemy_kinds import THROWER

    e = enemy_at(game, 15, "thrower")
    game.player.pos[0] = 15 * 16 - 120  # in sight, in reach, to the left
    xs, throws = [], []
    for frame in range(1, 400):
        before = len(list(game.projectiles))
        e.update(game.tilemap)
        xs.append(e.pos[0])
        if len(list(game.projectiles)) > before:
            throws.append(frame)
    assert throws[0] == TURRET_WINDUP + 1
    assert {b - a for a, b in zip(throws, throws[1:])} == {THROWER.fire_period}
    star = list(game.projectiles)[-1]
    assert star["kind"] == "star" and star["vel"][0] < 0 and star["gravity"] == THROWER.throw_gravity
    home = 15 * 16 + 4
    assert max(xs) - min(xs) > 3 * 16  # paces...
    assert home - THROWER.pace - 2 <= min(xs) and max(xs) <= home + THROWER.pace + 2  # ...around home


def test_a_thrown_star_hits_the_player(game):
    p = game.player
    enemy_at(game, 12, "thrower")
    lives = p.lives
    for _ in range(300):
        game.step()
        if p.lives < lives:
            break
    assert p.lives == lives - 1


def test_snapshot_keeps_a_stars_arc(game):
    from scripts.snapshot import SnapshotService

    game.projectiles.spawn(100, 100, -2.0, "enemy", vy=-2.2, gravity=0.08, kind="star")
    snap = SnapshotService.capture(game)
    data = SnapshotService.serialize(snap)
    restored = SnapshotService.deserialize(data)
    game.projectiles.clear()
    SnapshotService.restore(game, restored)
    star = list(game.projectiles)[0]
    assert star["vel"] == [-2.0, -2.2] and star["gravity"] == 0.08 and star["kind"] == "star"
