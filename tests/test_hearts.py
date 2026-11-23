"""Hearts: a life back once per run (scripts/collectableManager.py), placed
along the route by the danger on it (tools/worlds/hearts.py)."""

import json
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402
import pytest  # noqa: E402

from scripts import death_log  # noqa: E402
from scripts.collectableManager import CollectableManager  # noqa: E402
from scripts.constants import AIR_TIME_FATAL, HEART_COINS, RESPAWN_DEAD_THRESHOLD  # noqa: E402
from scripts.state_manager import GameState  # noqa: E402
from scripts.tilemap import Tilemap  # noqa: E402
from tools.worlds import hearts  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402

MAP_ID = 9010
GROUND = 20
HEART = (6, GROUND - 1)


def _build() -> Level:
    """Ground with a heart, a pit, more ground, the flag."""
    lv = Level(MAP_ID, "sand")
    lv.rect(0, GROUND, 10, GROUND + 3)
    lv.rect(14, GROUND, 40, GROUND + 3)
    lv.spawn(2, GROUND - 1)
    lv.heart(*HEART)
    lv.flag(38, GROUND - 1)
    return lv


@pytest.fixture
def maps(tmp_path, monkeypatch):
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    _build().save(str(maps_dir))
    load = Tilemap.load

    def redirected(self, path, *a, **k):
        target = str(maps_dir / f"{MAP_ID}.json") if path.endswith(f"/{MAP_ID}.json") else path
        result = load(self, target, *a, **k)
        self.loaded_path = target
        return result

    monkeypatch.setattr(Tilemap, "load", redirected)
    return maps_dir


@pytest.fixture(autouse=True)
def scratch_saves(tmp_path, monkeypatch):
    """Keep best times, replays and coins out of data/."""
    from scripts import timer
    from scripts.replay import ReplayManager

    monkeypatch.setattr(timer, "BEST_TIMES_FILE", str(tmp_path / "best_times.json"))
    monkeypatch.setattr(ReplayManager, "commit_run", lambda self, new_best: None)
    monkeypatch.setattr(CollectableManager, "save_collectables", lambda self: None)
    # No gear, whatever the settings select (a Lucky Charm would start with 4 lives)
    monkeypatch.setattr(CollectableManager, "GEAR", ["None"] * len(CollectableManager.GEAR))


@pytest.fixture
def deaths(tmp_path, monkeypatch):
    monkeypatch.delenv(death_log.ENV_SWITCH, raising=False)
    folder = tmp_path / "deaths"
    death_log.enable(str(folder))
    yield folder
    death_log.disable()


def _game_state():
    pygame.init()
    gs = GameState()
    g = gs.game
    g.level = MAP_ID
    g.load_level(MAP_ID)
    return gs


def _take(g):
    g.cm.update(g.cm.hearts[0].rect.copy())


def test_a_heart_gives_a_lost_life_back(maps, deaths):
    g = _game_state().game
    assert len(g.cm.hearts) == 1 and g.start_lives == 3
    g.player.lives = 1
    _take(g)
    assert g.player.lives == 2 and not g.cm.hearts
    line = death_log.read(MAP_ID, str(deaths))[-1]
    assert line["event"] == "heart" and line["life"] is True and line["lives"] == 2


def test_with_full_lives_a_heart_pays_coins(maps, deaths):
    g = _game_state().game
    coins = g.cm.coins
    _take(g)
    assert g.player.lives == 3 and g.cm.coins == coins + HEART_COINS
    assert death_log.read(MAP_ID, str(deaths))[-1]["life"] is False


def test_the_lucky_charm_raises_the_cap(maps, monkeypatch):
    monkeypatch.setattr(CollectableManager, "GEAR", ["Lucky Charm"] * len(CollectableManager.GEAR))
    pygame.init()
    gs = GameState()
    g = gs.game
    g.cm.lucky_charm = 1
    g.level = MAP_ID
    g.load_level(MAP_ID)
    assert g.start_lives == 4 and g.player.lives == 4
    g.player.lives = 3
    _take(g)
    assert g.player.lives == 4


def test_a_taken_heart_stays_gone_after_a_fall(maps):
    """Falls cost no life: a heart that came back with the respawn could be farmed."""
    gs = _game_state()
    g = gs.game
    g.player.lives = 2
    _take(g)
    g.player.pos = [12 * 16.0, (GROUND - 2) * 16.0]  # over the pit
    g.player.velocity = [0, 0]
    for _ in range(AIR_TIME_FATAL + 2 * RESPAWN_DEAD_THRESHOLD + 60):
        was_dead = g.dead
        gs.update(1 / 60)
        if was_dead and not g.dead:
            break
    else:
        raise AssertionError("no respawn")
    assert g.player.lives == 3 and g.cm.hearts == []


def test_a_new_run_brings_the_hearts_back(maps):
    g = _game_state().game
    _take(g)
    g.load_level(MAP_ID, g.player.lives, respawn=True)
    assert g.cm.hearts == []
    g.load_level(MAP_ID)
    assert len(g.cm.hearts) == 1 and g.hearts_taken == set()


def test_hearts_are_drawn(maps):
    g = _game_state().game
    surf = pygame.Surface((320, 240))
    g.cm.render(surf)
    assert surf.get_bounding_rect().width > 0


# --- placement ----------------------------------------------------------------


def _course() -> Level:
    """A flat run of ground with four ground waypoints and the flag."""
    lv = Level(MAP_ID, "sand")
    lv.rect(0, GROUND, 80, GROUND + 3)
    lv.spawn(2, GROUND - 1)
    for i, x in enumerate((15, 30, 45, 60)):
        lv.wp(x - 1, GROUND - 1, x + 1, GROUND - 1, ground=True, label=f"stop {i}")
    lv.wp(76, GROUND - 1, 78, GROUND - 1, ground=True, label="flag")
    lv.flag(78, GROUND - 1)
    return lv


SEGMENTS = [(0, 100), (100, 100), (200, 100), (300, 100), (400, 100)]  # waypoint i reached at frame 100 (i + 1)


def test_a_heart_goes_on_the_next_ground_waypoint_after_the_budget():
    lv = _course()
    hits = [0.0] * 500
    hits[150] = hearts.BUDGET  # all the danger between the first and the second stop
    assert hearts.heart_spots(lv, hits, SEGMENTS) == [(30, GROUND - 1)]


def test_a_calm_route_gets_no_heart_and_the_flag_none():
    lv = _course()
    assert hearts.heart_spots(lv, [0.0] * 500, SEGMENTS) == []
    hits = [0.0] * 500
    hits[450] = 2 * hearts.BUDGET  # danger only on the way to the flag
    assert hearts.heart_spots(lv, hits, SEGMENTS) == []


def test_counting_starts_again_at_a_heart():
    lv = _course()
    hits = [hearts.BUDGET / 50] * 500  # one budget every 50 frames
    # first at frame 49 -> stop 0 (frame 100); counting again from 101: frame 150 -> stop 1, ...
    assert hearts.heart_spots(lv, hits, SEGMENTS) == [(x, GROUND - 1) for x in (15, 30, 45, 60)]


def test_a_heart_keeps_out_of_flames_and_rock_and_takes_a_coins_place():
    lv = _course()
    lv.flamejet(30, GROUND, "up")  # its flame covers the waypoint's middle, (30, GROUND - 1)
    lv.coin(29, GROUND - 1)
    cell = hearts.heart_cell(lv, lv.route[1], hearts._flamed(lv))
    assert cell == (29, GROUND - 1)
    lv.heart(*cell)
    assert lv.objects[cell] == ("heart", 0)


def test_danger_counts_enemies_and_hazards():
    lv = _course()
    lv.enemy(20, GROUND - 1, "gunner")
    lv.spikes(22, GROUND - 1)
    lv.crumble(24, GROUND)
    lv.flamejet(26, GROUND, "up")
    enemies, hazards = hearts.danger_sites(lv)
    assert len(enemies) == 1 and len(hazards) == 3


@pytest.mark.parametrize("level", hearts.HEART_LEVELS)
def test_the_test_levels_have_hearts(level):
    with open(f"data/maps/{level}.json") as f:
        tiles = json.load(f)["map_data"]["tilemap"].values()
    assert sum(1 for t in tiles if t["type"] == "heart") >= 1
