"""The death log (scripts/death_log.py): one line per death, written where every death ends."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402
import pytest  # noqa: E402

from scripts import death_log  # noqa: E402
from scripts.constants import AIR_TIME_FATAL, RESPAWN_DEAD_THRESHOLD  # noqa: E402
from scripts.state_manager import GameState  # noqa: E402
from scripts.tilemap import Tilemap  # noqa: E402
from tools.worlds.builder import Level  # noqa: E402

MAP_ID = 9002
GROUND = 20
SPAWN = (2 * 16, (GROUND - 1) * 16)


def _build() -> Level:
    """Ground, a pit, ground with a banner, a pool deep enough to drown in, the flag."""
    lv = Level(MAP_ID, "sand")
    lv.rect(0, GROUND, 10, GROUND + 3)
    lv.rect(14, GROUND, 60, GROUND + 3)
    lv.carve(40, GROUND, 46, GROUND + 2)
    lv.rect(40, GROUND + 3, 46, GROUND + 3)
    lv.water(40, GROUND, 46, GROUND + 2)
    lv.spawn(2, GROUND - 1)
    lv.checkpoint(20, GROUND - 1)
    lv.flag(58, GROUND - 1)
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
    """A clear saves a best time and the run's replay: keep both out of data/."""
    from scripts import timer
    from scripts.replay import ReplayManager

    monkeypatch.setattr(timer, "BEST_TIMES_FILE", str(tmp_path / "best_times.json"))
    monkeypatch.setattr(ReplayManager, "commit_run", lambda self, new_best: None)


@pytest.fixture
def deaths(tmp_path, monkeypatch):
    """The log switched on as app.main() does, writing into a scratch folder."""
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


def _lines(folder):
    return death_log.read(MAP_ID, str(folder))


def _until_reload(gs, limit=AIR_TIME_FATAL + 2 * RESPAWN_DEAD_THRESHOLD + 60):
    """Run GameState.update until the death block reloads the level."""
    g = gs.game
    for _ in range(limit):
        was_dead = g.dead
        gs.update(1 / 60)
        if was_dead and not g.dead:
            return
    raise AssertionError("no reload")


def _over_the_pit(g):
    g.player.pos = [12 * 16.0, (GROUND - 2) * 16.0]
    g.player.velocity = [0, 0]


def test_a_fall_is_logged_once_when_the_level_reloads(maps, deaths):
    gs = _game_state()
    g = gs.game
    _over_the_pit(g)
    _until_reload(gs)
    lines = _lines(deaths)
    assert len(lines) == 1
    d = lines[0]
    assert d["event"] == "death" and d["cause"] == "fell_out"
    assert d["level"] == MAP_ID and d["attempt"] == 1
    assert d["pos"][1] > g.tilemap.kill_y and 11 * 16 <= d["pos"][0] <= 13 * 16
    assert d["respawn"] == list(SPAWN)
    assert d["checkpoint"] is None and d["checkpoints"] == []
    assert d["lives"] == 3 and d["restart"] is False
    assert d["tick"] > 0 and 0 < d["attempt_ticks"] <= d["tick"]
    assert len(d["map"]) == 12 and d["session"] and d["gear"]
    assert g.player.pos == list(SPAWN)  # respawned

    # the next death is the next attempt; its ticks count from the respawn
    _over_the_pit(g)
    _until_reload(gs)
    second = _lines(deaths)[1]
    assert second["attempt"] == 2
    assert second["attempt_ticks"] < second["tick"] - d["tick"] + 1


def test_the_respawn_point_and_the_banner_reached_are_recorded(maps, deaths):
    gs = _game_state()
    g = gs.game
    g.player.pos = [20 * 16.0, (GROUND - 1) * 16.0]
    gs.update(1 / 60)
    assert g.player.respawn_pos == [20 * 16, (GROUND - 1) * 16]
    _over_the_pit(g)
    _until_reload(gs)
    d = _lines(deaths)[0]
    assert d["respawn"] == [20 * 16, (GROUND - 1) * 16]
    assert d["checkpoint"] == 0 and d["checkpoints"] == [0]


def test_air_time_names_its_cause(maps, deaths):
    gs = _game_state()
    g = gs.game
    g.player.pos = [30 * 16.0, (GROUND - 6) * 16.0]  # in the air, far above the kill line
    g.player.air_time = AIR_TIME_FATAL
    _until_reload(gs)
    assert _lines(deaths)[0]["cause"] == "air_time"


def test_running_out_of_breath_names_its_cause(maps, deaths):
    gs = _game_state()
    g = gs.game
    g.player.pos = [42 * 16.0, (GROUND + 1) * 16.0]  # under water
    g.player.breath = 3
    _until_reload(gs)
    assert _lines(deaths)[0]["cause"] == "breath"


def test_r_costs_a_life_and_is_logged_as_a_restart(maps, deaths):
    gs = _game_state()
    for _ in range(5):
        gs.update(1 / 60)
    gs.handle([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r})])
    _until_reload(gs)
    d = _lines(deaths)[0]
    assert d["cause"] == "restart" and d["lives"] == 2 and d["restart"] is False


def test_the_last_life_lost_to_a_bullet_logs_a_hit_and_then_out_of_lives(maps, deaths):
    gs = _game_state()
    g = gs.game
    for _ in range(5):
        gs.update(1 / 60)
    g.player.lives = 1
    r = g.player.rect()
    g.projectiles.spawn(r.centerx - 1, r.centery - 1, 0.0, "enemy")
    _until_reload(gs)
    hit, death = _lines(deaths)
    assert hit["event"] == "hit" and hit["lives"] == 0 and hit["absorbed"] is False
    assert death["event"] == "death" and death["cause"] == "out_of_lives" and death["restart"] is True
    assert hit["attempt"] == death["attempt"] == 1


def test_the_first_cause_wins(maps, deaths):
    gs = _game_state()
    g = gs.game
    _over_the_pit(g)
    while not g.dead:
        gs.update(1 / 60)
    gs.handle([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r})])  # R during the death fade
    _until_reload(gs)
    lines = _lines(deaths)
    assert len(lines) == 1 and lines[0]["cause"] == "fell_out"


def test_a_ghost_or_another_player_names_no_cause(maps, deaths):
    gs = _game_state()
    g = gs.game
    death_log.set_cause(g, "air_time", entity=object())
    assert g.death_log._pending is None
    death_log.set_cause(g, "air_time", entity=g.player)
    assert g.death_log._pending[0] == "air_time"


def test_the_manual_checkpoint_clear_and_quit_are_logged(maps, deaths):
    gs = _game_state()
    g = gs.game
    for _ in range(5):
        gs.update(1 / 60)
    gs.handle([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_p})])
    g.player.pos = [58 * 16.0, (GROUND - 1) * 16.0]  # on the flag
    for _ in range(200):  # no manager here: the clear screen never comes, the block runs on
        gs.update(1 / 60)
    gs.on_exit(None)  # cleared: leaving is no quit
    kinds = [line["event"] for line in _lines(deaths)]
    assert kinds == ["save", "clear"]
    clear = _lines(deaths)[1]
    assert clear["run_ms"] >= 0 and clear["attempt"] == 1

    gs2 = _game_state()
    gs2.update(1 / 60)
    gs2.on_exit(None)
    quit_line = _lines(deaths)[-1]
    assert quit_line["event"] == "quit" and quit_line["attempt"] == 2


def test_nothing_is_logged_unless_the_app_switched_it_on(maps, tmp_path):
    death_log.disable()
    gs = _game_state()
    g = gs.game
    assert getattr(g, "death_log", None) is None
    _over_the_pit(g)
    _until_reload(gs)
    assert not (tmp_path / "deaths").exists()


def test_the_environment_switch_turns_it_off(monkeypatch, tmp_path):
    monkeypatch.setenv(death_log.ENV_SWITCH, "0")
    assert death_log.enable(str(tmp_path / "deaths")) is None
    assert death_log.current() is None


def test_the_route_bot_switches_it_off():
    import inspect

    from tools.worlds import play

    assert 'NINJA_DEATH_LOG"] = "0"' in inspect.getsource(play.run_level)
    assert 'NINJA_DEATH_LOG"] = "0"' in inspect.getsource(play.bot_main)


def test_a_named_map_outside_the_campaign_plays_and_logs_under_its_name(maps, deaths, monkeypatch):
    import shutil

    from scripts.state_manager import LevelCompleteState, StateManager

    shutil.copy(maps / f"{MAP_ID}.json", maps / "testcourse.json")
    load = Tilemap.load

    def named(self, path, *a, **k):
        if path.endswith("/testcourse.json"):
            result = load(self, str(maps / "testcourse.json"), *a, **k)
            self.loaded_path = str(maps / "testcourse.json")
            return result
        return load(self, path, *a, **k)

    monkeypatch.setattr(Tilemap, "load", named)
    pygame.init()
    sm = StateManager()
    gs = GameState(level="testcourse")
    sm.set(gs)
    g = gs.game
    assert g.level == "testcourse" and g.player.pos == list(SPAWN)
    _over_the_pit(g)
    _until_reload(gs)
    assert death_log.read("testcourse", str(deaths))[0]["level"] == "testcourse"
    g.player.pos = [58 * 16.0, (GROUND - 1) * 16.0]  # on the flag
    for _ in range(200):
        sm.update(1 / 60)
        if isinstance(sm.current, LevelCompleteState):
            break
    done = sm.current
    assert isinstance(done, LevelCompleteState)
    assert done.current_level == "testcourse" and done.next_level is None  # nothing follows, nothing unlocks
