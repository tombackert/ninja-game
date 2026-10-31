"""What the route planner explores to get across one route segment.

The search asks its goal for the distance of every state it keeps, so a
waypoint that notes down those states shows the search from the outside,
with no change to the planner. Draws them as a heat map over the level,
with the path the plan ends up taking.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

import pygame  # noqa: E402

from tools.report.routes import render_level  # noqa: E402
from tools.worlds import physics as ph  # noqa: E402
from tools.worlds.build import build_level  # noqa: E402
from tools.worlds.planner import Waypoint  # noqa: E402
from tools.worlds.route import plan_route  # noqa: E402

CELL = 2  # px of a heat cell
SCALE = 4
PAD = 40  # px around what the search reached
HEAT = (255, 110, 40)


@dataclass
class TracingWaypoint(Waypoint):
    trace: List[tuple] = field(default_factory=list)

    def distance(self, s: tuple) -> float:
        self.trace.append((s[ph.X] + ph.PW / 2, s[ph.Y] + ph.PH / 2))
        return super().distance(s)


def collect(out_dir: str, level: int, label: str, occurrence: int = 0) -> Dict[str, Any]:
    from game import Game

    lv = build_level(level)
    solids = lv.solids()
    spawn_px = (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
    kill_y = (max(y for _, y in solids) + 4) * 16

    matches = [i for i, wp in enumerate(lv.route) if wp.label == label]
    index = matches[occurrence]
    wp = lv.route[index]
    goal = TracingWaypoint(wp.x0, wp.y0, wp.x1, wp.y1, wp.ground, wp.label)
    res = plan_route(solids, spawn_px, [*lv.route[:index], goal], kill_y, verbose=False)
    if not res.ok:
        raise RuntimeError(f"segment {label} of level {level} failed")

    _label, start, n_frames, expanded = res.segments[-1]
    s = ph.spawn_state(*spawn_px)
    path = []
    for i, (m, j, d) in enumerate(res.frames):
        s = ph.apply_frame(s, m, j, d, solids)[0]
        if i >= start - 1:
            path.append((s[ph.X] + ph.PW / 2, s[ph.Y] + ph.PH / 2))

    game = Game(fullscreen=False)
    surface, offset = render_level(game, level)
    xs = [p[0] for p in goal.trace]
    ys = [p[1] for p in goal.trace]
    box = pygame.Rect(
        int(min(xs)) - PAD - offset[0],
        int(min(ys)) - PAD - offset[1],
        int(max(xs) - min(xs)) + 2 * PAD,
        int(max(ys) - min(ys)) + 2 * PAD,
    ).clip(surface.get_rect())
    crop = pygame.transform.grayscale(surface.subsurface(box)).convert()
    crop.fill((70, 70, 70), special_flags=pygame.BLEND_RGB_MULT)
    image = pygame.transform.scale(crop, (box.w * SCALE, box.h * SCALE))

    counts: Dict[tuple, int] = {}
    for x, y in goal.trace:
        key = (int(x - offset[0] - box.x) // CELL, int(y - offset[1] - box.y) // CELL)
        counts[key] = counts.get(key, 0) + 1
    peak = math.log1p(max(counts.values()))
    heat = pygame.Surface(image.get_size(), pygame.SRCALPHA)
    for (cx, cy), count in counts.items():
        strength = math.log1p(count) / peak
        cell = (cx * CELL * SCALE, cy * CELL * SCALE, CELL * SCALE, CELL * SCALE)
        heat.fill((*HEAT, int(60 + 195 * strength)), cell)
    image.blit(heat, (0, 0))

    points = [((x - offset[0] - box.x) * SCALE, (y - offset[1] - box.y) * SCALE) for x, y in path]
    pygame.draw.lines(image, (255, 255, 255), False, points, 3)

    out = os.path.join(out_dir, "search.png")
    pygame.image.save(image, out)
    summary = {
        "level": level,
        "label": label,
        "expanded": expanded,
        "states": len(goal.trace),
        "frames": n_frames,
        "size": list(image.get_size()),
    }
    with open(os.path.join(out_dir, "search-summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    return summary
