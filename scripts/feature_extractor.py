from typing import Any, Dict

import math
from scripts.snapshot import SimulationSnapshot


class FeatureExtractor:
    """Converts a SimulationSnapshot into a structured observation for RL.

    The observation is ego-centric to a specific entity (usually a player).
    """

    def __init__(self, grid_size: int = 13, max_enemies: int = 5, max_projectiles: int = 5):
        self.grid_size = grid_size
        self.max_enemies = max_enemies
        self.max_projectiles = max_projectiles
        # TODO: Inject tilemap or have snapshot include local grid data?
        # For now, we might assume the snapshot contains enough info or we pass tilemap context.
        # Since SnapshotService currently doesn't capture the static tilemap (it's large),
        # the extractor might need a reference to the static level data or the snapshot
        # should ideally contain a local grid cut-out.
        # As a compromise for this iteration, we will focus on Entity features.
        # Grid features will require efficient querying of the static Tilemap which isn't in the snapshot.

    def extract(self, snapshot: SimulationSnapshot, entity_id: int) -> Dict[str, Any]:
        # Find ego entity
        me = next((p for p in snapshot.players if p.id == entity_id), None)
        if not me:
            # If not found (e.g. dead), return zeros or specific dead state
            return self._empty_observation()

        obs: Dict[str, Any] = {}

        # 1. Self features
        # Normalize? For now, raw values or simple relative scaling.
        obs["self"] = [
            me.pos[0],
            me.pos[1],
            me.velocity[0],
            me.velocity[1],
            1.0 if me.flip else 0.0,
            me.lives,
            me.air_time,
            me.dashing,
        ]

        # 2. Enemy features (relative to self)
        # Sort by distance
        enemies = sorted(snapshot.enemies, key=lambda e: math.hypot(e.pos[0] - me.pos[0], e.pos[1] - me.pos[1]))

        enemy_features = []
        for i in range(self.max_enemies):
            if i < len(enemies):
                e = enemies[i]
                # Relative pos/vel
                dx = e.pos[0] - me.pos[0]
                dy = e.pos[1] - me.pos[1]
                enemy_features.extend([dx, dy, e.velocity[0], e.velocity[1], 1.0])  # 1.0 = present
            else:
                enemy_features.extend([0.0, 0.0, 0.0, 0.0, 0.0])  # 0.0 = absent
        obs["enemies"] = enemy_features

        # 3. Projectile features (relative)
        projectiles = sorted(snapshot.projectiles, key=lambda p: math.hypot(p.pos[0] - me.pos[0], p.pos[1] - me.pos[1]))

        proj_features = []
        for i in range(self.max_projectiles):
            if i < len(projectiles):
                p = projectiles[i]
                dx = p.pos[0] - me.pos[0]
                dy = p.pos[1] - me.pos[1]
                # Encode owner: 1 for player (friendly?), -1 for enemy (hostile)
                # Assumption: 'me' is a player.
                owner_val = 1.0 if p.owner == "player" else -1.0
                proj_features.extend([dx, dy, p.velocity, owner_val, 1.0])
            else:
                proj_features.extend([0.0, 0.0, 0.0, 0.0, 0.0])
        obs["projectiles"] = proj_features

        return obs

    def _empty_observation(self) -> Dict[str, Any]:
        # Return zeroed structures matching the shape of a valid observation
        return {
            "self": [0.0] * 8,
            "enemies": [0.0] * (5 * self.max_enemies),
            "projectiles": [0.0] * (5 * self.max_projectiles),
        }
