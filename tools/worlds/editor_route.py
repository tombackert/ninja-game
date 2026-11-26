"""The editor's route mode: the waypoints of map_data.route over the map.

R in the editor switches it on and off. While it is on, tiles stay as they
are and the mouse edits the route instead (tools/worlds/mapfile.py):

    left drag      a new waypoint over the tiles dragged (after the selected one, else at the end)
    left click     select the waypoint under the mouse
    right click    delete the waypoint under the mouse
    Q / E          select the previous / next waypoint
    , / .          move the selected waypoint one place earlier / later
    F / U          the selected waypoint: ground (stand in it) / guide (only for the planner) on or off
    Del            delete the selected waypoint
    N              draft route: spawn, checkpoints, flag (Shift+N replaces a route)
    L              route from the replay of the best run, data/replays/<id>.json (Shift+L replaces)
    P              save the map and plan its route in the background; the plan is saved when it is OK

The planned path is drawn over the map, the waypoint the planner could not
reach in red. Any change to the route takes the shown plan away.
"""

from __future__ import annotations

import json
import threading

import pygame

from tools.worlds.mapfile import MapLevel, route_from_json, route_to_json
from tools.worlds.planner import Waypoint

STOP = (40, 120, 255)
GROUND = (20, 160, 60)
GUIDE = (210, 140, 0)
SELECTED = (240, 0, 200)
FAILED = (230, 30, 30)
TRAIL = (255, 90, 0)
TEXT = (0, 0, 0)
TRAIL_EVERY = 3  # frames per point of the drawn path
HELP = "drag new | click select | RMB del | Q/E sel | ,/. order | F ground | U guide | N draft | L replay | P plan"


class RouteLayer:
    """Route editing on a Tilemap (its `route` rows), for map `map_id`. `save`
    writes the map file (the editor's save); planning calls it first, so the
    plan belongs to the map on disk."""

    def __init__(self, tilemap, map_id, save):
        self.tilemap = tilemap
        self.map_id = int(map_id) if str(map_id).lstrip("-").isdigit() else map_id  # plans name numbered maps by int
        self._save = save
        self.active = False
        self.selected: int | None = None
        self.drag_start: tuple | None = None
        self.status = ""
        self.trail: list | None = None
        self.failed_at: int | None = None
        self._thread: threading.Thread | None = None
        self._outcome = None  # (MapLevel, Planned) or an Exception, from the planning thread
        self._spawn: tuple | None = None  # the player spawner's tile, found once per switch-on

    def toggle_active(self) -> None:
        """Route mode on or off (the editor's R)."""
        self.active = not self.active
        self.drag_start = None
        self._spawn = None

    # --- the route -----------------------------------------------------------
    @property
    def route(self) -> list[Waypoint]:
        return route_from_json(self.tilemap.route)

    def _set(self, route: list[Waypoint], selected: int | None = None) -> None:
        self.tilemap.route = route_to_json(route)
        self.selected = selected if selected is not None and 0 <= selected < len(route) else None
        self.trail = None
        self.failed_at = None

    def hit(self, tile: tuple) -> int | None:
        """The waypoint whose box holds tile (x, y); the latest of several."""
        x, y = tile
        for i in range(len(self.tilemap.route) - 1, -1, -1):
            w = self.tilemap.route[i]
            if w["x0"] <= x <= w["x1"] and w["y0"] <= y <= w["y1"]:
                return i
        return None

    def _solid(self, x: int, y: int) -> bool:
        from scripts.tilemap import PHYSICS_TILES

        t = self.tilemap.tilemap.get(f"{x};{y}")
        return t is not None and t["type"] in PHYSICS_TILES

    def add(self, a: tuple, b: tuple) -> int:
        """A waypoint over tiles a..b, after the selected one (else at the end); a
        ground waypoint when rock lies under its bottom row. Returns its index."""
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        ground = any(self._solid(x, y1 + 1) and not self._solid(x, y1) for x in range(x0, x1 + 1))
        route = self.route
        at = len(route) if self.selected is None else self.selected + 1
        route.insert(at, Waypoint(x0, y0, x1, y1, ground, f"{x0};{y0}"))
        self._set(route, at)
        return at

    def delete(self, i: int) -> None:
        route = self.route
        del route[i]
        sel = self.selected
        if sel == i:
            sel = min(i, len(route) - 1)
        elif sel is not None and sel > i:
            sel -= 1
        self._set(route, sel)

    def toggle(self, field: str) -> None:
        if self.selected is None:
            return
        route = self.route
        w = route[self.selected]
        setattr(w, field, not getattr(w, field))
        self._set(route, self.selected)

    def move(self, delta: int) -> None:
        """Move the selected waypoint `delta` places in the order."""
        if self.selected is None:
            return
        route = self.route
        j = self.selected + delta
        if 0 <= j < len(route):
            route[self.selected], route[j] = route[j], route[self.selected]
            self._set(route, j)

    def select_step(self, delta: int) -> None:
        n = len(self.tilemap.route)
        if n == 0:
            return
        if self.selected is None:
            self.selected = 0 if delta > 0 else n - 1
        else:
            self.selected = (self.selected + delta) % n

    def map_level(self) -> MapLevel:
        """The map as it would be saved, as the planner reads it (a copy)."""
        return MapLevel(self.map_id, json.loads(json.dumps(self.tilemap.to_json())))

    def _replace(self, make, force: bool, what: str) -> None:
        if self.tilemap.route and not force:
            self.status = f"there is a route already: Shift+{what} replaces it"
            return
        try:
            route = make(self.map_level())
        except (OSError, ValueError) as e:
            self.status = f"no route: {e}"
            return
        self._set(route)
        self.status = f"{len(route)} waypoints"

    def draft(self, force: bool = False) -> None:
        from tools.worlds.draft import draft_route

        self._replace(draft_route, force, "N")

    def from_replay(self, force: bool = False) -> None:
        from tools.worlds.draft import load_replay, replay_route

        self._replace(lambda ml: replay_route(ml, load_replay(self.map_id)), force, "L")

    # --- planning ----------------------------------------------------------------
    @property
    def planning(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def plan(self, wait: bool = False) -> None:
        """Save the map, then plan its route in a thread (`wait`: until it is done)."""
        if self.planning:
            return
        ml = self.map_level()
        if not ml.route:
            self.status = "no route to plan (N drafts one)"
            return
        if ml.spawn_tile is None:
            self.status = "no player spawner in the map"
            return
        self._save()
        self.trail = None
        self.failed_at = None
        self.status = f"planning {len(ml.route)} waypoints ..."

        def job():
            from tools.worlds.build import plan_map

            try:
                self._outcome = (ml, plan_map(ml, verbose=False))
            except Exception as e:  # shown in the editor, not raised in its loop
                self._outcome = e

        self._outcome = None
        self._thread = threading.Thread(target=job, daemon=True)
        self._thread.start()
        if wait:
            self._thread.join()
        self.poll()

    def poll(self) -> None:
        """Take over a finished plan: show it, and save it when it is OK."""
        if self._outcome is None or self.planning:
            return
        outcome, self._outcome = self._outcome, None
        if isinstance(outcome, Exception):
            self.status = f"planner error: {outcome}"
            return
        ml, planned = outcome
        res = planned.res
        self.trail = planned.trail
        if not res.ok:
            self.failed_at = res.failed_at
            w = ml.route[res.failed_at]
            self.status = f"UNREACHED waypoint {res.failed_at} '{w.label}' ({len(res.frames)} frames up to it)"
            return
        from tools.worlds.route import save_plan

        path = save_plan(self.map_id, ml.spawn_px, res.frames, ml.route, res.segments)
        hazards = f", hazard: {planned.problems[0]}" if planned.problems else ""
        self.status = f"OK {len(res.frames)} frames ({len(res.frames) / 60:.1f} s), saved {path}{hazards}"

    # --- input and drawing ---------------------------------------------------------
    def handle_event(self, event, tile: tuple) -> bool:
        """Act on a pygame event in route mode; True if it was the route's."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                i = self.hit(tile)
                if i is None:
                    self.drag_start = tuple(tile)
                else:
                    self.selected = i
                return True
            if event.button == 3:
                i = self.hit(tile)
                if i is not None:
                    self.delete(i)
                return True
            return event.button in (4, 5)  # the wheel picks no tiles here
        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.drag_start is not None:
                self.add(self.drag_start, tuple(tile))
                self.drag_start = None
            return event.button in (1, 3, 4, 5)
        if event.type == pygame.KEYDOWN:
            shift = bool(event.mod & pygame.KMOD_SHIFT)
            actions = {
                pygame.K_q: lambda: self.select_step(-1),
                pygame.K_e: lambda: self.select_step(1),
                pygame.K_COMMA: lambda: self.move(-1),
                pygame.K_PERIOD: lambda: self.move(1),
                pygame.K_f: lambda: self.toggle("ground"),
                pygame.K_u: lambda: self.toggle("guide"),
                pygame.K_DELETE: lambda: self.selected is not None and self.delete(self.selected),
                pygame.K_BACKSPACE: lambda: self.selected is not None and self.delete(self.selected),
                pygame.K_n: lambda: self.draft(shift),
                pygame.K_l: lambda: self.from_replay(shift),
                pygame.K_p: lambda: self.plan(),
            }
            if event.key in actions:
                actions[event.key]()
                return True
        return False

    def render(self, surf, scroll: tuple, font, tile: tuple | None = None, ts: int = 16) -> None:
        self.poll()
        overlay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        sx, sy = scroll
        route = self.route

        def box(w) -> pygame.Rect:
            return pygame.Rect(w.x0 * ts - sx, w.y0 * ts - sy, (w.x1 - w.x0 + 1) * ts, (w.y1 - w.y0 + 1) * ts)

        if self.trail:
            pts = [(x + 4 - sx, y + 7 - sy) for x, y in self.trail[::TRAIL_EVERY]]
            if len(pts) > 1:
                pygame.draw.lines(overlay, TRAIL + (220,), False, pts, 1)
        if self._spawn is None:
            spawners = [
                t["pos"] for t in self.tilemap.tilemap.values() if t["type"] == "spawners" and t["variant"] == 0
            ]
            self._spawn = tuple(spawners[0]) if spawners else ()
        spawn = self._spawn or None
        prev = (spawn[0] * ts + 8 - sx, spawn[1] * ts + 8 - sy) if spawn else None
        for i, w in enumerate(route):
            r = box(w)
            color = FAILED if i == self.failed_at else GUIDE if w.guide else GROUND if w.ground else STOP
            if prev:
                pygame.draw.line(overlay, color + (120,), prev, r.center, 1)
            prev = r.center
            overlay.fill(color + (70,), r)
            pygame.draw.rect(
                overlay, (SELECTED if i == self.selected else color) + (255,), r, 2 if i == self.selected else 1
            )
            if w.ground:  # the floor the player stands on in it
                pygame.draw.line(overlay, color + (255,), (r.left, r.bottom - 1), (r.right - 1, r.bottom - 1), 2)
            overlay.blit(font.render(str(i), True, TEXT), (r.x + 2, r.y + 1))
        if self.drag_start is not None and tile is not None:
            a, b = self.drag_start, tile
            r = pygame.Rect(
                min(a[0], b[0]) * ts - sx,
                min(a[1], b[1]) * ts - sy,
                (abs(a[0] - b[0]) + 1) * ts,
                (abs(a[1] - b[1]) + 1) * ts,
            )
            pygame.draw.rect(overlay, SELECTED + (255,), r, 1)
        surf.blit(overlay, (0, 0))

        sel = ""
        if self.selected is not None and self.selected < len(route):
            w = route[self.selected]
            sel = f" | {self.selected}: '{w.label}'{' ground' if w.ground else ''}{' guide' if w.guide else ''}"
        lines = [f"ROUTE {len(route)} waypoints{sel}", self.status or HELP]
        h = surf.get_height()
        for k, line in enumerate(lines):
            img = font.render(line, True, TEXT)
            surf.blit(img, (5, h - 12 * (len(lines) - k) - 2))
