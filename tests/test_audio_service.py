import pygame
import pytest
from scripts.audio_service import AudioService
from scripts.settings import settings


@pytest.fixture(autouse=True, scope="module")
def pygame_init():
    pygame.init()
    yield
    pygame.quit()


class DummySound:
    def __init__(self):
        self.last_volume = None
        self.play_calls = 0

    def set_volume(self, v):
        self.last_volume = v

    def play(self, loops=0):
        self.play_calls += 1


@pytest.fixture
def patch_sounds(monkeypatch):
    dummy = DummySound()

    def fake_get_sound(path):
        return dummy

    from scripts import asset_manager

    monkeypatch.setattr(
        asset_manager.AssetManager,
        "get_sound",
        staticmethod(lambda p: fake_get_sound(p)),
    )
    # Recreate singleton to use patched method
    asset_manager.AssetManager._instance = None
    AudioService._instance = None
    svc = AudioService.get()
    return svc, dummy


def test_volume_application(patch_sounds):
    svc, dummy = patch_sounds
    settings.sound_volume = 0.5
    settings.music_volume = 0.3
    svc.apply_volumes()
    assert dummy.last_volume is not None


def test_play_calls(patch_sounds):
    svc, dummy = patch_sounds
    before = dummy.play_calls
    svc.play("jump")
    assert dummy.play_calls == before + 1
