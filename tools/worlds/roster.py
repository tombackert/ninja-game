"""Which enemy kind stands where: the cast of a level's enemies.

A level's difficulty comes from its enemy kinds (scripts/enemy_kinds.py), not
from the level number: a gunner fires the same in level 40 as in level 1. As
in Super Mario Bros., the campaign brings in the kinds one by one and later
levels mix in the harder ones more often. That is this file:

- `INTRO`: the first level each kind appears in.
- `MIX`: the share of each kind on open ground, by chapter.
- A thrower needs `THROWER_RUN` tiles to pace on.
- The spot decides too: on a ledge too short to walk (`SHORT` tiles or
  less) a stand-still turret, as a walker would only turn on the spot; a
  jumper needs room to hop (`JUMPER_RUN` tiles and `JUMPER_HEADROOM` of air
  above), a chaser room to run (`CHASER_RUN`).

The pick per spawner is a hash of the level and the spot, so it is the same
on every build. A level script names a kind where the design needs one
(`Level.enemy(x, y, "turret")`); the cast here fills in the rest.

Levels 0-10 are hand-drawn maps: their spawners were cast once with

    python -m tools.worlds.roster 0-10 --apply

which rewrites the enemy spawners' variants in data/maps/<id>.json. Without
`--apply` it prints each level's cast.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import zlib

from scripts.enemy_kinds import ENEMY_VARIANTS, KINDS
from scripts.tilemap import PHYSICS_TILES

INTRO = {"patrol": 0, "gunner": 1, "turret": 3, "jumper": 6, "chaser": 9, "thrower": 13}

# (first level of the band, {kind: share}); kinds not yet introduced drop out
MIX = [
    (0, {"patrol": 0.55, "gunner": 0.45}),
    (5, {"patrol": 0.35, "gunner": 0.40, "turret": 0.10, "jumper": 0.15}),
    (11, {"patrol": 0.25, "gunner": 0.30, "turret": 0.13, "jumper": 0.12, "chaser": 0.12, "thrower": 0.08}),
    (21, {"patrol": 0.18, "gunner": 0.26, "turret": 0.16, "jumper": 0.12, "chaser": 0.16, "thrower": 0.12}),
]

SHORT = 2  # tiles of walkable ground: a turret's spot
JUMPER_RUN = 4
JUMPER_HEADROOM = 3
CHASER_RUN = 5
THROWER_RUN = 3
RUN_LIMIT = 12  # tiles counted to either side


def mix_for(level: int) -> dict:
    mix = MIX[0][1]
    for first, shares in MIX:
        if level >= first:
            mix = shares
    return {k: v for k, v in mix.items() if INTRO[k] <= level}


def _unit(level: int, x: int, y: int) -> float:
    """A stable number in [0, 1) for this spot."""
    return zlib.crc32(f"{level}:{x}:{y}".encode()) / 2**32


def ground_run(is_solid, x: int, y: int) -> int:
    """Tiles of walkable ground through (x, y): air on row y with solid under it."""
    n = 1
    for step in (-1, 1):
        tx = x + step
        while abs(tx - x) <= RUN_LIMIT and not is_solid(tx, y) and is_solid(tx, y + 1):
            n += 1
            tx += step
    return n


def headroom(is_solid, x: int, y: int, limit: int = 6) -> int:
    n = 0
    while n < limit and not is_solid(x, y - 1 - n):
        n += 1
    return n


def fits(kind: str, run: int, room: int) -> bool:
    if kind == "jumper":
        return run >= JUMPER_RUN and room >= JUMPER_HEADROOM
    if kind == "chaser":
        return run >= CHASER_RUN
    if kind == "thrower":
        return run >= THROWER_RUN
    return True


def cast(level: int, is_solid, x: int, y: int) -> str:
    """The kind of the enemy standing on air tile (x, y) of `level`."""
    run = ground_run(is_solid, x, y)
    if run <= SHORT:
        return _first_in(level, "turret", "gunner", "patrol")
    mix = mix_for(level)
    u = _unit(level, x, y) * sum(mix.values())
    for kind, share in mix.items():
        u -= share
        if u < 0:
            break
    if not fits(kind, run, headroom(is_solid, x, y)):
        kind = _first_in(level, "gunner", "patrol")
    return kind


def _first_in(level: int, *kinds: str) -> str:
    """The first of `kinds` the campaign has brought in by `level`."""
    return next((k for k in kinds if INTRO[k] <= level), kinds[-1])


# --- the hand-drawn maps --------------------------------------------------------------


def map_path(level: int) -> str:
    return os.path.join("data", "maps", f"{level}.json")


def cast_map(level: int, data: dict) -> collections.Counter:
    """Cast every enemy spawner of map `data` in place. Returns the count by kind."""
    tilemap = data["map_data"]["tilemap"]

    def is_solid(x, y):
        t = tilemap.get(f"{x};{y}")
        return t is not None and t["type"] in PHYSICS_TILES

    counts: collections.Counter = collections.Counter()
    for tile in tilemap.values():
        if tile["type"] == "spawners" and tile["variant"] in ENEMY_VARIANTS:
            x, y = tile["pos"]
            kind = cast(level, is_solid, int(x), int(y))
            tile["variant"] = KINDS[kind].variant
            counts[kind] += 1
    return counts


def _ids(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("levels", help="ids, e.g. 0-10 or 3,5")
    ap.add_argument("--apply", action="store_true", help="write the cast into data/maps/<id>.json")
    args = ap.parse_args(argv)
    for level in _ids(args.levels):
        path = map_path(level)
        with open(path) as f:
            text = f.read()
        data = json.loads(text)
        counts = cast_map(level, data)
        line = ", ".join(f"{k} {counts[k]}" for k in KINDS if counts[k])
        print(f"level {level}: {sum(counts.values())} enemies: {line}")
        if args.apply:
            with open(path, "w") as f:
                if text.startswith("{\n"):  # the hand-drawn maps are indented
                    json.dump(data, f, indent=4)
                else:
                    json.dump(data, f, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
