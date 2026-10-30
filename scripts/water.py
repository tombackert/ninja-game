"""The water layer of a level (water world).

Water is a layer of its own beside the tile grid, so coins, enemies and
decor can sit in it: `Tilemap.water` maps a tile (tx, ty) to its flow, 0
for still water or 1-4 for a current (right, left, up, down; the push per
flow is WATER_CURRENTS in scripts/constants.py). Map files store it as
runs of equal flow, `[ty, tx0, tx1, flow]`, under map_data["water"].
Water has to be held like real water: rock or more water beside and
under every water tile (`water_leaks` lists where it would run out), so
air only ever sits over water, as its surface or trapped under rock.

Entities read the layer in scripts/entities.py. `WaterRenderer` draws it
as one body of water: its colour follows a single smooth gradient by
depth below the level's highest water row, so pools, shafts, caves and
currents all read as the same sea. Behind the level a dense blue (the sea
instead of the sky), over it a light tint, so tiles, coins and entities
in the water stay readable but look submerged, and a moving wave crest
where the water meets open air. Currents only add sparse light streaks
(rising bubbles in up-currents) that drift with the flow and fade out
towards the current's edges. Air pockets, air trapped under rock, are
drawn as hollows in the rock: a dark back wall of the surrounding tile,
lit from the water below with moving reflections, rounded top corners and
dripstones hanging from the ceiling.
"""

from __future__ import annotations

import math
import random
from collections import Counter, deque

import pygame

from scripts.constants import WATER_CURRENTS

RIGHT, LEFT, UP, DOWN = 1, 2, 3, 4

# One gradient for the whole level, by depth below its highest water row
SHALLOW_COLOR = (68, 162, 216)
DEEP_COLOR = (24, 76, 142)
GRADIENT_ROWS = 40  # tiles down to the deepest colour
BACK_ALPHA = (216, 255)  # shallow, deep: the sky shows through only near the top
# Front tint over the level, a little stronger with depth
WATER_COLOR = (34, 112, 190)
SHALLOW_ALPHA, DEEP_ALPHA = 40, 72
SURFACE_ALPHA = 230
FRAME_TICKS = 8  # simulation ticks per crest frame
CREST_H = 4  # rows of the wave crest at the top of a surface tile

# Currents: lanes of streaks inside the current, a few per tile
STREAK_COLOR = (178, 228, 250)
STREAK_ALPHA = 130
BUBBLE_ALPHA = 200
LANE_OFFSETS = (3, 8, 13)  # lane positions across a tile, jittered by a pixel
STREAK_GAP = (40, 88)  # px between the streaks of a lane
STREAK_LEN = (4, 8)
FADE_PX = 28  # streaks fade in and out over this distance from a current's ends
FADE_LEVELS = 4
STREAK_SPEED = 1.3  # streak speed per px/frame of the current's push

# Air pockets: enclosed air over water, up to this many tiles. The back
# wall is the surrounding rock lit by the water's blue glow from below
POCKET_MAX = 400
GLOW_LOW = (176, 214, 236)  # light on the back wall just over the water
GLOW_HIGH = (92, 104, 132)  # and under the ceiling
GLOW_ROCK = (70, 78, 100)  # behind the rock around the pocket
CORNER_R = 20  # rounded top corners, at most (less in low pockets)
CAUSTIC_COLOR = (36, 56, 68)  # added light where the water's ripples focus it
CAUSTIC_TILE = 64  # px, the caustic net repeats seamlessly
CAUSTIC_FRAMES = 8
CAUSTIC_TICKS = 7
# Air in a wreck is a ship's hold: square corners, moss hanging off the deck
MOSS = ((80, 118, 76), (110, 152, 96))


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


def water_leaks(water: dict, is_solid) -> list:
    """Air tiles the water would run into: beside or under a water tile
    (rock in the water holds itself). Empty for a level whose water is held."""
    leaks = set()
    for tx, ty in water:
        if is_solid(tx, ty):
            continue
        for n in ((tx - 1, ty), (tx + 1, ty), (tx, ty + 1)):
            if n not in water and not is_solid(*n):
                leaks.add(n)
    return sorted(leaks, key=lambda t: (t[1], t[0]))


def depth_shade(d_px: float, ts: int = 16) -> float:
    """0 at the top water row, 1 at GRADIENT_ROWS down; light fades fastest near the top."""
    t = min(max(d_px / (GRADIENT_ROWS * ts), 0.0), 1.0)
    return 1 - (1 - t) ** 2


def _mix(a, b, t: float) -> tuple:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _translucent(img: pygame.Surface, alpha: int) -> pygame.Surface:
    """Colorkeyed asset -> per-pixel alpha copy at `alpha` (fast to blend)."""
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    out.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def _streak(length: int, level: int, flow: int) -> pygame.Surface:
    """A streak with its head downstream, brightest at the head."""
    img = pygame.Surface((length, 1), pygame.SRCALPHA)
    for i in range(length):
        img.set_at((i, 0), STREAK_COLOR + (STREAK_ALPHA * level * (i + 1) // (FADE_LEVELS * length),))
    if flow == LEFT:
        img = pygame.transform.flip(img, True, False)
    elif flow in (UP, DOWN):
        img = pygame.transform.rotate(img, 90 if flow == UP else -90)
    return img


def current_lanes(water: dict, is_solid, ts: int = 16, seed: int = 7):
    """Streak lanes along each current, split where rock stands in it.

    Horizontal flows: tile row -> lanes; vertical flows: tile column ->
    lanes. A lane is (across px, start px, end px, flow, speed, gap,
    phase, length, k), k its index across the tile (0 and 2 border the
    neighbouring tiles).
    """
    rng = random.Random(seed)
    by_row: dict = {}
    by_col: dict = {}
    for flow, index, key in ((RIGHT, by_row, 1), (LEFT, by_row, 1), (UP, by_col, 0), (DOWN, by_col, 0)):
        cells = sorted(
            (t[key], t[1 - key]) for t, f in water.items() if f == flow and not is_solid(*t)
        )  # (fixed, along)
        runs: list = []
        for fixed, along in cells:
            if runs and runs[-1][0] == fixed and runs[-1][2] == along - 1:
                runs[-1][2] = along
            else:
                runs.append([fixed, along, along])
        for fixed, a, b in runs:
            for k, off in enumerate(LANE_OFFSETS):
                across = fixed * ts + off + rng.randint(-1, 1)
                speed = sum(map(abs, WATER_CURRENTS[flow])) * STREAK_SPEED * rng.uniform(0.8, 1.25)
                gap = rng.randint(*STREAK_GAP)
                if flow == UP:
                    gap //= 2  # geysers: plenty of bubbles
                phase, length = rng.uniform(0, gap), rng.randint(*STREAK_LEN)
                index.setdefault(fixed, []).append((across, a * ts, (b + 1) * ts, flow, speed, gap, phase, length, k))
    return by_row, by_col


def find_pockets(water: dict, solid_type, limit: int = POCKET_MAX) -> list:
    """Air trapped over water: connected air tiles (neither rock nor water)
    that rock and water close in, at most `limit` tiles, standing on water
    for at least half their floor (a dry cave by a pool is no pocket)."""
    seen: set = set()
    pockets = []
    for tx, ty in sorted(water):
        start = (tx, ty - 1)
        if start in water or start in seen or solid_type(*start):
            continue
        region, queue, enclosed = {start}, deque([start]), True
        while queue and enclosed:
            cx, cy = queue.popleft()
            for n in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if n in region or n in water or solid_type(*n):
                    continue
                region.add(n)
                queue.append(n)
                if len(region) > limit:
                    enclosed = False
                    break
        seen |= region
        floor = [(x, y + 1) for x, y in region if (x, y + 1) not in region]
        if enclosed and 2 * sum(t in water for t in floor) >= len(floor):
            pockets.append(region)
    return pockets


_caustic_tiles: list = []


def caustic_tiles() -> list:
    """CAUSTIC_FRAMES seamless tiles of the caustic net, light added on black.

    Two families of wavy lines (where a wave crosses zero) run across each
    other into a net of cells; every wave fits the tile a whole number of
    times and every phase turns a whole number of times per loop, so the
    net tiles and loops without a seam.
    """
    if not _caustic_tiles:
        n, k = CAUSTIC_TILE, 2 * math.pi / CAUSTIC_TILE
        for f in range(CAUSTIC_FRAMES):
            p = f * 2 * math.pi / CAUSTIC_FRAMES
            tile = pygame.Surface((n, n))
            tile.fill((0, 0, 0))
            for x in range(n):
                for y in range(n):
                    a = math.sin(k * (x + 2 * y) + p + 1.1 * math.sin(k * (2 * x - y) - p))
                    b = math.sin(k * (2 * x - y) - p + 1.1 * math.sin(k * (x + 2 * y) + 2 * p))
                    ridge = max(1 - abs(a) * 4, 1 - abs(b) * 4)
                    if ridge > 0:
                        tile.set_at((x, y), _mix((0, 0, 0), CAUSTIC_COLOR, min(1.0, ridge * 1.5)))
            _caustic_tiles.append(tile)
    return _caustic_tiles


class Pocket:
    """One air pocket, drawn as a hollow in the rock: a back wall behind the
    level and the hollow's rounded rock in front of it, with the tiles."""

    def __init__(self, region: set, water: dict, solid_type, assets, ts: int, rng: random.Random) -> None:
        self.ts = ts
        self.region = region
        # Air plus the rock around it: rock tiles have see-through corners
        cover = set(region)
        types: Counter = Counter()
        for tx, ty in region:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    t = solid_type(tx + dx, ty + dy)
                    if t:
                        cover.add((tx + dx, ty + dy))
                        types[t] += 1
        self.x0 = min(x for x, _ in cover)
        self.y0 = min(y for _, y in cover)
        self.x1 = max(x for x, _ in cover)
        self.y1 = max(y for _, y in cover)
        self.rows: dict = {}  # ty -> [[tx0, tx1], ...]
        for tx, ty in sorted(cover, key=lambda t: (t[1], t[0])):
            runs = self.rows.setdefault(ty, [])
            if runs and runs[-1][1] == tx - 1:
                runs[-1][1] = tx
            else:
                runs.append([tx, tx])
        kind = types.most_common(1)[0][0] if types else None
        self.wreck = kind == "wreck"
        tiles = assets.get(kind)
        self.tex = tiles[8] if tiles and len(tiles) > 8 else (tiles[0] if tiles else None)
        self.size = ((self.x1 - self.x0 + 1) * ts, (self.y1 - self.y0 + 1) * ts)
        shapes = self._shapes(solid_type, rng)
        self.rock = self._rock(shapes)
        back = self._back_wall()
        self.frames = self._caustics(back, water)

    def _air(self, x: int, y: int) -> bool:
        return (x // self.ts + self.x0, y // self.ts + self.y0) in self.region

    def _texture(self, w: int, h: int) -> pygame.Surface:
        """The surrounding tile repeated over w x h px, aligned with the tile grid."""
        ts = self.ts
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((62, 84, 104, 255))  # the reef's rock, should the tile be missing
        if self.tex:
            for x in range(0, w, ts):
                for y in range(0, h, ts):
                    surf.blit(self.tex, (x, y))
        return surf

    def _back_wall(self) -> pygame.Surface:
        """The rock behind the pocket in the water's glow: blue light from
        below that fades towards the ceiling and behind the rock around."""
        ts = self.ts
        back = self._texture(*self.size)
        top = min(y for _, y in self.region)
        bottom = max(y for _, y in self.region)
        light = pygame.Surface((self.x1 - self.x0 + 3, self.y1 - self.y0 + 3))
        light.fill(GLOW_ROCK)
        for tx, ty in self.region:
            t = 1 - (bottom - ty) / max(1, bottom - top)
            light.set_at((tx - self.x0 + 1, ty - self.y0 + 1), _mix(GLOW_HIGH, GLOW_LOW, t))
        # Scaled up smoothly, tile by tile light shades the hollow round
        light = pygame.transform.smoothscale(light, (light.get_width() * ts, light.get_height() * ts))
        back.blit(light, (0, 0), (ts, ts, *self.size), special_flags=pygame.BLEND_RGB_MULT)
        return back

    def _shapes(self, solid_type, rng: random.Random) -> dict:
        """Pixels the hollow keeps inside its tiles, pixel -> colour (None for
        the rock's own): rounded corners under the ceiling, bumps and
        dripstones on it and bulges in the walls; in a wreck moss strands."""
        ts = self.ts
        shapes: dict = {}

        def disc(cx, cy, r):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if dx * dx + dy * dy <= r * r + 1:
                        shapes[(cx + dx, cy + dy)] = None

        for tx, ty in sorted(self.region):
            px, py = (tx - self.x0) * ts, (ty - self.y0) * ts
            if self.wreck:
                if solid_type(tx, ty - 1):
                    for _ in range(rng.choice((0, 1, 2, 2))):
                        x, length = px + rng.randrange(ts), rng.randint(2, 7)
                        for i in range(length):
                            shapes[(x, py + i)] = MOSS[i < length - 2]
                continue
            if solid_type(tx, ty - 1):  # under the ceiling
                below = 1
                while (tx, ty + below) in self.region:
                    below += 1
                r = min(CORNER_R, below * ts * 5 // 12)
                for side in (-1, 1):
                    if solid_type(tx + side, ty):
                        for dy in range(r):
                            for dx in range(r):
                                if (r - dx - 0.5) ** 2 + (r - dy - 0.5) ** 2 > r * r:
                                    shapes[(px + dx if side < 0 else px + ts - 1 - dx, py + dy)] = None
                for _ in range(rng.choice((1, 2, 2, 3))):
                    disc(px + rng.randrange(ts), py - 1, rng.randint(2, 3))
                for _ in range(rng.choice((0, 1, 1, 2))):
                    cx, length = px + rng.randint(3, ts - 4), rng.randint(4, min(9, below * 5))
                    for i in range(length):
                        half = 1 if i < length // 2 else 0
                        shapes.update(((x, py + i), None) for x in range(cx - half, cx + half + 1))
            for side in (-1, 1):
                if solid_type(tx + side, ty) and rng.random() < 0.6:
                    edge = px - 1 if side < 0 else px + ts
                    disc(edge, py + rng.randint(4, ts - 5), rng.randint(2, 3))
        w, h = self.size
        return {p: c for p, c in shapes.items() if 0 <= p[0] < w and 0 <= p[1] < h and self._air(*p)}

    def _rock(self, shapes: dict) -> pygame.Surface:
        """The hollow's own rock, in the tile's colours, see-through elsewhere."""
        tex = self._texture(*self.size)
        rock = pygame.Surface(self.size, pygame.SRCALPHA)
        for p, color in shapes.items():
            rock.set_at(p, color or tex.get_at(p))
        return rock

    def _caustics(self, back: pygame.Surface, water) -> list:
        """The back wall with the light the water's ripples throw on it, one
        surface per frame: the caustic net, strongest just over the water."""
        ts = self.ts
        w, h = self.size
        fade = pygame.Surface((self.x1 - self.x0 + 3, self.y1 - self.y0 + 3))
        fade.fill((0, 0, 0))
        for tx in {x for x, _ in self.region}:
            bottom = max(y for x, y in self.region if x == tx)
            if (tx, bottom + 1) not in water:
                continue
            ty = bottom
            while (tx, ty) in self.region:
                v = 255 * (1 - 0.85 * (bottom - ty) / max(1, bottom - min(y for x, y in self.region if x == tx)))
                fade.set_at((tx - self.x0 + 1, ty - self.y0 + 1), (round(v),) * 3)
                ty -= 1
        fade = pygame.transform.smoothscale(fade, (fade.get_width() * ts, fade.get_height() * ts))
        # The net is aligned with the world, so pockets side by side match
        sx, sy = -(self.x0 * ts) % CAUSTIC_TILE, -(self.y0 * ts) % CAUSTIC_TILE
        frames = []
        for tile in caustic_tiles():
            layer = pygame.Surface((w, h))
            for x in range(-sx, w, CAUSTIC_TILE):
                for y in range(-sy, h, CAUSTIC_TILE):
                    layer.blit(tile, (x, y))
            layer.blit(fade, (0, 0), (ts, ts, w, h), special_flags=pygame.BLEND_RGB_MULT)
            frame = back.copy()
            frame.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            frames.append(frame)
        return frames

    def on_screen(self, offset, size) -> bool:
        ts, (ox, oy), (w, h) = self.ts, offset, size
        return (self.x1 + 1) * ts > ox and self.x0 * ts < ox + w and (self.y1 + 1) * ts > oy and self.y0 * ts < oy + h

    def render_back(self, surf: pygame.Surface, offset, tick: int) -> None:
        ts, (ox, oy) = self.ts, offset
        frame = self.frames[(tick // CAUSTIC_TICKS) % CAUSTIC_FRAMES]
        for ty, runs in self.rows.items():
            for a, b in runs:
                area = ((a - self.x0) * ts, (ty - self.y0) * ts, (b - a + 1) * ts, ts)
                surf.blit(frame, (a * ts - ox, ty * ts - oy), area)

    def render_rock(self, surf: pygame.Surface, offset) -> None:
        surf.blit(self.rock, (self.x0 * self.ts - offset[0], self.y0 * self.ts - offset[1]))


class WaterRenderer:
    """Draws one level's water. Built once per map, cheap per frame: the
    layer is kept as horizontal runs per row, each drawn with one blit."""

    def __init__(self, water: dict, assets, solid_type, tile_size: int = 16) -> None:
        self.ts = tile_size
        self.assets = assets
        self.water = water
        self.top = min(ty for _, ty in water) if water else 0

        def is_solid(tx, ty):
            return solid_type(tx, ty) is not None

        # ty -> [[tx0, tx1, crest], ...]
        self.rows: dict = {}
        for tx, ty in sorted(water, key=lambda t: (t[1], t[0])):
            # The crest shows only where the water meets open air, not a ceiling
            crest = (tx, ty - 1) not in water and not is_solid(tx, ty - 1)
            runs = self.rows.setdefault(ty, [])
            if runs and runs[-1][1] == tx - 1 and runs[-1][2] == crest:
                runs[-1][1] = tx
            else:
                runs.append([tx, tx, crest])
        self.lanes_h, self.lanes_v = current_lanes(water, is_solid, tile_size)
        rng = random.Random(11)
        self.pockets = [Pocket(r, water, solid_type, assets, tile_size, rng) for r in find_pockets(water, solid_type)]
        self._width = 0
        self._back = pygame.Surface((0, 0))
        self._body = pygame.Surface((0, 0))
        self._crest: list = []
        self._streaks: dict = {}
        self._bubbles: dict = {}

    def _build(self, width: int) -> None:
        """Gradients one screen wide (runs blit a part of them), crest frames and streaks."""
        ts = self.ts
        w = (width // ts + 2) * ts
        h = GRADIENT_ROWS * ts
        self._width = width
        self._back = pygame.Surface((w, h), pygame.SRCALPHA)
        self._body = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            t = depth_shade(y, ts)
            self._back.fill(_mix(SHALLOW_COLOR, DEEP_COLOR, t) + _mix(BACK_ALPHA[:1], BACK_ALPHA[1:], t), (0, y, w, 1))
            self._body.fill(WATER_COLOR + (round(SHALLOW_ALPHA + (DEEP_ALPHA - SHALLOW_ALPHA) * t),), (0, y, w, 1))
        self._crest = []
        for frame in self.assets["water/surface"]:
            strip = pygame.Surface((w, frame.get_height()))
            strip.fill((0, 0, 0))
            for x in range(0, w, ts):
                strip.blit(frame, (x, 0))
            strip.set_colorkey((0, 0, 0))
            self._crest.append(_translucent(strip, SURFACE_ALPHA))
        self._streaks = {
            (flow, length, level): _streak(length, level, flow)
            for flow in (RIGHT, LEFT, UP, DOWN)
            for length in range(STREAK_LEN[0], STREAK_LEN[1] + 1)
            for level in range(1, FADE_LEVELS + 1)
        }
        bubble = self.assets["particle/bubble"].images[:4]
        self._bubbles = {
            (size, level): _translucent(img, BUBBLE_ALPHA * level // FADE_LEVELS)
            for size, img in enumerate(bubble)
            for level in range(1, FADE_LEVELS + 1)
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

    def _gradient_y(self, ty: int) -> int:
        return min((ty - self.top) * self.ts, (GRADIENT_ROWS - 1) * self.ts)

    def render_back(self, surf: pygame.Surface, offset, tick: int = 0) -> None:
        """The sea behind the level, in place of the sky, and the air pockets' back walls."""
        ts, (ox, oy), blit = self.ts, offset, surf.blit
        for pocket in self.pockets:
            if pocket.on_screen(offset, surf.get_size()):
                pocket.render_back(surf, offset, tick)
        rows, x0, x1 = self._visible(surf, offset)
        back = self._back
        for ty, runs in rows:
            py, gy = ty * ts - oy, self._gradient_y(ty)
            for a, b, _crest in runs:
                if b >= x0 and a <= x1:
                    a, b = max(a, x0), min(b, x1)
                    blit(back, (a * ts - ox, py), (0, gy, (b - a + 1) * ts, ts))

    def render_rock(self, surf: pygame.Surface, offset) -> None:
        """The air pockets' rounded rock, drawn with the tiles (so it gets their outline)."""
        for pocket in self.pockets:
            if pocket.on_screen(offset, surf.get_size()):
                pocket.render_rock(surf, offset)

    def render(self, surf: pygame.Surface, offset, tick: int) -> None:
        """The tint, the crest and the currents over the level."""
        ts, (ox, oy), blit = self.ts, offset, surf.blit
        rows, x0, x1 = self._visible(surf, offset)
        body, crest = self._body, self._crest[(tick // FRAME_TICKS) % len(self._crest)]
        for ty, runs in rows:
            py, gy = ty * ts - oy, self._gradient_y(ty)
            for a, b, top in runs:
                if b >= x0 and a <= x1:
                    a, b = max(a, x0), min(b, x1)
                    px, w = a * ts - ox, (b - a + 1) * ts
                    blit(body, (px, py), (0, gy, w, ts))
                    if top:
                        blit(crest, (px, py), (0, 0, w, CREST_H))
        self._render_currents(surf, offset, tick)

    def _render_currents(self, surf: pygame.Surface, offset, tick: int) -> None:
        """Streaks drift along each lane; near a current's ends, and where a
        border lane runs past still water, they fade."""
        ts, (ox, oy) = self.ts, offset
        width, height = surf.get_size()
        water, streaks, bubbles = self.water, self._streaks, self._bubbles
        draw = []
        for horizontal, lanes, lo, hi, cross_lo, cross_hi in (
            (True, self.lanes_h, ox - ts, ox + width + ts, oy // ts, (oy + height) // ts),
            (False, self.lanes_v, oy - ts, oy + height + ts, ox // ts, (ox + width) // ts),
        ):
            for fixed in range(cross_lo, cross_hi + 1):
                for across, a, b, flow, speed, gap, phase, length, k in lanes.get(fixed, ()):
                    vis_a, vis_b = max(a, lo), min(b, hi)
                    if vis_a >= vis_b:
                        continue
                    forward = flow in (RIGHT, DOWN)
                    # s: distance of a streak's head from the lane's upstream end
                    s_lo, s_hi = (vis_a - a, vis_b - a + length) if forward else (b - vis_b, b - vis_a + length)
                    shift = (phase + tick * speed) % gap
                    n = max(0, math.ceil((s_lo - shift) / gap))
                    s = shift + n * gap
                    bubble = flow == UP and k != 1
                    while s <= s_hi:
                        dist = min(s - length, b - a - s)
                        if dist > 0:
                            level = min(FADE_LEVELS, 1 + dist * FADE_LEVELS // FADE_PX)
                            pos = a + s - length if forward else b - s
                            mid = (pos + length // 2) // ts
                            if k != 1:  # a border lane: dim where the neighbour is not this current
                                side = -1 if k == 0 else 1
                                n_tile = (mid, fixed + side) if horizontal else (fixed + side, mid)
                                if water.get(n_tile) != flow:
                                    level //= 2
                            if level:
                                if horizontal:
                                    draw.append((streaks[(flow, length, level)], (pos - ox, across - oy)))
                                elif bubble:
                                    wobble = round(1.2 * math.sin((s + phase) * 0.18))
                                    size = (length + k) % 4
                                    draw.append((bubbles[(size, level)], (across + wobble - 3 - ox, pos - 3 - oy)))
                                else:
                                    draw.append((streaks[(flow, length, level)], (across - ox, pos - oy)))
                        s += gap
        if draw:
            surf.fblits(draw)


__all__ = ["WaterRenderer", "depth_shade", "find_pockets", "water_from_rows", "water_leaks", "water_to_rows"]
