import pygame
import pytest

from scripts.replay import ReplayManager
from scripts.settings import settings as global_settings


class _StubAnim:
    def __init__(self, size=(12, 18)):
        self.images = [pygame.Surface(size, pygame.SRCALPHA)]
        self.img_duration = 5


class _StubGame:
    def __init__(self):
        self.assets = {"player/default/idle": _StubAnim(), "player/default/run": _StubAnim()}
        self.display = pygame.Surface((160, 120), pygame.SRCALPHA)
        self.dead = 0


class _StubPlayer:
    def __init__(self):
        self.pos = [0.0, 0.0]
        self.flip = False
        self.action = "idle"
        self.skin = 0
        self.animation = type("Anim", (), {"frame": 0, "img_duration": 5})()


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

    manager.on_level_load(level=1, player=player)
    assert not manager.has_ghost()

    for idx in range(4):
        player.pos = [float(idx * 4), float(idx * 2)]
        player.animation.frame = idx * player.animation.img_duration
        player.flip = bool(idx % 2)
        manager.capture_player(player)

    manager.commit_run(duration_ms=1234, new_best=True)

    replay_path = tmp_path / "1.json"
    assert replay_path.exists()

    manager.on_level_load(level=1, player=player)
    assert manager.has_ghost()

    first_frame = manager.ghost_current_frame()
    assert first_frame is not None
    assert first_frame.x == pytest.approx(0.0)
    assert first_frame.y == pytest.approx(0.0)

    manager.advance_and_render(game.display, (0, 0))
    assert manager.ghost_index() >= 1


def test_replay_last_run_persisted(tmp_path):
    game = _StubGame()
    manager = ReplayManager(game, storage_dir=tmp_path)
    player = _StubPlayer()

    manager.on_level_load(level=2, player=player)
    for idx in range(3):
        player.pos = [float(idx), float(idx * 2)]
        manager.capture_player(player)

    manager.commit_run(duration_ms=9999, new_best=False)

    best_path = tmp_path / "2.json"
    last_path = tmp_path / "last_runs" / "2.json"
    assert not best_path.exists()
    assert last_path.exists()

    # Simulate fresh session to ensure last run is loaded
    new_manager = ReplayManager(game, storage_dir=tmp_path)
    new_manager.on_level_load(level=2, player=player)
    assert new_manager.has_ghost()
    frame = new_manager.ghost_current_frame()
    assert frame is not None
    assert frame.x == pytest.approx(0.0)


def test_replay_disabled_skips_capture(tmp_path):
    game = _StubGame()
    global_settings.ghost_enabled = False
    manager = ReplayManager(game, storage_dir=tmp_path)
    player = _StubPlayer()

    manager.on_level_load(level=5, player=player)
    assert manager.recording is None
    assert not manager.has_ghost()

    for idx in range(3):
        player.pos = [float(idx * 3), float(idx)]
        manager.capture_player(player)

    manager.commit_run(duration_ms=777, new_best=True)

    assert not (tmp_path / "5.json").exists()
    assert not (tmp_path / "last_runs" / "5.json").exists()
