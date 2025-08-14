import os
import pygame
import pytest
from scripts.ui import UI

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()


# Helper to make distinct tiny images
def make_img(path, color):
    surf = pygame.Surface((4, 4))
    surf.fill(color)
    pygame.image.save(surf, path)


def setup_module(module):
    # Create 5 images
    for i, color in enumerate(
        [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)]
    ):
        make_img(f"temp_img_{i}.png", color)


def teardown_module(module):
    for i in range(5):
        p = f"temp_img_{i}.png"
        if os.path.exists(p):
            os.remove(p)


def test_lru_eviction_and_stats():
    UI.clear_image_cache()
    UI.configure_image_cache(capacity=3)
    display = pygame.Surface((40, 40))

    # Load 3 images -> misses=3
    for i in range(3):
        UI.render_ui_img(display, f"temp_img_{i}.png", 10, 10)
    stats = UI.get_image_cache_stats()
    assert stats["misses"] == 3
    assert stats["size"] == 3
    assert stats["evictions"] == 0

    # Access first again -> hit
    UI.render_ui_img(display, "temp_img_0.png", 10, 10)
    stats = UI.get_image_cache_stats()
    assert stats["hits"] == 1

    # Add a 4th image -> eviction of LRU (which should be img_1 if 0 was just touched)
    UI.render_ui_img(display, "temp_img_3.png", 10, 10)
    stats = UI.get_image_cache_stats()
    assert stats["misses"] == 4
    assert stats["evictions"] == 1
    assert stats["size"] == 3

    # Ensure key ordering by attempting to load evicted image (temp_img_1) -> miss
    UI.render_ui_img(display, "temp_img_1.png", 10, 10)
    stats = UI.get_image_cache_stats()
    assert stats["misses"] == 5
    # Another eviction happened
    assert stats["evictions"] == 2
    assert stats["size"] == 3
