import json
import os
import traceback
from datetime import datetime

import pygame

from scripts.entities import Enemy, Player
from scripts.logger import get_logger
from scripts.settings import settings
from scripts.utils import Animation

log = get_logger("tilemap")

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

NEIGHBOR_OFFSET = [
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
    (1, 0),
    (0, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
]
PHYSICS_TILES = {"grass", "stone"}  # things an entity can colid with
AUTOTILE_TILES = {"grass", "stone"}


class Tilemap:
    def __init__(self, game, tile_size=16):
        self.game = game
        self.level = settings.get_selected_editor_level()
        self.tile_size = tile_size
        self.tilemap = {}
        self.offgrid_tiles = []
        self.enemies = []
        self.players = []
        self.meta_data = {}
        # Current save schema version (Issue 21)
        self.version = 2
        # Cache for tile type counts (recomputed on perf overlay rebuild cycles)
        self._cached_type_counts = None  # type: ignore[assignment]
        self.save_dir = "data/saves"
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

    def extract(self, id_pairs, keep=False):
        matches = []
        for tile in self.offgrid_tiles.copy():
            if (tile["type"], tile["variant"]) in id_pairs:
                matches.append(tile.copy())
                if not keep:
                    self.offgrid_tiles.remove(tile)

        for loc in self.tilemap.copy():
            tile = self.tilemap[loc]
            if (tile["type"], tile["variant"]) in id_pairs:
                matches.append(tile.copy())
                matches[-1]["pos"] = matches[-1]["pos"].copy()
                matches[-1]["pos"][0] *= self.tile_size
                matches[-1]["pos"][1] *= self.tile_size
                if not keep:
                    del self.tilemap[loc]

        return matches

    def tiles_around(self, pos):
        tiles = []
        tile_loc = (int(pos[0] // self.tile_size), int(pos[1] // self.tile_size))
        for offset in NEIGHBOR_OFFSET:
            check_loc = str(tile_loc[0] + offset[0]) + ";" + str(tile_loc[1] + offset[1])
            if check_loc in self.tilemap:
                tiles.append(self.tilemap[check_loc])
        return tiles

    def save(self, path):
        game_state = {}

        meta_data = self.meta_data.copy()
        if not meta_data:
            meta_data = {
                "map": self.level,
                "timer": {
                    "current_time": "00:00:00",
                    "start_time": "00:00:00",
                },
            }

        entity_data = {
            "players": [
                {
                    "id": player.id,
                    "pos": player.pos,
                    "velocity": player.velocity,
                    "air_time": player.air_time,
                    "action": player.action,
                    "flip": player.flip,
                    "alive": player.alive,
                    # Write new canonical key 'lives' (legacy 'lifes' supported on load)
                    "lives": getattr(player, "lives", getattr(player, "lifes", 0)),
                    "respawn_pos": player.respawn_pos,
                }
                for player in self.players
            ],
            "enemies": [
                {
                    "id": enemy.id,
                    "pos": enemy.pos,
                    "velocity": enemy.velocity,
                    "alive": enemy.alive,
                }
                for enemy in self.enemies
            ],
        }

        tilemap_data = {
            "tilemap": self.tilemap,
            "tile_size": self.tile_size,
            "offgrid": self.offgrid_tiles,
        }
        # Persist version inside meta_data for forward detection
        meta_data["version"] = self.version
        game_state["meta_data"] = meta_data
        game_state["entities_data"] = entity_data
        game_state["map_data"] = tilemap_data

        try:
            with open(path, "w") as f:
                json.dump(game_state, f, indent=4)
            log.info("Game saved", path)
            return True
        except Exception as e:
            log.error("Error saving tilemap", e)
            return False

    def _migrate(self, data: dict) -> dict:
        """Migrate legacy save data in-place returning upgraded dict.

        Supported migrations:
          - v1 -> v2: inject meta_data.version, ensure players use 'lives' key
        """
        meta = data.get("meta_data") or {}
        detected_version = meta.get("version", 1)
        if detected_version == 1:
            # Add lives key if only legacy 'lifes' present
            entities_data = data.get("entities_data", {})
            for p in entities_data.get("players", []):
                if "lives" not in p and "lifes" in p:
                    p["lives"] = p["lifes"]
            meta["version"] = 2
            data["meta_data"] = meta
            detected_version = 2
        # Future migrations would chain here.
        return data

    def load(self, path, load_entities=True):
        try:
            with open(path, "r") as f:
                data = json.load(f)

            # Perform migrations (Issue 21)
            data = self._migrate(data)

            self.meta_data = data.get("meta_data", {})
            self.version = self.meta_data.get("version", 1)
            self.level = self.meta_data.get("map", self.level)

            map_data = data.get("map_data", data)
            self.tilemap = map_data["tilemap"]
            self.tile_size = map_data["tile_size"]
            self.offgrid_tiles = map_data["offgrid"]

            self.players = []
            self.enemies = []

            if load_entities:
                entities_data = data.get("entities_data", {})

                for player_data in entities_data.get("players", []):
                    # Backward compatibility: accept 'lifes' or 'lives'. Prefer 'lives'.
                    lives_value = player_data.get("lives", player_data.get("lifes", 3))
                    player = Player(
                        self.game,
                        player_data["pos"],
                        (8, 15),
                        player_data["id"],
                        lives=lives_value,
                        respawn_pos=player_data["respawn_pos"],
                    )
                    player.velocity = player_data.get("velocity", [0, 0])
                    player.air_time = player_data.get("air_time", 0)
                    player.action = player_data.get("action", "idle")
                    player.flip = player_data.get("flip", False)
                    player.alive = player_data.get("alive", True)
                    player.respawn_pos = player_data.get("respawn_pos", [0, 0])
                    self.players.append(player)

                for enemy_data in entities_data.get("enemies", []):
                    enemy = Enemy(self.game, enemy_data["pos"], (8, 15), enemy_data["id"])
                    enemy.velocity = enemy_data.get("velocity", [0, 0])
                    enemy.alive = enemy_data.get("alive", True)
                    self.enemies.append(enemy)

            # print(f"Tilemap loaded from {path}")
            # Precompute immutable type counts for performance HUD (done once per level load)
            try:
                self._cached_type_counts = self._recompute_type_counts()
            except Exception:
                pass
        except Exception as e:
            traceback.print_exc()
            log.error("Error while loading Tilemap", e)

    def solid_check(self, pos):
        tile_loc = str(int(pos[0] // self.tile_size)) + ";" + str(int(pos[1] // self.tile_size))
        if tile_loc in self.tilemap:
            if self.tilemap[tile_loc]["type"] in PHYSICS_TILES:
                return self.tilemap[tile_loc]

    def physics_rects_around(self, pos):
        return [
            pygame.Rect(
                tile["pos"][0] * self.tile_size,
                tile["pos"][1] * self.tile_size,
                self.tile_size,
                self.tile_size,
            )
            for tile in self.tiles_around(pos)
            if tile["type"] in PHYSICS_TILES
        ]

    def autotile(self):
        for loc in self.tilemap:
            tile = self.tilemap[loc]
            neighbors = set()
            for shift in [(1, 0), (-1, 0), (0, -1), (0, 1)]:
                check_loc = str(tile["pos"][0] + shift[0]) + ";" + str(tile["pos"][1] + shift[1])
                if check_loc in self.tilemap:
                    if self.tilemap[check_loc]["type"] == tile["type"]:
                        neighbors.add(shift)
            neighbors = tuple(sorted(neighbors))
            if tile["type"] in AUTOTILE_TILES and neighbors in AUTOTILE_MAP:
                tile["variant"] = AUTOTILE_MAP[neighbors]

    def render(self, surf, offset=(0, 0)):
        for tile in self.offgrid_tiles:
            image = self.get_image(tile)
            if image:
                surf.blit(image, (tile["pos"][0] - offset[0], tile["pos"][1] - offset[1]))

        for x in range(
            int(offset[0] // self.tile_size),
            int((offset[0] + surf.get_width()) // self.tile_size) + 1,
        ):
            for y in range(
                int(offset[1] // self.tile_size),
                int((offset[1] + surf.get_height()) // self.tile_size) + 1,
            ):
                loc = str(x) + ";" + str(y)
                if loc in self.tilemap:
                    tile = self.tilemap[loc]
                    image = self.get_image(tile)
                    if image:
                        surf.blit(
                            image,
                            (
                                tile["pos"][0] * self.tile_size - offset[0],
                                tile["pos"][1] * self.tile_size - offset[1],
                            ),
                        )

    def get_image(self, tile):
        asset = self.game.assets.get(tile["type"])
        if asset is None:
            log.warn(f"Missing asset for tile type {tile['type']}")
            return None

        if isinstance(asset, list):
            if 0 <= tile["variant"] < len(asset):
                return asset[tile["variant"]]
            else:
                log.warn(f"Variant index {tile['variant']} out of bounds for tile type {tile['type']}")
                return None
        elif isinstance(asset, pygame.Surface):
            return asset
        elif isinstance(asset, Animation):
            frame = asset.get_current_frame()
            if isinstance(frame, pygame.Surface):
                return frame
            else:
                log.warn(f"Animation frame not Surface for tile type {tile['type']}")
                return None
        else:
            log.warn(f"Unexpected asset type for tile type {tile['type']}: {type(asset)}")
            return None

    def save_game(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"round-{self.level}-{timestamp}.json"
        save_path = os.path.join(self.save_dir, filename)

        self.meta_data = {
            "map": self.game.level,
            "timer": {
                "current_time": self.game.timer.text,
                "start_time": self.game.timer.start_time,
            },
        }

        self.players = self.game.players
        self.enemies = self.game.enemies

        success = self.save(save_path)
        if success:
            return True, filename
        else:
            return False, ""

    def load_game(self, game_state):
        pass

    def get_player_count(self):
        return len(self.players)

    def get_enemy_count(self):
        return len(self.enemies)

    # ------------------------------------------------------------------
    # Introspection helpers for performance HUD
    def get_type_counts(self, throttle: bool = True) -> dict:
        """Return cached counts of tiles by *type* (including offgrid).

        Tiles do not change during gameplay (except collectables handled
        separately), so we precompute once at level load and simply
        return the snapshot here. The parameter `throttle` is retained
        for backward compatibility but no longer affects behaviour.
        """
        if self._cached_type_counts is None:
            # Fallback (should be precomputed at load time)
            self._cached_type_counts = self._recompute_type_counts()
        return self._cached_type_counts

    # Internal helper to build counts (called once at load)
    def _recompute_type_counts(self) -> dict:
        counts: dict[str, int] = {}
        for tile in self.tilemap.values():
            t = tile.get("type")
            if t:
                counts[t] = counts.get(t, 0) + 1
        for tile in self.offgrid_tiles:
            t = tile.get("type")
            if t:
                counts[t] = counts.get(t, 0) + 1
        try:
            from scripts.tilemap import PHYSICS_TILES  # local import safe

            physics_total = sum(v for k, v in counts.items() if k in PHYSICS_TILES)
            if physics_total:
                counts["_physics"] = physics_total
        except Exception:
            pass
        return counts

    def extract_entities(self):
        pass
