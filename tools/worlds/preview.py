"""Render a whole map to a PNG, optionally with the route and planned path.

Usage:
    python -m tools.worlds.preview <map_id> <out.png> [--scale 0.5]
"""

from __future__ import annotations

import argparse
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

TILE_DIRS = {"coin": "collectables/coin", "flag": "collectables/flag"}


def render(map_path: str, out: str, scale: float = 0.5, route=None, path_px=None) -> tuple:
    pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    with open(map_path) as f:
        data = json.load(f)
    m = data["map_data"]
    ts = m["tile_size"]
    cache: dict = {}

    def img(t, v):
        if (t, v) not in cache:
            d = os.path.join("data/images/tiles", TILE_DIRS.get(t, t))
            p = os.path.join(d, f"{v}.png")
            if not os.path.exists(p):
                p = os.path.join(d, sorted(os.listdir(d))[0])
            s = pygame.image.load(p).convert()
            s.set_colorkey((0, 0, 0))
            cache[(t, v)] = s
        return cache[(t, v)]

    tiles = list(m["tilemap"].values())
    xs = [t["pos"][0] for t in tiles]
    ys = [t["pos"][1] for t in tiles]
    x0, x1, y0, y1 = min(xs) - 2, max(xs) + 3, min(ys) - 4, max(ys) + 3
    W, H = (x1 - x0) * ts, (y1 - y0) * ts
    surf = pygame.Surface((W, H))
    bg = pygame.image.load(os.path.join("data/images", data["meta_data"].get("background", "background-big.png")))
    surf.fill(bg.get_at((10, 200)))
    for t in m["offgrid"]:
        surf.blit(img(t["type"], t["variant"]), (t["pos"][0] - x0 * ts, t["pos"][1] - y0 * ts))
    for t in tiles:
        surf.blit(img(t["type"], t["variant"]), ((t["pos"][0] - x0) * ts, (t["pos"][1] - y0) * ts))
    font = pygame.font.Font(None, 16)
    for gx in range(x0 - x0 % 10, x1, 10):
        pygame.draw.line(surf, (255, 255, 255), ((gx - x0) * ts, 0), ((gx - x0) * ts, H), 1)
        surf.blit(font.render(str(gx), True, (255, 255, 0)), ((gx - x0) * ts + 2, 2))
    for gy in range(y0 - y0 % 10, y1, 10):
        pygame.draw.line(surf, (255, 255, 255), (0, (gy - y0) * ts), (W, (gy - y0) * ts), 1)
        surf.blit(font.render(str(gy), True, (255, 255, 0)), (2, (gy - y0) * ts + 2))
    for t in tiles:
        r = ((t["pos"][0] - x0) * ts - 2, (t["pos"][1] - y0) * ts - 2, 12, 19)
        if t["type"] == "spawners":
            pygame.draw.rect(surf, (0, 255, 0) if t["variant"] == 0 else (255, 0, 0), r, 2)
        elif t["type"] == "flag":
            pygame.draw.rect(surf, (255, 0, 255), ((t["pos"][0] - x0) * ts - 4, (t["pos"][1] - y0) * ts - 4, 24, 24), 3)
    for i, wp in enumerate(route or []):
        rect = ((wp.x0 - x0) * ts, (wp.y0 - y0) * ts, (wp.x1 - wp.x0 + 1) * ts, (wp.y1 - wp.y0 + 1) * ts)
        pygame.draw.rect(surf, (255, 255, 0), rect, 1)
        surf.blit(font.render(str(i), True, (255, 255, 0)), (rect[0] + 1, rect[1] + 1))
    if path_px and len(path_px) > 1:
        pts = [(x + 4 - x0 * ts, y + 7 - y0 * ts) for x, y in path_px]
        pygame.draw.lines(surf, (255, 40, 200), False, pts, 2)
    if scale != 1:
        surf = pygame.transform.smoothscale(surf, (int(W * scale), int(H * scale)))
    pygame.image.save(surf, out)
    return (x0, y0, x1, y1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("map_id")
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=0.5)
    args = ap.parse_args()
    render(f"data/maps/{args.map_id}.json", args.out, args.scale)


if __name__ == "__main__":
    main()
