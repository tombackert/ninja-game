"""Drawing for the level editor (editor.py): theme, fonts and the map view.

The map is drawn at any zoom from chunks of CHUNK x CHUNK tiles: each chunk
is drawn once at the map's own size (1 px per world px) and scaled to the
zoom once, so a whole map of 20,000 tiles stays a few hundred blits a frame.
An edit redraws only the chunks it touched. Zooms are multiples of 1/16, so
a tile is a whole number of screen pixels and chunks meet without seams.

The UI (panels, text) is drawn straight onto the window at its own
resolution with a system font, not onto the game's 640x360 surface.
"""

from __future__ import annotations

import math
from collections import OrderedDict

import pygame

TS = 16
CHUNK = 16  # tiles per chunk side
CHUNK_PX = CHUNK * TS
ZOOM_STEP = 1 / 16  # a tile is 16 * zoom screen pixels: whole pixels
MIN_ZOOM = 1 / 16
MAX_ZOOM = 8.0
DEFAULT_ZOOM = 2.0
SCALED_BUDGET = 48_000_000  # pixels of scaled chunks kept for the current zoom

# --- theme -----------------------------------------------------------------------
BG = (22, 24, 29)
PANEL = (30, 33, 40)
PANEL_2 = (38, 42, 51)
PANEL_3 = (48, 53, 64)
BORDER = (58, 63, 75)
TEXT = (230, 233, 240)
DIM = (150, 157, 172)
FAINT = (105, 112, 128)
ACCENT = (82, 150, 255)
ACCENT_DIM = (44, 78, 132)
OK = (84, 204, 126)
WARN = (242, 184, 64)
ERR = (238, 86, 86)
CANVAS = (196, 220, 238)  # sky behind the map
GRID = (0, 0, 0, 22)
CURSOR = (255, 255, 255)

UI_FONTS = "sfprotext,helveticaneue,segoeui,helvetica,arial"
MONO_FONTS = "menlo,sfmono,consolas,dejavusansmono"


def clamp_zoom(z: float) -> float:
    z = round(z / ZOOM_STEP) * ZOOM_STEP
    return max(MIN_ZOOM, min(MAX_ZOOM, z))


def zoom_label(z: float) -> str:
    pct = z * 100
    return f"{pct:.0f} %" if pct >= 10 else f"{pct:.1f} %"


def scale_image(img: pygame.Surface, size: tuple) -> pygame.Surface:
    """Pixel art scaled to `size`: sharp pixels when enlarged, smoothed when shrunk."""
    w, h = max(1, size[0]), max(1, size[1])
    if (w, h) == img.get_size():
        return img
    if w < img.get_width() or h < img.get_height():
        src = img if img.get_bitsize() in (24, 32) else img.convert_alpha()
        return pygame.transform.smoothscale(src, (w, h))
    return pygame.transform.scale(img, (w, h))


class Fonts:
    """System fonts at the window's resolution, and a cache of rendered text."""

    def __init__(self):
        pygame.font.init()
        self.small = self._font(UI_FONTS, 13)
        self.ui = self._font(UI_FONTS, 15)
        self.bold = self._font(UI_FONTS, 15, bold=True)
        self.title = self._font(UI_FONTS, 17, bold=True)
        self.mono = self._font(MONO_FONTS, 13)
        self._cache: OrderedDict = OrderedDict()

    @staticmethod
    def _font(names: str, size: int, bold: bool = False) -> pygame.font.Font:
        try:
            font = pygame.font.SysFont(names, size, bold=bold)
        except Exception:  # no system font list (some headless setups)
            font = pygame.font.Font(None, size + 4)
            font.set_bold(bold)
        return font

    def text(self, s: str, font: pygame.font.Font | None = None, color=TEXT) -> pygame.Surface:
        font = font or self.ui
        key = (s, id(font), color)
        img = self._cache.get(key)
        if img is None:
            img = font.render(s, True, color)
            self._cache[key] = img
            if len(self._cache) > 2000:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)
        return img


def draw_text(surf, fonts: Fonts, s: str, pos, font=None, color=TEXT, anchor: str = "topleft") -> pygame.Rect:
    img = fonts.text(s, font, color)
    r = img.get_rect(**{anchor: pos})
    surf.blit(img, r)
    return r


def fit_text(fonts: Fonts, s: str, font, width: int) -> str:
    """`s`, cut with an ellipsis to fit `width` px."""
    if font.size(s)[0] <= width:
        return s
    while s and font.size(s + "…")[0] > width:
        s = s[:-1]
    return s + "…"


def key_chip_width(fonts: Fonts, label: str) -> int:
    return fonts.small.size(label)[0] + 12


def key_chip(surf, fonts: Fonts, label: str, pos) -> pygame.Rect:
    """A keyboard key drawn as a small rounded chip; returns its rect."""
    img = fonts.text(label, fonts.small, TEXT)
    r = pygame.Rect(pos[0], pos[1], img.get_width() + 12, img.get_height() + 4)
    pygame.draw.rect(surf, PANEL_3, r, border_radius=4)
    pygame.draw.rect(surf, BORDER, r, 1, border_radius=4)
    surf.blit(img, img.get_rect(center=r.center))
    return r


# --- the map ---------------------------------------------------------------------


class WorldView:
    """The map (tiles, offgrid decor, water) drawn in chunks at a zoom.

    `assets` maps a tile type to its images; `skip` names tile types drawn
    elsewhere (the spawners, as their characters); `water_icons[flow]` is the
    image a water tile shows."""

    def __init__(self, tilemap, assets: dict, water_icons: list, skip: tuple = ("spawners",)):
        self.tilemap = tilemap
        self.assets = assets
        self.water_icons = water_icons
        self.skip = set(skip)
        self.raw: dict = {}  # (cx, cy) -> Surface | None at 1 px per world px
        self.scaled: OrderedDict = OrderedDict()  # (cx, cy) -> Surface at self.zoom
        self.scaled_px = 0
        self.zoom = None
        self._offgrid_index: dict | None = None

    # -- invalidation --
    def invalidate_all(self) -> None:
        self.raw.clear()
        self.scaled.clear()
        self.scaled_px = 0
        self._offgrid_index = None

    def invalidate_tiles(self, tiles) -> None:
        for tx, ty in tiles:
            self._drop((tx // CHUNK, ty // CHUNK))

    def invalidate_px_rect(self, rect: pygame.Rect) -> None:
        """Chunks under a world-px rect (an offgrid tile) and the offgrid index."""
        self._offgrid_index = None
        for cx in range(rect.left // CHUNK_PX, (rect.right - 1) // CHUNK_PX + 1):
            for cy in range(rect.top // CHUNK_PX, (rect.bottom - 1) // CHUNK_PX + 1):
                self._drop((cx, cy))

    def _drop(self, key) -> None:
        self.raw.pop(key, None)
        img = self.scaled.pop(key, None)
        if img is not None:
            self.scaled_px -= img.get_width() * img.get_height()

    # -- building --
    def image(self, tile: dict) -> pygame.Surface | None:
        imgs = self.assets.get(tile["type"])
        if not imgs:
            return None
        v = tile.get("variant", 0)
        return imgs[v] if 0 <= v < len(imgs) else None

    def offgrid_rect(self, tile: dict) -> pygame.Rect | None:
        img = self.image(tile)
        if img is None:
            return None
        return pygame.Rect(int(tile["pos"][0]), int(tile["pos"][1]), img.get_width(), img.get_height())

    def _offgrid_by_chunk(self) -> dict:
        if self._offgrid_index is None:
            index: dict = {}
            for tile in self.tilemap.offgrid_tiles:
                if tile["type"] in self.skip:
                    continue
                r = self.offgrid_rect(tile)
                if r is None:
                    continue
                for cx in range(r.left // CHUNK_PX, (r.right - 1) // CHUNK_PX + 1):
                    for cy in range(r.top // CHUNK_PX, (r.bottom - 1) // CHUNK_PX + 1):
                        index.setdefault((cx, cy), []).append(tile)
            self._offgrid_index = index
        return self._offgrid_index

    def _build(self, key) -> pygame.Surface | None:
        cx, cy = key
        ox, oy = cx * CHUNK_PX, cy * CHUNK_PX
        surf = None

        def canvas():
            nonlocal surf
            if surf is None:
                surf = pygame.Surface((CHUNK_PX, CHUNK_PX), pygame.SRCALPHA)
            return surf

        for tile in self._offgrid_by_chunk().get(key, ()):  # under the grid tiles, as in the game
            img = self.image(tile)
            canvas().blit(img, (int(tile["pos"][0]) - ox, int(tile["pos"][1]) - oy))
        tm, water = self.tilemap.tilemap, self.tilemap.water
        for tx in range(cx * CHUNK, cx * CHUNK + CHUNK):
            for ty in range(cy * CHUNK, cy * CHUNK + CHUNK):
                tile = tm.get(f"{tx};{ty}")
                if tile is not None and tile["type"] not in self.skip:
                    img = self.image(tile)
                    if img is not None:
                        canvas().blit(img, (tx * TS - ox, ty * TS - oy))
                flow = water.get((tx, ty))
                if flow is not None and 0 <= flow < len(self.water_icons):
                    canvas().blit(self.water_icons[flow], (tx * TS - ox, ty * TS - oy))
        return surf

    def chunk(self, key, zoom: float) -> pygame.Surface | None:
        if zoom != self.zoom:
            self.scaled.clear()
            self.scaled_px = 0
            self.zoom = zoom
        if key in self.scaled:
            self.scaled.move_to_end(key)
            return self.scaled[key]
        if key not in self.raw:
            self.raw[key] = self._build(key)
        raw = self.raw[key]
        img = None
        if raw is not None:
            size = round(CHUNK_PX * zoom)
            img = scale_image(raw, (size, size))
            self.scaled_px += size * size
        self.scaled[key] = img
        while self.scaled_px > SCALED_BUDGET and len(self.scaled) > 1:
            _, old = self.scaled.popitem(last=False)
            if old is not None:
                self.scaled_px -= old.get_width() * old.get_height()
        return img

    def render(self, surf: pygame.Surface, cam: tuple, zoom: float) -> None:
        """Draw the map onto `surf` (the viewport) with world px `cam` at its top left."""
        size = round(CHUNK_PX * zoom)
        ox, oy = round(cam[0] * zoom), round(cam[1] * zoom)
        w, h = surf.get_size()
        for cx in range(math.floor(ox / size), math.floor((ox + w) / size) + 1):
            for cy in range(math.floor(oy / size), math.floor((oy + h) / size) + 1):
                img = self.chunk((cx, cy), zoom)
                if img is not None:
                    surf.blit(img, (cx * size - ox, cy * size - oy))


def map_bounds(tilemap) -> pygame.Rect | None:
    """World px rect around every tile of the map (grid and offgrid), None when empty."""
    xs, ys = [], []
    for tile in tilemap.tilemap.values():
        xs.append(tile["pos"][0])
        ys.append(tile["pos"][1])
    if not xs and not tilemap.offgrid_tiles:
        return None
    rect = None
    if xs:
        rect = pygame.Rect(min(xs) * TS, min(ys) * TS, (max(xs) - min(xs) + 1) * TS, (max(ys) - min(ys) + 1) * TS)
    for tile in tilemap.offgrid_tiles:
        r = pygame.Rect(int(tile["pos"][0]), int(tile["pos"][1]), TS, TS)
        rect = r if rect is None else rect.union(r)
    return rect
