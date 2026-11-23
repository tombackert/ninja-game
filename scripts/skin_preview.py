"""Item stage for the store and accessories menus.

A small scene in the game's own look (sky, a strip of grass) with the
ninja standing on it, scaled up so every pixel of a skin shows. For a skin
the ninja plays its moves one after another (idle, a few run cycles, jump,
slide, wall slide, swim); for a weapon it holds the weapon the way it does
in a level.

Skin frames come from the folders the game loads
(data/images/entities/player/<path>). Smaller frames (the default skin's
14x18) sit in the 20x22 box of the larger skins the way the game draws
them: centered, feet on the bottom row.
"""

from __future__ import annotations

import os

import pygame

PLAYER_DIR = "data/images/entities/player"
BOX = (20, 22)
TICKS_PER_SECOND = 60

# Stage in game pixels: sky, grass from GROUND_Y down, the ninja centered
STAGE = (96, 56)
GROUND_Y = 40

# (animation, game ticks per frame, loops); tick counts as in game.py
SEQUENCE = [
    ("idle", 6, 1),
    ("run", 4, 3),
    ("jump", 40, 1),
    ("slide", 40, 1),
    ("wall_slide", 40, 1),
    ("swim", 8, 2),
]


def _load_frames(path: str, anim: str) -> list[pygame.Surface]:
    d = os.path.join(PLAYER_DIR, path, anim)
    frames = []
    for name in sorted(n for n in os.listdir(d) if n.endswith(".png")):
        img = pygame.image.load(os.path.join(d, name))
        img.set_colorkey((0, 0, 0))
        box = pygame.Surface(BOX, pygame.SRCALPHA)
        box.blit(img, ((BOX[0] - img.get_width()) // 2, BOX[1] - img.get_height()))
        frames.append(box)
    return frames


def _load_image(rel: str) -> pygame.Surface:
    img = pygame.image.load(os.path.join("data/images", rel))
    img.set_colorkey((0, 0, 0))
    return img


class SkinPreview:
    """Plays one skin's showcase; `frame()` is the current 20x22 frame."""

    _timelines: dict = {}  # (path, showcase) -> [(frame, ticks)]
    _anims: dict = {}  # (path, anim) -> frames
    _backdrop: pygame.Surface | None = None

    def __init__(self) -> None:
        self.path: str | None = None
        self.showcase = True
        self.ticks = 0.0

    def set_skin(self, path: str, showcase: bool = True) -> None:
        """showcase False: idle only (the ninja posing with a weapon)."""
        if (path, showcase) != (self.path, self.showcase):
            self.path, self.showcase = path, showcase
            self.ticks = 0.0

    def update(self, dt: float) -> None:
        self.ticks += dt * TICKS_PER_SECOND

    def _timeline(self) -> list:
        assert self.path is not None  # frame() returns early without a skin
        key = (self.path, self.showcase)
        timeline = SkinPreview._timelines.get(key)
        if timeline is None:
            timeline = []
            for anim, dur, loops in SEQUENCE if self.showcase else SEQUENCE[:1]:
                frames = _load_frames(self.path, anim)
                timeline += [(img, dur) for _ in range(loops) for img in frames]
            SkinPreview._timelines[key] = timeline
        return timeline

    def frame(self) -> pygame.Surface | None:
        if self.path is None:
            return None
        timeline = self._timeline()
        t = self.ticks % sum(d for _, d in timeline)
        for img, dur in timeline:
            if t < dur:
                return img
            t -= dur
        return timeline[-1][0]

    def anim_frame(self, anim: str, ticks: float) -> pygame.Surface | None:
        """Frame of one move of the current skin at `ticks` (timing as in game.py)."""
        if self.path is None:
            return None
        key = (self.path, anim)
        frames = SkinPreview._anims.get(key)
        if frames is None:
            frames = SkinPreview._anims[key] = _load_frames(self.path, anim)
        dur = next((d for a, d, _ in SEQUENCE if a == anim), 6)
        return frames[int(ticks // dur) % len(frames)]

    @classmethod
    def backdrop(cls) -> pygame.Surface:
        """Sky and grass of the stage, in game pixels."""
        if cls._backdrop is None:
            sky = pygame.image.load("data/images/background.png")
            stage = pygame.Surface(STAGE)
            stage.blit(sky, (0, 0), pygame.Rect(150, 130, *STAGE))
            top = _load_image("tiles/grass/1.png")
            fill = _load_image("tiles/grass/8.png")
            for x in range(0, STAGE[0], top.get_width()):
                stage.blit(top, (x, GROUND_Y))
                stage.blit(fill, (x, GROUND_Y + top.get_height()))
            cls._backdrop = stage
        return cls._backdrop

    def render_stage(self, surface: pygame.Surface, rect: pygame.Rect, held: str | None = None, scene=None) -> None:
        """Draw the stage into `rect` (a multiple of STAGE): the ninja, holding
        `held` (an image under data/images); or an item's `scene`
        (scripts/item_showcase.py), which draws the ninja itself."""
        stage = self.backdrop().copy()
        feet = (STAGE[0] // 2, GROUND_Y)
        if scene is not None:
            scene.draw(stage, self, self.ticks)
        else:
            img = self.frame()
            if img is not None:
                stage.blit(img, (feet[0] - BOX[0] // 2, feet[1] - BOX[1]))
            if held is not None:
                stage.blit(_load_image(held), (feet[0] + 4, feet[1] - 8))
        surface.blit(pygame.transform.scale(stage, rect.size), rect.topleft)


def wrap_text(font: pygame.font.Font, text: str, width: int) -> list[str]:
    """Split `text` into lines no wider than `width` pixels."""
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and font.size(candidate)[0] > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines
