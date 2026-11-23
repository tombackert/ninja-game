"""Check a planned route against the hazards the planner cannot see.

The physics replica (tools/worlds/physics.py) knows spikes, but it is
time-blind: a crumbling block never falls and a flame never burns there.
This replays a route's frames and checks both against the game's clock
(scripts/hazards.py: ticks since the level was loaded, the plan's frame
count from the spawn), in Game.step's order: the hazards tick, then the
player moves, then a touch kills.

- a **flame** problem: the route stands in a burning flame;
- a **crumble** problem: the route still stands on a crumbling block when
  it falls (CRUMBLE_DELAY frames after the route first stood on it, minus
  `margin` frames of slack), or before it is back.

`build` runs it after each plan (tools/worlds/build.py); a problem fails the
level, so the designer moves a jet's `phase` or shortens the stand.
"""

from __future__ import annotations

from scripts.hazards import (
    CRUMBLE,
    CRUMBLE_DELAY,
    CRUMBLE_RETURN,
    FLAMEJET,
    FlameJet,
    flame_box,
    flame_cells,
)
from tools.worlds import physics as ph


def _jets(tiles: dict) -> list:
    solid = {tuple(t["pos"]) for t in tiles.values() if t["type"] in ph.PHYSICS_TILES}
    jets = []
    for t in tiles.values():
        if t["type"] == FLAMEJET:
            tx, ty = t["pos"]
            jet = FlameJet(t, flame_cells(tx, ty, t.get("variant", 0), lambda x, y: (x, y) in solid), ph.TS)
            jets.append((jet, [flame_box(c, jet.facing, ph.TS) for c in jet.cells]))
    return jets


def check_route(tiles: dict, spawn_px: tuple, frames: list, solids, margin: int = 4) -> list[str]:
    """Problems of the route `frames` ((move, jump, dash) per frame) from
    `spawn_px` on the map tiles `tiles` ({"x;y": tile}), as text lines."""
    jets = _jets(tiles)
    crumble = {tuple(t["pos"]) for t in tiles.values() if t["type"] == CRUMBLE}
    if not jets and not crumble:
        return []
    problems: list[str] = []
    first_stand: dict = {}
    s = ph.spawn_state(*spawn_px)
    for k, (m, j, d) in enumerate(frames, 1):
        s, down, _dead = ph.apply_frame(s, m, j, d, solids)
        rx, ry = int(s[ph.X]), int(s[ph.Y])
        for jet, boxes in jets:
            if jet.burning(k) and any(
                rx < bx + bw and bx < rx + ph.PW and ry < by + bh and by < ry + ph.PH for bx, by, bw, bh in boxes
            ):
                problems.append(f"flame: frame {k} at ({rx}, {ry}) in the jet at {jet.pos}")
                break
        if down:
            feet = {(rx // ph.TS, (ry + ph.PH) // ph.TS), ((rx + ph.PW - 1) // ph.TS, (ry + ph.PH) // ph.TS)}
            for tile in feet & crumble:
                start = first_stand.setdefault(tile, k)
                age = k - start
                if CRUMBLE_DELAY - margin <= age < CRUMBLE_DELAY + CRUMBLE_RETURN:
                    problems.append(
                        f"crumble: frame {k} still on the block at {tile}, {age} frames after stepping on it"
                    )
                    first_stand[tile] = -(10**9)  # report each block once
        if len(problems) >= 10:
            break
    return problems
