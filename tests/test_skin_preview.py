"""The stage the store and accessories show items on (scripts/skin_preview.py)."""

import os

import pygame

from scripts.collectableManager import CollectableManager
from scripts.skin_preview import BOX, SEQUENCE, STAGE, SkinPreview, wrap_text

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()


def test_showcase_plays_every_move_of_every_skin():
    for path in CollectableManager.SKIN_PATHS:
        preview = SkinPreview()
        preview.set_skin(path)
        seen = set()
        total = sum(len(os.listdir(f"data/images/entities/player/{path}/{a}")) * d * n for a, d, n in SEQUENCE)
        for _ in range(total):
            seen.add(id(preview.frame()))
            preview.update(1 / 60)
        assert preview.frame().get_size() == BOX
        assert len(seen) > 30, path


def test_switching_skins_restarts_the_showcase():
    preview = SkinPreview()
    preview.set_skin("homura")
    preview.update(1.0)
    preview.set_skin("oni")
    assert preview.ticks == 0


def test_stage_fills_its_rect_and_shows_the_ninja():
    preview = SkinPreview()
    preview.set_skin("default", showcase=False)
    surf = pygame.Surface((STAGE[0] * 2, STAGE[1] * 2))
    surf.fill((1, 2, 3))
    preview.render_stage(surf, surf.get_rect(), held="gun.png")
    assert surf.get_at((0, 0)) != (1, 2, 3)  # sky reaches the corner
    body = (38, 36, 58)  # the default ninja's suit, standing mid-stage
    assert any(surf.get_at((x, y))[:3] == body for x in range(STAGE[0] - 16, STAGE[0] + 16) for y in range(40, 80))


def test_wrap_text_keeps_lines_within_width():
    font = pygame.font.Font("data/font.ttf", 18)
    text = CollectableManager.SKIN_INFO["Shogun"].description
    lines = wrap_text(font, text, 300)
    assert " ".join(lines) == text
    assert all(font.size(line)[0] <= 300 for line in lines)
