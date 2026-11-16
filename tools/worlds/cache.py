"""Exact caches for the level checks (docs/level-building-process-brainstorm.md, 3.4).

A planner search or an element's rating only reads the tiles near the states
it simulates. `Probe` records the box of every state the physics steps from
while it is active; a result is stored with that box and a hash of the tiles
(and water) in it. A later lookup with the same inputs is a hit only if the
tiles in the stored box are still the same, so after a local change only the
searches whose box touches the change run again, and every hit gives exactly
what the search would give.

Two more things are read, and kept in the key:
- the kill line (`Terrain.kill_y`, from the level's lowest rock), part of every key;
- the planner's distance field (F1), a Dijkstra over the tiles round its goal
  (`planner.field_bounds`): its box is added to the probe's.

Entries live under out/check/cache/<kind>/, one pickle per input key.
"""

from __future__ import annotations

import hashlib
import math
import os
import pickle

from tools.worlds import physics as ph
from tools.worlds import planner

CACHE_DIR = os.path.join("out", "check", "cache")
MARGIN = 3  # tiles round the stepped-from positions a step can read (neighbours, the hitbox, one step's travel)

_HERE = os.path.dirname(os.path.abspath(__file__))


def code_version(*names: str) -> str:
    """A hash of the code a result depends on: the files' syntax trees, so
    comments and formatting do not throw results away."""
    import ast

    h = hashlib.sha1()
    for name in names:
        with open(os.path.join(_HERE, name), encoding="utf-8") as f:
            h.update(ast.dump(ast.parse(f.read())).encode())
    return h.hexdigest()[:12]


class Probe:
    """While active, records the box of every position the physics steps from
    and the tiles the planner's distance fields cover."""

    def __init__(self):
        self.x0 = self.y0 = math.inf
        self.x1 = self.y1 = -math.inf
        self.fields: list = []  # tile boxes (x0, y0, x1, y1) of the fields read

    def read(self, x0, y0, x1, y1) -> None:
        self.fields.append((x0, y0, x1, y1))

    def __enter__(self):
        self._orig = ph.step
        planner.PROBES.append(self)
        probe = self
        orig = self._orig

        def step(s, m, solids):
            x, y = s[0], s[1]
            if x < probe.x0:
                probe.x0 = x
            if x > probe.x1:
                probe.x1 = x
            if y < probe.y0:
                probe.y0 = y
            if y > probe.y1:
                probe.y1 = y
            return orig(s, m, solids)

        ph.step = step
        return self

    def __exit__(self, *exc):
        ph.step = self._orig
        planner.PROBES.remove(self)
        return False

    def box(self) -> tuple:
        """(tx0, ty0, tx1, ty1): every tile that may have been read."""
        boxes = list(self.fields)
        if self.x0 != math.inf:
            ts = ph.TS
            boxes.append(
                (
                    int(self.x0 // ts) - MARGIN,
                    int(self.y0 // ts) - MARGIN,
                    int(self.x1 // ts) + 1 + MARGIN,
                    int(self.y1 // ts) + 1 + MARGIN,
                )
            )
        if not boxes:
            return (0, 0, -1, -1)
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )


def tiles_hash(solids, box: tuple | None) -> str:
    """Hash of the solid tiles and water in `box` (None: the whole level)."""
    water = getattr(solids, "water", None) or {}
    if box is None:
        cache = getattr(solids, "__dict__", None)
        if cache is not None and "_whole_hash" in cache:
            return cache["_whole_hash"]
        h = hashlib.sha1(repr((sorted(solids), sorted(water.items()))).encode()).hexdigest()
        if cache is not None:
            cache["_whole_hash"] = h
        return h
    x0, y0, x1, y1 = box
    rock = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (x, y) in solids]
    wet = [((x, y), water[(x, y)]) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (x, y) in water]
    return hashlib.sha1(repr((rock, wet)).encode()).hexdigest()


def input_key(*parts) -> str:
    """Key of a search's inputs (states, goals, settings: anything repr-stable)."""

    def norm(v):
        if isinstance(v, float):
            return round(v, 9)
        if isinstance(v, (list, tuple)):
            return tuple(norm(x) for x in v)
        return v

    return hashlib.sha1(repr(norm(parts)).encode()).hexdigest()


class Store:
    """Results of one kind ("route", "element") keyed by their inputs, each with
    the tile box it read. Counts hits and misses."""

    def __init__(self, kind: str, version: str, root: str = CACHE_DIR):
        self.dir = os.path.join(root, kind)
        self.version = version
        self.hits = self.misses = 0

    def _path(self, key: str) -> str:
        return os.path.join(self.dir, key[:2], key + ".pkl")

    def get(self, key: str, solids):
        path = self._path(key)
        try:
            with open(path, "rb") as f:
                entries = pickle.load(f)
        except (OSError, pickle.UnpicklingError, EOFError):
            entries = []
        for version, box, h, kill_y, value in entries:
            if version == self.version and kill_y == getattr(solids, "kill_y", None) and tiles_hash(solids, box) == h:
                self.hits += 1
                return value
        self.misses += 1
        return None

    def put(self, key: str, solids, box: tuple | None, value) -> None:
        path = self._path(key)
        try:
            with open(path, "rb") as f:
                entries = pickle.load(f)
        except (OSError, pickle.UnpicklingError, EOFError):
            entries = []
        entries = [e for e in entries if e[0] == self.version][-7:]  # a few geometry variants per input
        entries.append((self.version, box, tiles_hash(solids, box), getattr(solids, "kill_y", None), value))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + f".{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            pickle.dump(entries, f)
        os.replace(tmp, path)

    def stats(self) -> str:
        return f"{self.hits} of {self.hits + self.misses} cached"


def route_store(root: str = CACHE_DIR) -> Store:
    return Store("route", code_version("physics.py", "planner.py", "route.py"), root)


def element_store(root: str = CACHE_DIR) -> Store:
    return Store("element", code_version("physics.py", "planner.py", "route.py", "windows.py"), root)
