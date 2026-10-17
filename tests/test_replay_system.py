import pygame
import pytest

from scripts.replay import ReplayManager
from scripts.settings import settings as global_settings


class _StubAnim:
    def __init__(self, size=(12, 18)):
        self.images = [pygame.Surface(size, pygame.SRCALPHA)]
        self.img_duration = 5
        self.frame = 0

    def img(self):
        return self.images[0]

    def copy(self):
        return self

    def update(self):
        self.frame += 1


class _StubGame:
    def __init__(self):
        self.assets = {"player/default/idle": _StubAnim(), "player/default/run": _StubAnim()}
        self.display = pygame.Surface((160, 120), pygame.SRCALPHA)
        self.dead = 0
        self.transition = 0
        self.tilemap = type("StubTM", (), {"physics_rects_around": lambda self, pos: []})()
        self.players = []
        self.enemies = []
        # self.projectiles = [] # Optional, checking hasattr


class _StubPlayer:
    def __init__(self):
        self.pos = [0.0, 0.0]
        self.flip = False
        self.action = "idle"
        self.skin = 0
        self.animation = type("Anim", (), {"frame": 0, "img_duration": 5})()
        self.velocity = [0.0, 0.0]
        self.lives = 3
        self.air_time = 0
        self.jumps = 1
        self.wall_slide = False
        self.dashing = 0
        self.shoot_cooldown = 0
        self.id = 0


@pytest.fixture(autouse=True)
def _init_pygame():
    pygame.init()
    previous_ghost = global_settings.ghost_enabled
    global_settings.ghost_enabled = True
    yield
    global_settings.ghost_enabled = previous_ghost
    pygame.quit()


def test_replay_commit_and_load(tmp_path):
    game = _StubGame()
    manager = ReplayManager(game, storage_dir=tmp_path)
    player = _StubPlayer()
    # Add player to game so SnapshotService finds it
    game.players.append(player)

    manager.on_level_load(level=1, player=player)
    assert not manager.ghost  # No ghost on first run

    # Capture inputs & frames
    for idx in range(15):  # Need > 10 frames for commit
        player.pos = [float(idx * 4), float(idx * 2)]
        # manager.update now takes inputs
        manager.update(player, inputs=[])

    manager.commit_run(new_best=True)

    replay_path = tmp_path / "1.json"
    assert replay_path.exists()

    manager.on_level_load(level=1, player=player)
    assert manager.ghost is not None  # Ghost exists now

    # Render test
    # This now triggers re-simulation
    manager.render_ghost(game.display, (0, 0))
    assert manager.ghost.tick >= 1


def test_replay_last_run_persisted(tmp_path):
    game = _StubGame()
    manager = ReplayManager(game, storage_dir=tmp_path)
    player = _StubPlayer()
    game.players.append(player)

    manager.on_level_load(level=2, player=player)
    for idx in range(15):
        player.pos = [float(idx), float(idx * 2)]
        manager.update(player, [])

    manager.commit_run(new_best=False)

    best_path = tmp_path / "2.json"
    last_path = tmp_path / "last_runs" / "2.json"
    assert not best_path.exists()
    assert last_path.exists()

    # Simulate fresh session to ensure last run is loaded
    new_manager = ReplayManager(game, storage_dir=tmp_path)
    new_manager.on_level_load(level=2, player=player)
    assert new_manager.ghost is not None


def test_replay_disabled_skips_capture(tmp_path):
    game = _StubGame()
    global_settings.ghost_enabled = False
    manager = ReplayManager(game, storage_dir=tmp_path)
    player = _StubPlayer()
    game.players.append(player)

    manager.on_level_load(level=5, player=player)
    assert manager.recording is None
    assert manager.ghost is None

    for idx in range(15):
        player.pos = [float(idx * 3), float(idx)]
        manager.update(player, [])

    manager.commit_run(new_best=True)

    assert not (tmp_path / "5.json").exists()
    assert not (tmp_path / "last_runs" / "5.json").exists()


def _committed_run(tmp_path, level, new_best):
    game = _StubGame()
    manager = ReplayManager(game, storage_dir=tmp_path)
    player = _StubPlayer()
    game.players.append(player)
    manager.on_level_load(level=level, player=player)
    for idx in range(15):
        player.pos = [float(idx), float(idx)]
        manager.update(player, [])
    manager.commit_run(new_best=new_best)
    return game, player


def test_ghost_replay_is_read_once_per_level(tmp_path, monkeypatch):
    game, player = _committed_run(tmp_path, level=3, new_best=True)  # writes best and last run
    manager = ReplayManager(game, storage_dir=tmp_path)
    reads = []
    real_load = manager._load
    monkeypatch.setattr(manager, "_load", lambda level, kind: reads.append(kind) or real_load(level, kind))

    manager.on_level_load(level=3, player=player)
    manager.on_level_load(level=3, player=player)  # respawn

    assert reads == ["best"]  # the last run is not needed while a best run exists
    assert manager.ghost is not None and manager.ghost.data is manager.best_data


def test_ghost_falls_back_to_the_other_replay(tmp_path, monkeypatch):
    game, player = _committed_run(tmp_path, level=4, new_best=False)  # writes only the last run
    monkeypatch.setattr(global_settings, "_ghost_mode", "best")  # the setter would save settings
    manager = ReplayManager(game, storage_dir=tmp_path)

    manager.on_level_load(level=4, player=player)

    assert manager.best_data is None
    assert manager.ghost is not None and manager.ghost.data is manager.last_data


def test_ghost_advances_once_per_game_tick(tmp_path):
    game, player = _committed_run(tmp_path, level=6, new_best=True)
    game.tick = 0
    manager = ReplayManager(game, storage_dir=tmp_path)
    manager.on_level_load(level=6, player=player)

    game.tick += 1
    manager.render_ghost(game.display, (0, 0))
    for _ in range(5):  # paused: frames are drawn, the game does not tick
        manager.render_ghost(game.display, (0, 0))
    assert manager.ghost.tick == 1

    game.tick += 1
    manager.render_ghost(game.display, (0, 0))
    assert manager.ghost.tick == 2
