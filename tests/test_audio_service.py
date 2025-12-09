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


def test_audio_ducking(patch_sounds, monkeypatch):
    svc, _ = patch_sounds
    settings.music_volume = 1.0

    # Mock mixer.music.set_volume
    music_vols = []

    def fake_set_volume(v):
        music_vols.append(v)

    monkeypatch.setattr(pygame.mixer.music, "set_volume", fake_set_volume)

    # 1. Trigger ducking
    svc.trigger_ducking(intensity=0.2)
    # Check that update() applies the ducking immediately (linear interpolation downward)
    svc.update()

    assert len(music_vols) > 0
    # First update should lower volume from 1.0 towards 0.2
    assert music_vols[-1] < 1.0

    # 2. Simulate frames until recovery
    # We expect volume to go down, stay low, then recover?
    # Current implementation:
    #   if _duck_target < 1.0: lerp down
    #   if _duck_factor <= target: target = 1.0
    #   if _duck_factor < 1.0: lerp up

    # Reach bottom
    for _ in range(20):
        svc.update()

    lowest = min(music_vols)
    assert lowest <= 0.3  # Should reach near intensity target (0.2 + tolerance)

    # Recover
    for _ in range(20):
        svc.update()

    assert music_vols[-1] >= 0.95  # Should be back near 1.0
