import os
import pygame
import pytest

from scripts.ui import UI

# Initialize pygame for image operations (headless)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()

# Create a temporary surface file for testing
TEST_IMG_PATH = "temp_test_img.png"
if not os.path.exists(TEST_IMG_PATH):
    surf = pygame.Surface((10, 10))
    surf.fill((255, 0, 0))
    pygame.image.save(surf, TEST_IMG_PATH)


def test_render_ui_img_uses_cache(monkeypatch):
    UI.clear_image_cache()
    load_calls = {"count": 0}

    original_load = pygame.image.load

    def fake_load(path):  # track invocations
        load_calls["count"] += 1
        return original_load(path)

    monkeypatch.setattr(pygame.image, "load", fake_load)

    display = pygame.Surface((100, 100))
    # First call loads from disk
    UI.render_ui_img(display, TEST_IMG_PATH, 50, 50, scale=2)
    # Second call should hit cache (no new load)
    UI.render_ui_img(display, TEST_IMG_PATH, 60, 60, scale=2)

    assert load_calls["count"] == 1, "Image should be loaded only once due to caching"


def test_cache_distinguishes_scale(monkeypatch):
    UI.clear_image_cache()
    load_calls = {"count": 0}
    original_load = pygame.image.load

    def fake_load(path):
        load_calls["count"] += 1
        return original_load(path)

    monkeypatch.setattr(pygame.image, "load", fake_load)

    display = pygame.Surface((100, 100))
    UI.render_ui_img(display, TEST_IMG_PATH, 10, 10, scale=1)
    UI.render_ui_img(display, TEST_IMG_PATH, 20, 20, scale=2)
    # Two different scale variants should each trigger a base load once (still 1 underlying disk read per variant)
    assert load_calls["count"] == 2


def teardown_module(module):
    if os.path.exists(TEST_IMG_PATH):
        os.remove(TEST_IMG_PATH)
