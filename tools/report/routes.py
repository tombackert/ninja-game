"""Route explorer data: every built level as an image plus its planned route.

Renders each level with the game's own tiles, water and sprites, and writes
what the page needs to draw the route on top: the path of the player's
hitbox, the waypoints, the frame-exact inputs and how often each 24-frame
piece of the route fails when its keys are pressed a little off.
"""

from __future__ import annotations

import importlib
import json
import os
import random
from typing import Any, Dict, Tuple

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

import pygame  # noqa: E402

from tools.worlds import physics as ph  # noqa: E402
from tools.worlds.assess import piece_fail_rate  # noqa: E402
from tools.worlds.build import LEVELS  # noqa: E402
from tools.worlds.route import LEAD_IN, load_plan  # noqa: E402

TS = 16
MARGIN = 2  # tiles around the level
PATH_EVERY = 3  # frames per path point
CHUNK, SIGMA, SAMPLES = 24, 2.0, 30  # the defaults of tools.worlds.assess


def level_name(map_id: int) -> str:
    """'Undertow Caves' from the level's docstring: 'Level 24 - Undertow Caves (reef, deep water).'"""
    doc = importlib.import_module(f"tools.worlds.levels.level_{map_id}").__doc__ or ""
    first = doc.strip().splitlines()[0]
    return first.split(" - ", 1)[-1].split("(")[0].rstrip(" .")


def render_level(game: Any, map_id: int) -> Tuple[pygame.Surface, Tuple[int, int]]:
    """The whole level on one surface, and the world position of the surface's top left."""
    game.load_level(map_id)
    tilemap = game.tilemap
    cells = [tile["pos"] for tile in tilemap.tilemap.values()]
    x0 = (min(c[0] for c in cells) - MARGIN) * TS
    y0 = (min(c[1] for c in cells) - MARGIN) * TS
    x1 = (max(c[0] for c in cells) + MARGIN + 1) * TS
    y1 = (max(c[1] for c in cells) + MARGIN + 1) * TS
    offset = (x0, y0)
    size = (x1 - x0, y1 - y0)

    surface = pygame.Surface(size).convert()
    background = game.assets["background"]
    surface.blit(pygame.transform.smoothscale(background, size), (0, 0))
    tilemap.render_water_back(surface, offset, 0)
    tilemap.render(surface, offset)
    tilemap.render_water_rock(surface, offset)
    game.cm.render(surface, offset)
    for enemy in game.enemies:
        enemy.render(surface, offset)
    tilemap.render_water(surface, offset, 0)
    return surface, offset


def route_data(map_id: int, offset: Tuple[int, int], size: Tuple[int, int]) -> Dict[str, Any]:
    with open(f"data/maps/{map_id}.json") as f:
        solids = ph.terrain_from_map(json.load(f)["map_data"])
    kill_y = (max(y for _, y in solids) + 4) * TS
    plan = load_plan(map_id)
    frames = plan["frame_list"]

    states = [ph.spawn_state(*plan["spawn"])]
    for m, j, d in frames:
        states.append(ph.apply_frame(states[-1], m, j, d, solids)[0])

    def center(s: tuple) -> list:
        return [round(s[ph.X] + ph.PW / 2 - offset[0]), round(s[ph.Y] + ph.PH / 2 - offset[1])]

    rng = random.Random(map_id)
    pieces = []
    for a in range(LEAD_IN, len(frames) - 1, CHUNK):
        b = min(a + CHUNK, len(frames))
        pieces.append(round(piece_fail_rate(states, frames, a, b, solids, kill_y, rng, SIGMA, SAMPLES), 2))

    return {
        "level": map_id,
        "name": level_name(map_id),
        "size": list(size),
        "frames": len(frames),
        "lead_in": LEAD_IN,
        "path_every": PATH_EVERY,
        "path": [center(s) for s in states[::PATH_EVERY]],
        "inputs": plan["inputs"],
        "waypoints": [
            {
                "box": [
                    round(w.x0 * TS - offset[0]),
                    round(w.y0 * TS - offset[1]),
                    round((w.x1 + 1) * TS - offset[0]),
                    round((w.y1 + 1) * TS - offset[1]),
                ],
                "label": w.label,
            }
            for w in plan["waypoints"]
        ],
        "piece_frames": CHUNK,
        "pieces": pieces,
    }


def collect(out_dir: str) -> Dict[str, Any]:
    from game import Game

    route_dir = os.path.join(out_dir, "routes")
    os.makedirs(route_dir, exist_ok=True)
    game = Game(fullscreen=False)
    index = []
    for map_id in LEVELS:
        surface, offset = render_level(game, map_id)
        pygame.image.save(surface, os.path.join(route_dir, f"{map_id}.png"))
        data = route_data(map_id, offset, surface.get_size())
        with open(os.path.join(route_dir, f"{map_id}.json"), "w") as f:
            json.dump(data, f, separators=(",", ":"))
        index.append({k: data[k] for k in ("level", "name", "size", "frames")})
        print(f"level {map_id}: {data['name']}, {surface.get_size()}", flush=True)
    return {"levels": index}
