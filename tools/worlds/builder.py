"""Small level-building toolkit for the hand-designed worlds (levels 11-25).

A `Level` is a tile grid plus spawners, enemies, coins, decor, water and
the intended route (waypoints for tools/worlds/route.py). The element
helpers stamp the parametric building blocks the worlds are made of:
wall-jump chimneys, zigzag shafts, box stairs, pillar runs, dash gaps,
low-ceiling corridors and labyrinths. `save()` autotiles and writes the map
JSON in the format `Tilemap.load` reads, the route included (map_data.route,
tools/worlds/mapfile.py).
"""

from __future__ import annotations

import json
import math
import os
import random
from collections import deque

from scripts.enemy_kinds import get_kind
from scripts.hazards import CRUMBLE, DOWN, FLAME_ON, FLAME_PERIOD, FLAMEJET, LEFT, RIGHT, SPIKES, UP
from scripts.water import water_leaks, water_to_rows
from tools.worlds import roster
from tools.worlds.mapfile import route_to_json
from tools.worlds.physics import Terrain, lethal_from_tiles
from tools.worlds.planner import Waypoint

AUTOTILE_MAP = {
    tuple(sorted([(1, 0), (0, 1)])): 0,
    tuple(sorted([(1, 0), (0, 1), (-1, 0)])): 1,
    tuple(sorted([(-1, 0), (0, 1)])): 2,
    tuple(sorted([(-1, 0), (0, -1), (0, 1)])): 3,
    tuple(sorted([(-1, 0), (0, -1)])): 4,
    tuple(sorted([(-1, 0), (0, -1), (1, 0)])): 5,
    tuple(sorted([(1, 0), (0, -1)])): 6,
    tuple(sorted([(1, 0), (0, -1), (0, 1)])): 7,
    tuple(sorted([(1, 0), (-1, 0), (0, 1), (0, -1)])): 8,
}

# Pixel sizes of tiles/large_decor/<variant>.png (offgrid decor sits on the ground)
LARGE_DECOR_SIZE = {
    0: (31, 9),
    1: (25, 12),
    2: (33, 44),
    3: (19, 22),
    4: (21, 7),
    5: (26, 10),
    6: (13, 42),
    7: (26, 18),
    8: (17, 22),
    9: (19, 13),
}

FACINGS = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}
CAST = -1  # spawner variant of an enemy whose kind the level's cast picks on save

# Water flows (scripts/water.py)
STILL, RIGHT, LEFT, UP, DOWN = range(5)


def autotile_variant(nb: set) -> int:
    """Autotile variant for a tile with same-type neighbors `nb` (offsets).

    Uses the game's AUTOTILE_MAP and picks the closest look for shapes it
    leaves out (1-tile thin platforms and pillars).
    """
    key = tuple(sorted(nb))
    if key in AUTOTILE_MAP:
        return AUTOTILE_MAP[key]
    left, right, up, down = (-1, 0) in nb, (1, 0) in nb, (0, -1) in nb, (0, 1) in nb
    if not up:
        if left and not right:
            return 2
        if right and not left:
            return 0
        return 1
    if not down:
        if left and not right:
            return 4
        if right and not left:
            return 6
        return 5
    if not left:
        return 7
    return 3


class Level:
    def __init__(self, map_id: int, tile: str, background: str | None = None, clouds: bool = True):
        self.map_id = map_id
        self.tile = tile  # default solid tile type
        self.background = background
        self.clouds = clouds
        self.solid: dict[tuple[int, int], str] = {}
        self.objects: dict[tuple[int, int], tuple[str, int]] = {}  # coins, spawners, flag, decor
        self.offgrid: list[dict] = []
        self.water_tiles: dict[tuple[int, int], int] = {}  # (x, y) -> flow
        self.route: list[Waypoint] = []
        self.spawn_tile: tuple[int, int] | None = None
        self.obstacles: list[dict] = []  # declared for the shortcut checker (tools/worlds/shortcuts.py)
        self.fixed: dict[tuple[int, int], dict] = {}  # solid tiles with their own variant (hazards), + fields

    # --- terrain ---------------------------------------------------------
    def rect(self, x0, y0, x1, y1, t: str | None = None):
        """Fill tiles x0..x1, y0..y1 (inclusive) with solid `t`."""
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self.solid[(x, y)] = t or self.tile

    def carve(self, x0, y0, x1, y1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self.solid.pop((x, y), None)

    def is_solid(self, x, y) -> bool:
        return (x, y) in self.solid

    # --- water -----------------------------------------------------------
    def water(self, x0, y0, x1, y1, flow: int = STILL):
        """Flood tiles x0..x1, y0..y1 (inclusive). Rock inside it is flooded too:
        it never holds a swimmer, but it is drawn as under water."""
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self.water_tiles[(x, y)] = flow

    def drain(self, x0, y0, x1, y1):
        """Take the water out of tiles x0..x1, y0..y1: an air pocket. Air stays
        only under rock with rock beside it, water under it (see `to_json`)."""
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self.water_tiles.pop((x, y), None)

    # --- objects ---------------------------------------------------------
    def _obj(self, x, y, kind, variant=0):
        if (x, y) in self.solid:
            raise ValueError(f"level {self.map_id}: {kind} at {(x, y)} inside solid tile")
        self.objects[(x, y)] = (kind, variant)

    def spawn(self, x, y):
        """Player start; (x, y) is the air tile directly above the ground."""
        self._obj(x, y, "spawners", 0)
        self.spawn_tile = (x, y)

    def enemy(self, x, y, kind: str | None = None):
        """An enemy standing on air tile (x, y). `kind` (scripts/enemy_kinds.py):
        gunner, patrol, turret, chaser or jumper; None lets the level's cast
        pick one for the spot (tools/worlds/roster.py)."""
        self._obj(x, y, "spawners", CAST if kind is None else get_kind(kind).variant)

    # --- hazards (scripts/hazards.py) -------------------------------------
    def spikes(self, x0, y, x1=None, facing: str = "up"):
        """Spikes on tiles x0..x1 of row y (air tiles), points to `facing`:
        "up" on the ground below, "down" under the ceiling above, "left" /
        "right" on the wall to the right / left of the tile."""
        for x in range(min(x0, x1 if x1 is not None else x0), max(x0, x1 if x1 is not None else x0) + 1):
            self._obj(x, y, SPIKES, FACINGS[facing])

    def crumble(self, x0, y, x1=None):
        """Crumbling blocks on tiles x0..x1 of row y: solid until a player has
        stood on one for CRUMBLE_DELAY frames."""
        for x in range(min(x0, x1 if x1 is not None else x0), max(x0, x1 if x1 is not None else x0) + 1):
            self.solid[(x, y)] = CRUMBLE
            self.fixed[(x, y)] = {"variant": 0}

    def flamejet(self, x, y, facing: str = "up", period: int = FLAME_PERIOD, on: int = FLAME_ON, phase: int = 0):
        """A flame jet nozzle (a solid block) at (x, y) firing `facing` for
        `on` of every `period` frames, `phase` frames ahead of the beat."""
        if not 0 < on < period:
            raise ValueError(f"level {self.map_id}: flame jet at {(x, y)}: on {on} must lie in 1..period-1")
        self.solid[(x, y)] = FLAMEJET
        self.fixed[(x, y)] = {"variant": FACINGS[facing], "period": period, "on": on, "phase": phase}

    def coin(self, x, y):
        self._obj(x, y, "coin", 0)

    def coins(self, x0, y, x1, step=1):
        """A row of coins; tiles that are already solid are left out."""
        for x in range(x0, x1 + 1, step):
            if (x, y) not in self.solid:
                self.coin(x, y)

    def heart(self, x, y):
        """A heart pickup (one life back) on air tile (x, y); tools/worlds/hearts.py
        places them along the route by the danger on it."""
        self._obj(x, y, "heart", 0)

    def flag(self, x, y):
        self._obj(x, y, "flag", 0)

    def checkpoint(self, x, y):
        """Checkpoint banner (scripts/checkpoints.py) standing on the ground under
        air tile (x, y): a player who touches it respawns at (x, y). Offgrid, as
        its banner is two tiles tall. One per level, halfway, where every route
        passes (a world's finale may take a second); the player has P on top."""
        for t in ((x, y), (x, y - 1)):
            if t in self.solid:
                raise ValueError(f"level {self.map_id}: checkpoint at {(x, y)} overlaps solid tile {t}")
        self.offgrid.append({"type": "checkpoint", "variant": 0, "pos": [x * 16, (y - 1) * 16]})

    def decor(self, x, y, variant):
        self._obj(x, y, "decor", variant)

    def big_decor(self, x, y, variant):
        """Offgrid decor standing on the ground tile row below air tile (x, y)."""
        w, h = LARGE_DECOR_SIZE[variant]
        self.offgrid.append(
            {"type": "large_decor", "variant": variant, "pos": [x * 16 + (16 - w) / 2, (y + 1) * 16 - h]}
        )

    def wp(self, x0, y0, x1=None, y1=None, ground=False, label="", guide=False):
        """Next route waypoint: the hitbox center must enter tiles x0..x1, y0..y1.
        `guide`: there only so the planner gets through, not a stop of the design."""
        self.route.append(Waypoint(x0, y0, x0 if x1 is None else x1, y0 if y1 is None else y1, ground, label, guide))

    def obstacle(
        self, label: str, x0: int, y0: int, x1: int, y1: int, before: str, after: str, margin: int = 6, area=None
    ):
        """Declare an obstacle for the shortcut checker: the way from waypoint
        `before` to waypoint `after` (labels) is meant to lead through tiles
        x0..x1, y0..y1 and nowhere else. The checker blocks the designed route's
        trail there and searches for another way within `area` (x0, y0, x1, y1;
        by default the box widened by `margin` tiles): found (proven), none
        (refuted), or the budget ran out (not proven)."""
        self.obstacles.append(
            {"label": label, "box": (x0, y0, x1, y1), "before": before, "after": after, "margin": margin, "area": area}
        )

    def _check_hazards(self):
        """Spikes need a solid tile behind their base, a flame jet air in front
        of its nozzle, and no enemy may spawn in a jet's flame (it would burn on
        the first beat): a later carve or rect can break what was placed."""
        # (UP, DOWN, ... are the water flows here, FACINGS holds the hazard facings)
        offsets = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        steps = {FACINGS[k]: v for k, v in offsets.items()}
        bad = []
        for (x, y), (kind, variant) in self.objects.items():
            if kind == SPIKES:
                dx, dy = steps[variant]
                if not self.is_solid(x - dx, y - dy):
                    bad.append(f"spikes at {(x, y)} hang in the air")
        for (x, y), fields in self.fixed.items():
            if self.solid.get((x, y)) != FLAMEJET:
                continue
            dx, dy = steps[fields["variant"]]
            if self.is_solid(x + dx, y + dy):
                bad.append(f"flame jet at {(x, y)} fires into rock")
            for i in range(1, 4):
                c = (x + dx * i, y + dy * i)
                if self.is_solid(*c):
                    break
                if self.objects.get(c, ("",))[0] == "spawners" and self.objects[c][1] != 0:
                    bad.append(f"enemy at {c} spawns in the flame of the jet at {(x, y)}")
        if bad:
            raise ValueError(f"level {self.map_id}: " + "; ".join(bad))

    # --- export ----------------------------------------------------------
    def to_json(self) -> dict:
        clash = sorted(set(self.objects) & set(self.solid))
        if clash:  # an object placed first, a solid stamped over it later
            raise ValueError(f"level {self.map_id}: objects inside solid tiles at {clash}")
        self._check_hazards()
        leaks = water_leaks(self.water_tiles, self.is_solid)
        if leaks:  # water with no rock to hold it, beside or under it
            raise ValueError(f"level {self.map_id}: water would run out into {leaks[:12]}")
        tilemap = {}
        for (x, y), t in self.solid.items():
            fixed = self.fixed.get((x, y))
            if fixed is not None and t in (CRUMBLE, FLAMEJET):
                tilemap[f"{x};{y}"] = {"type": t, "pos": [x, y], **fixed}
                continue
            nb = {o for o in ((1, 0), (-1, 0), (0, -1), (0, 1)) if self.solid.get((x + o[0], y + o[1])) == t}
            tilemap[f"{x};{y}"] = {"type": t, "variant": autotile_variant(nb), "pos": [x, y]}
        for (x, y), (kind, variant) in self.objects.items():
            if kind == "spawners" and variant == CAST:
                variant = get_kind(roster.cast(self.map_id, self.is_solid, x, y)).variant
            tilemap[f"{x};{y}"] = {"type": kind, "variant": variant, "pos": [x, y]}
        meta = {
            "map": self.map_id,
            "timer": {"current_time": "00:00:00", "start_time": "00:00:00"},
            "version": 2,
            "music": "data/music/music_0.wav",
        }
        if self.background:
            meta["background"] = self.background
        if not self.clouds:
            meta["clouds"] = False
        map_data = {"tilemap": tilemap, "tile_size": 16, "offgrid": self.offgrid}
        if self.water_tiles:
            map_data["water"] = water_to_rows(self.water_tiles)
        if self.route:  # the intended route, for the planner (tools/worlds/mapfile.py)
            map_data["route"] = route_to_json(self.route)
        return {
            "meta_data": meta,
            "entities_data": {"players": [], "enemies": []},
            "map_data": map_data,
        }

    def save(self, maps_dir: str = "data/maps") -> str:
        path = os.path.join(maps_dir, f"{self.map_id}.json")
        data = self.to_json()  # checks first: a failed check leaves the old map in place
        with open(path, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        return path

    def solids(self) -> Terrain:
        spikes = [{"type": k, "variant": v, "pos": [x, y]} for (x, y), (k, v) in self.objects.items() if k == SPIKES]
        return Terrain(self.solid, dict(self.water_tiles), lethal_from_tiles(spikes))

    def stats(self) -> dict:
        xs = [x for x, _ in self.solid]
        ys = [y for _, y in self.solid]
        kinds = [k for k, _v in self.objects.values()]
        enemies = sum(1 for k, v in self.objects.values() if k == "spawners" and v != 0)
        return {
            "size": (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1),
            "tiles": len(self.solid),
            "enemies": enemies,
            "coins": kinds.count("coin"),
            "waypoints": len(self.route),
        }


# --- elements ------------------------------------------------------------------
# All take tile coordinates. "floor y" = the solid row the player stands on.


def chimney(lv: Level, x_left: int, inner: int, y_bottom: int, height: int, t=None, ledges=()):
    """Two walls with `inner` tiles of air between them, rising `height` tiles
    above floor row `y_bottom` (walls x_left and x_left+inner+1). `ledges` are
    (side, y) rest notches: 1-tile ledges sticking into the shaft."""
    xr = x_left + inner + 1
    lv.rect(x_left, y_bottom - height, x_left, y_bottom, t)
    lv.rect(xr, y_bottom - height, xr, y_bottom, t)
    for side, y in ledges:
        lv.rect(x_left + 1 if side < 0 else xr - 1, y, x_left + 1 if side < 0 else xr - 1, y, t)


def pillar(lv: Level, x: int, y_top: int, y_bottom: int, w: int = 1, t=None):
    lv.rect(x, y_top, x + w - 1, y_bottom, t)


def box(lv: Level, x: int, y: int, w: int = 2, h: int = 2, t=None):
    """Solid box with its top-left tile at (x, y)."""
    lv.rect(x, y, x + w - 1, y + h - 1, t)


def maze_cells(cols: int, rows: int, seed: int, start=(0, 0)):
    """Perfect maze (recursive backtracker). Returns the set of open edges
    between cells as frozensets {(c, r), (c2, r2)}."""
    rng = random.Random(seed)
    seen = {start}
    stack = [start]
    edges = set()
    while stack:
        c, r = stack[-1]
        nbrs = [(c + dc, r + dr) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        nbrs = [n for n in nbrs if 0 <= n[0] < cols and 0 <= n[1] < rows and n not in seen]
        if not nbrs:
            stack.pop()
            continue
        n = rng.choice(nbrs)
        edges.add(frozenset(((c, r), n)))
        seen.add(n)
        stack.append(n)
    return edges


def maze_path(edges, a, b):
    """Cell path a -> b through the maze (BFS)."""
    adj: dict = {}
    for e in edges:
        p, q = tuple(e)
        adj.setdefault(p, []).append(q)
        adj.setdefault(q, []).append(p)
    prev = {a: None}
    dq = deque([a])
    while dq:
        cur = dq.popleft()
        if cur == b:
            break
        for n in adj.get(cur, []):
            if n not in prev:
                prev[n] = cur
                dq.append(n)
    path = []
    cur = b
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return path[::-1]


class Maze:
    """Labyrinth carved into solid rock.

    Cells sit on a grid with pitch (dx, dy). Each cell is a `cw` x `ch` room
    (air); horizontal edges are corridors `ch` tall, vertical edges are shafts
    `cw` wide (wall-jump chimneys going up, drops going down). Rock fills
    everything else inside the maze's bounding box plus a `border`.
    """

    def __init__(
        self,
        lv: Level,
        x0: int,
        y0: int,
        cols: int,
        rows: int,
        seed: int,
        dx: int = 8,
        dy: int = 6,
        cw: int = 3,
        ch: int = 3,
        border: int = 2,
        t=None,
        extra_edges: int = 0,
        start=(0, 0),
    ):
        self.lv, self.x0, self.y0 = lv, x0, y0
        self.cols, self.rows, self.dx, self.dy, self.cw, self.ch = cols, rows, dx, dy, cw, ch
        self.edges = maze_cells(cols, rows, seed, start)
        rng = random.Random(seed + 1)
        # A few loops make it a labyrinth with choices instead of a single tree
        tries = 0
        while extra_edges > 0 and tries < 500:
            tries += 1
            c, r = rng.randrange(cols), rng.randrange(rows)
            dc, dr = rng.choice(((1, 0), (0, 1)))
            n = (c + dc, r + dr)
            if n[0] < cols and n[1] < rows:
                e = frozenset(((c, r), n))
                if e not in self.edges:
                    self.edges.add(e)
                    extra_edges -= 1
        w = (cols - 1) * dx + cw
        h = (rows - 1) * dy + ch
        self.bounds = (x0 - border, y0 - border, x0 + w - 1 + border, y0 + h - 1 + border)
        lv.rect(*self.bounds, t)
        for c in range(cols):
            for r in range(rows):
                cx, cy = self.cell_xy(c, r)
                lv.carve(cx, cy, cx + cw - 1, cy + ch - 1)
        for e in self.edges:
            (c1, r1), (c2, r2) = sorted(e)
            ax, ay = self.cell_xy(c1, r1)
            bx, by = self.cell_xy(c2, r2)
            if r1 == r2:  # corridor
                lv.carve(ax + cw, ay, bx - 1, ay + ch - 1)
            else:  # shaft
                lv.carve(ax, ay + ch, ax + cw - 1, by - 1)

    def cell_xy(self, c: int, r: int):
        return self.x0 + c * self.dx, self.y0 + r * self.dy

    def floor_y(self, c: int, r: int) -> int:
        """Row of the floor tiles under cell (c, r)."""
        return self.y0 + r * self.dy + self.ch

    def open_to(self, c, r, side: str):
        """Open the maze wall next to cell (c, r) on `side` ('left'/'right'/'up'/'down')."""
        cx, cy = self.cell_xy(c, r)
        x0, y0, x1, y1 = self.bounds
        if side == "left":
            self.lv.carve(x0, cy, cx - 1, cy + self.ch - 1)
        elif side == "right":
            self.lv.carve(cx + self.cw, cy, x1, cy + self.ch - 1)
        elif side == "up":
            self.lv.carve(cx, y0, cx + self.cw - 1, cy - 1)
        elif side == "down":
            self.lv.carve(cx, cy + self.ch, cx + self.cw - 1, y1)

    def route(self, a, b, coins=True, skip=()):
        """Add waypoints through the maze from cell a to cell b, with a coin
        trail along the way. `skip`: cells that get no waypoint (the planner
        finds its own way through them: cells a player only passes, where
        letting go of the keys does not come to rest)."""
        for c, r in maze_path(self.edges, a, b):
            cx, cy = self.cell_xy(c, r)
            if (c, r) not in skip:
                self.lv.wp(cx, cy, cx + self.cw - 1, cy + self.ch - 1, label=f"maze {c},{r}")
            if coins and (cx + 1, cy) not in self.lv.objects:
                self.lv.coin(cx + 1, cy)

    def vent(self, c: int, r: int, period: int = FLAME_PERIOD, on: int = FLAME_ON, phase: int = 0) -> bool:
        """A flame jet in the ceiling over the middle of cell (c, r), burning
        down to its floor on a beat. Left out (False) where the ceiling is open
        (a shaft) or an enemy stands in the flame."""
        x, y = self.cell_xy(c, r)
        x += self.cw // 2
        if not (self.lv.is_solid(x, y - 1) and self.lv.is_solid(x, y - 2)):
            return False
        if any(self.lv.objects.get((x, yy), ("",))[0] == "spawners" for yy in range(y, y + self.ch)):
            return False
        self.lv.flamejet(x, y - 1, "down", period, on, phase)
        return True

    def vents(self, a, b, count: int = 3, period: int = FLAME_PERIOD, on: int = FLAME_ON, phases=None) -> list:
        """Up to `count` vents (see vent) spread over the cells of the way from
        cell a to cell b, its ends left out; `phases`: one per vent. Returns
        the cells that got one."""
        path = maze_path(self.edges, a, b)[1:-1]
        placed: list = []
        if not path:
            return placed
        step = max(1, len(path) // count)
        order = path[step // 2 :: step] + [p for i, p in enumerate(path) if (i - step // 2) % step]
        for c, r in order:
            if len(placed) == count:
                break
            if any(abs(c - pc) + abs(r - pr) < 2 for pc, pr in placed):
                continue
            phase = phases[len(placed)] if phases else 40 * len(placed)
            if self.vent(c, r, period, on, phase):
                placed.append((c, r))
        return placed

    def dead_ends(self):
        deg: dict = {}
        for e in self.edges:
            for p in e:
                deg[p] = deg.get(p, 0) + 1
        return [p for p, d in deg.items() if d == 1]


def zigzag(lv: Level, x_left: int, y_bottom: int, sections: int, height: int, inner: int, offset: int, label="zigzag"):
    """Wall-jump shaft of `sections` pieces `height` tall, each shifted by
    `offset` tiles (alternately right and left), carved into rock. Every
    shift leaves a ledge to stand on (and reset the air time); the route
    stops on each of them."""
    x, y = x_left, y_bottom
    for i in range(sections):
        lv.carve(x, y - height + 1, x + inner - 1, y)
        if i % 2 == 1:  # shifted right: ledge on its right side
            lv.wp(x + inner - offset, y, x + inner - 1, y, ground=True, label=f"{label} ledge {i}")
        elif i > 0:
            lv.wp(x, y, x + offset - 1, y, ground=True, label=f"{label} ledge {i}")
        y -= height
        x += offset if i % 2 == 0 else -offset
    return x - (offset if (sections - 1) % 2 == 0 else -offset), y + height


def perforate(lv: Level, x: int, y_top: int, y_bottom: int, solid: int = 2, gap: int = 1):
    """Punch through-holes into a 1-thick wall column: `solid` rows of wall,
    then `gap` rows open, from the bottom up. Wall slides break at every
    hole, so a climb against it needs well-timed wall jumps."""
    y = y_bottom - solid
    while y - gap + 1 > y_top:
        lv.carve(x, y - gap + 1, x, y)
        y -= solid + gap


def pillar_run(lv: Level, pillars, bottom: int, t=None, label="pillar"):
    """1-wide pillars over the void: (x, top) each, with a coin above and a
    route stop on every top."""
    for x, top in pillars:
        pillar(lv, x, top, bottom, t=t)
        lv.coin(x, top - 2)
        lv.wp(x, top - 1, ground=True, label=f"{label} {x}")


def crate_chain(lv: Level, crates, t=None, label="crate"):
    """Floating crates (x, top, width), one tile thick, a route stop on each."""
    for x, top, w in crates:
        box(lv, x, top, w, 1, t=t)
        lv.coin(x, top - 2)
        lv.wp(x, top - 1, x + w - 1, top - 1, ground=True, label=f"{label} {x}")


def holed_chimney(
    lv: Level, x_left: int, inner: int, y_top: int, floor: int, rests=(), t=None, label="chimney", top=True
):
    """Wall-jump chimney between two 1-thick walls full of holes, standing on
    floor row `floor`. The left wall leaves a 3-row gap at the bottom to crawl
    in. `rests` are (side, row) 1-tile ledges (side -1 = left wall). `top`: a
    waypoint over the walls' tops (leave it out where the next stop beyond the
    top is all the planner needs)."""
    xr = x_left + inner + 1
    lv.rect(x_left, y_top, x_left, floor - 4, t)
    lv.rect(xr, y_top, xr, floor - 1, t)
    perforate(lv, x_left, y_top + 1, floor - 6, solid=2, gap=1)
    perforate(lv, xr, y_top + 1, floor - 6, solid=2, gap=1)
    lv.wp(x_left + 1, floor - 3, xr - 1, floor - 1, ground=True, label=f"{label} base")
    for side, row in sorted(rests, key=lambda r: -r[1]):
        x = x_left + 1 if side < 0 else xr - 1
        lv.rect(x, row, x, row, t)
        lv.wp(x, row - 1, ground=True, label=f"{label} rest {row}")
        lv.coin(x_left + 1 + inner // 2, row - 3)
    if top:
        lv.wp(x_left, y_top - 1, xr, y_top - 1, label=f"{label} top")


def dunes(lv: Level, x0: int, x1: int, base: int, amp: float, period: float, bottom: int, phase=0.0, t=None):
    """Rolling surface from x0 to x1 around row `base`, solid down to `bottom`.
    Returns {x: surface row}."""
    tops = {}
    for x in range(x0, x1 + 1):
        top = base - round(amp * (math.sin((x + phase) / period) + 0.5 * math.sin((x + phase) / (period * 0.37))))
        lv.rect(x, top, x, bottom, t)
        tops[x] = top
    return tops
