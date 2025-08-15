import pygame
import pytest
from scripts.asset_manager import AssetManager


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    pygame.init()
    yield
    pygame.quit()


def test_image_caching():
    am = AssetManager.get()
    img1 = am.get_image("background-big.png")
    img2 = am.get_image("background-big.png")
    assert img1 is img2, "Expected same cached surface instance"


def test_animation_instances_share_frames_not_state():
    am = AssetManager.get()
    anim1 = am.get_animation("entities/player/default/idle", img_dur=6)
    anim2 = am.get_animation("entities/player/default/idle", img_dur=6)
    # Should not be same Animation wrapper
    assert anim1 is not anim2
    # Underlying frame list objects identical (shared cache)
    assert anim1.images is anim2.images
    # Advance one animation; frame counters diverge
    before1, before2 = anim1.frame, anim2.frame
    anim1.update()
    assert anim1.frame != before1 or anim1.frame == 0  # moved or looped
    assert anim2.frame == before2  # untouched
