"""The water layer of a level (water world).

Water is a layer of its own beside the tile grid, so coins, enemies and
decor can sit in it: `Tilemap.water` maps a tile (tx, ty) to its flow, 0
for still water or 1-4 for a current (right, left, up, down; the push per
flow is WATER_CURRENTS in scripts/constants.py). Map files store it as
runs of equal flow, `[ty, tx0, tx1, flow]`, under map_data["water"].

Entities read the layer in scripts/entities.py. `WaterRenderer` draws it
in two layers: behind the level a dense blue that darkens with depth (the
sea instead of the sky), and over it a light tint, so tiles, coins and
entities in the water stay readable but look submerged, a moving wave
crest where the water meets open air, streaks along horizontal and
downward currents, and rising bubbles in up-currents.
"""

from __future__ import annotations

import pygame

# Back layer by depth (tiles of water above); deeper tiles use the last one
DEPTH_COLORS = ((66, 160, 214), (56, 144, 204), (48, 128, 192), (40, 112, 178), (32, 96, 164), (26, 82, 150))
BACK_ALPHA = 220
# Front tint over the level, a little stronger with depth
WATER_COLOR = (34, 112, 190)
DEPTH_ALPHA = (40, 46, 52, 58, 64, 70)
SURFACE_ALPHA = 230
CURRENT_ALPHA = 110
BUBBLES_ALPHA = 170
FRAME_TICKS = 8  # simulation ticks per overlay animation frame
CREST_H = 4  # rows of the wave crest at the top of a surface tile


def water_from_rows(rows) -> dict:
    """Map-file runs [ty, tx0, tx1, flow] -> {(tx, ty): flow}."""
    water = {}
    for ty, x0, x1, flow in rows:
        for tx in range(x0, x1 + 1):
            water[(tx, ty)] = flow
    return water


def water_to_rows(water: dict) -> list:
    """{(tx, ty): flow} -> runs [ty, tx0, tx1, flow], top to bottom."""
    rows: list = []
    for tx, ty in sorted(water, key=lambda t: (t[1], t[0])):
        flow = water[(tx, ty)]
        if rows and rows[-1][0] == ty and rows[-1][2] == tx - 1 and rows[-1][3] == flow:
            rows[-1][2] = tx
        else:
            rows.append([ty, tx, tx, flow])
    return rows


def _translucent(img: pygame.Surface, alpha: int) -> pygame.Surface:
    """Colorkeyed asset -> per-pixel alpha copy at `alpha` (fast to blend)."""
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    out.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return out


class WaterRenderer:
    """Draws one level's water. Built once per map, cheap per frame: the
    layer is kept as horizontal runs per row, each drawn with one blit."""

    def __init__(self, water: dict, assets, is_solid, tile_size: int = 16) -> None:
        self.ts = tile_size
        self.assets = assets
        # ty -> [[tx0, tx1, depth, crest], ...] and ty -> [(tx, flow), ...]
        self.rows: dict = {}
        self.currents: dict = {}
        depth: dict = {}
        last = len(DEPTH_ALPHA) - 1
        for tx, ty in sorted(water, key=lambda t: (t[1], t[0])):  # top-down: the tile above is done
            d = depth.get((tx, ty - 1), -1) + 1
            depth[(tx, ty)] = d
            # The crest shows only where the water meets open air, not a ceiling
            crest = d == 0 and not is_solid(tx, ty - 1)
            d = min(d, last)
            runs = self.rows.setdefault(ty, [])
            if runs and runs[-1][1] == tx - 1 and runs[-1][2] == d and runs[-1][3] == crest:
                runs[-1][1] = tx
            else:
                runs.append([tx, tx, d, crest])
            flow = water[(tx, ty)]
            if flow:
                self.currents.setdefault(ty, []).append((tx, flow))
        self._width = 0
        self._back: list = []
        self._body: list = []
        self._crest: list = []
        self._overlays: dict = {}

    def _build(self, width: int) -> None:
        """Strips one screen wide (runs blit a part of them) and overlay frames."""
        ts = self.ts
        w = (width // ts + 2) * ts
        self._width = width
        self._back = []
        for color in DEPTH_COLORS:
            strip = pygame.Surface((w, ts), pygame.SRCALPHA)
            strip.fill(color + (BACK_ALPHA,))
            self._back.append(strip)
        self._body = []
        for alpha in DEPTH_ALPHA:
            strip = pygame.Surface((w, ts), pygame.SRCALPHA)
            strip.fill(WATER_COLOR + (alpha,))
            self._body.append(strip)
        self._crest = []
        for frame in self.assets["water/surface"]:
            strip = pygame.Surface((w, frame.get_height()))
            strip.fill((0, 0, 0))
            for x in range(0, w, ts):
                strip.blit(frame, (x, 0))
            strip.set_colorkey((0, 0, 0))
            self._crest.append(_translucent(strip, SURFACE_ALPHA))
        current = self.assets["water/current"]
        self._overlays = {
            1: [_translucent(f, CURRENT_ALPHA) for f in current],
            2: [_translucent(pygame.transform.flip(f, True, False), CURRENT_ALPHA) for f in current],
            3: [_translucent(f, BUBBLES_ALPHA) for f in self.assets["water/bubbles"]],
            4: [_translucent(pygame.transform.rotate(f, -90), CURRENT_ALPHA) for f in current],
        }

    def _visible(self, surf: pygame.Surface, offset):
        """Rows on screen with their runs, and the first and last tile column on screen."""
        ts = self.ts
        width, height = surf.get_size()
        if width != self._width:
            self._build(width)
        ox, oy = offset
        rows = [(ty, self.rows[ty]) for ty in range(oy // ts, (oy + height) // ts + 1) if ty in self.rows]
        return rows, ox // ts, (ox + width) // ts

    def render_back(self, surf: pygame.Surface, offset) -> None:
        """The sea behind the level, in place of the sky."""
        ts, (ox, oy), blit = self.ts, offset, surf.blit
        rows, x0, x1 = self._visible(surf, offset)
        back = self._back
        for ty, runs in rows:
            py = ty * ts - oy
            for a, b, d, _top in runs:
                if b >= x0 and a <= x1:
                    a, b = max(a, x0), min(b, x1)
                    blit(back[d], (a * ts - ox, py), (0, 0, (b - a + 1) * ts, ts))

    def render(self, surf: pygame.Surface, offset, tick: int) -> None:
        """The tint, the crest and the currents over the level."""
        ts, (ox, oy), blit = self.ts, offset, surf.blit
        rows, x0, x1 = self._visible(surf, offset)
        frame = (tick // FRAME_TICKS) % 4
        body, crest = self._body, self._crest[frame]
        for ty, runs in rows:
            py = ty * ts - oy
            for a, b, d, top in runs:
                if b >= x0 and a <= x1:
                    a, b = max(a, x0), min(b, x1)
                    px, w = a * ts - ox, (b - a + 1) * ts
                    blit(body[d], (px, py), (0, 0, w, ts))
                    if top:
                        blit(crest, (px, py), (0, 0, w, CREST_H))
            for tx, flow in self.currents.get(ty, ()):
                if x0 <= tx <= x1:
                    blit(self._overlays[flow][frame], (tx * ts - ox, py))


__all__ = ["WaterRenderer", "water_from_rows", "water_to_rows"]
