"""A map file (data/maps/<id>.json) as the route planner sees it.

The intended route is part of the map: `map_data.route`, a list of waypoints
with the fields of tools.worlds.planner.Waypoint (x0, y0, x1, y1 in tiles,
inclusive; ground, label, guide). A built level (tools/worlds/levels) writes it
from its `lv.wp(...)` calls (builder.Level.to_json), an editor map gets a first
draft from tools/worlds/draft.py. Either way the planner reads the map, not the
code that made it:

    level script or editor -> data/maps/<id>.json (tiles + route) -> planner -> plans/<id>.json

`MapLevel` holds a loaded map with what the planner and the hearts
(tools/worlds/hearts.py) read of it: terrain, spawn, route, and the objects
and hazard tiles. Maps without a route load with an empty one.
"""

from __future__ import annotations

import dataclasses
import json
import os

from tools.worlds.physics import PHYSICS_TILES, TS, Terrain, terrain_from_map
from tools.worlds.planner import Waypoint

MAPS_DIR = "data/maps"
CHECKPOINT = "checkpoint"  # scripts/checkpoints.py
FIELDS = [f.name for f in dataclasses.fields(Waypoint)]


def route_to_json(route) -> list[dict]:
    """Waypoints as map_data.route rows (all fields, in Waypoint's order)."""
    return [dataclasses.asdict(w) for w in route]


def route_from_json(rows) -> list[Waypoint]:
    """map_data.route rows as Waypoints; missing fields take Waypoint's defaults."""
    out = []
    for row in rows or ():
        unknown = set(row) - set(FIELDS)
        if unknown:
            raise ValueError(f"waypoint {row}: unknown fields {sorted(unknown)}")
        out.append(Waypoint(**row))
    return out


def map_path(map_id, maps_dir: str = MAPS_DIR) -> str:
    return os.path.join(maps_dir, f"{map_id}.json")


def write_map(path: str, data: dict) -> None:
    """Compact JSON, as Tilemap.save and builder.Level.save write maps."""
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))


def kill_y(solids) -> float:
    """Where the planner counts a fall as lost: 4 tiles below the lowest solid tile."""
    return (max(y for _, y in solids) + 4) * TS


class MapLevel:
    """A loaded map: its JSON (`data`) and the planner's view of it.

    For the hearts it offers what they read of a builder.Level: `solid`
    ((x, y) -> type of the physics tiles), `objects` ((x, y) -> (type,
    variant) of the other grid tiles), `fixed` ((x, y) -> the tile's own
    fields of crumbling blocks and flame jets), `route`, `spawn_tile`,
    `is_solid`, `solids()` and `heart()`; `save()` writes the map back."""

    def __init__(self, map_id, data: dict, path: str | None = None):
        self.map_id = map_id
        self.data = data
        self.path = path
        md = data["map_data"]
        self.tilemap: dict = md["tilemap"]
        self.route: list[Waypoint] = route_from_json(md.get("route"))
        self.solid: dict = {}
        self.objects: dict = {}
        self.fixed: dict = {}
        for t in self.tilemap.values():
            xy = (int(t["pos"][0]), int(t["pos"][1]))
            if t["type"] in PHYSICS_TILES:
                self.solid[xy] = t["type"]
                extra = {k: v for k, v in t.items() if k not in ("type", "pos")}
                if t["type"] in ("crumble", "flamejet"):
                    self.fixed[xy] = extra
            else:
                self.objects[xy] = (t["type"], t.get("variant", 0))
        self._terrain = None

    @classmethod
    def load(cls, map_id, maps_dir: str = MAPS_DIR) -> "MapLevel":
        path = map_path(map_id, maps_dir)
        with open(path) as f:
            return cls(map_id, json.load(f), path)

    # --- what the planner reads -------------------------------------------
    @property
    def spawn_tile(self) -> tuple | None:
        """The player spawner's tile (spawners variant 0), on the grid or offgrid."""
        for (x, y), (kind, variant) in self.objects.items():
            if kind == "spawners" and variant == 0:
                return x, y
        for t in self.data["map_data"].get("offgrid", []):
            if t["type"] == "spawners" and t.get("variant", 0) == 0:
                return int(t["pos"][0] // TS), int(t["pos"][1] // TS)
        return None

    @property
    def spawn_px(self) -> tuple:
        x, y = self.spawn_tile
        return x * TS, y * TS

    @property
    def flag_tile(self) -> tuple | None:
        for xy, (kind, _v) in self.objects.items():
            if kind == "flag":
                return xy
        return None

    @property
    def checkpoint_tiles(self) -> list[tuple]:
        """The air tiles a checkpoint respawns the player on (scripts/checkpoints.py), west to east."""
        found = [(x, y) for (x, y), (kind, _v) in self.objects.items() if kind == CHECKPOINT]
        for t in self.data["map_data"].get("offgrid", []):
            if t["type"] == CHECKPOINT:  # banner's top left (px), two tiles tall
                found.append((int(t["pos"][0] // TS), int(t["pos"][1] // TS) + 1))
        return sorted(found)

    def is_solid(self, x, y) -> bool:
        return (x, y) in self.solid

    def solids(self) -> Terrain:
        if self._terrain is None:
            self._terrain = terrain_from_map(self.data["map_data"])
        return self._terrain

    def kill_y(self) -> float:
        return kill_y(self.solids())

    # --- what changes the map ---------------------------------------------
    def set_route(self, route) -> None:
        self.route = list(route)
        if self.route:
            self.data["map_data"]["route"] = route_to_json(self.route)
        else:
            self.data["map_data"].pop("route", None)

    def heart(self, x, y) -> None:
        """A heart pickup on air tile (x, y), in place of what lies there (a coin)."""
        if (x, y) in self.solid:
            raise ValueError(f"map {self.map_id}: heart at {(x, y)} inside solid tile")
        self.objects[(x, y)] = ("heart", 0)
        self.tilemap[f"{x};{y}"] = {"type": "heart", "variant": 0, "pos": [x, y]}

    def hearts(self) -> list[tuple]:
        return sorted(xy for xy, (kind, _v) in self.objects.items() if kind == "heart")

    def remove_hearts(self) -> list[tuple]:
        """Take the hearts out (a heart that replaced a coin leaves the tile empty)."""
        gone = self.hearts()
        for x, y in gone:
            del self.objects[(x, y)]
            del self.tilemap[f"{x};{y}"]
        return gone

    def save(self, path: str | None = None) -> str:
        path = path or self.path or map_path(self.map_id)
        write_map(path, self.data)
        return path
