"""Behaviors of the enemy kinds (scripts/enemy_kinds.py).

A policy reads its numbers (speed, sight, fire period) from the enemy's
kind and never from the level number: a gunner in level 40 is the gunner
of level 1. Policies return intents; `Enemy.update` applies them.
"""

from __future__ import annotations

from typing import Any, Dict

from scripts.ai.core import Policy
from scripts.constants import GRAVITY_ACCEL
from scripts.enemy_kinds import CLUSTER_HOLD, CLUSTER_RADIUS, DEFAULT, EnemyKind
from scripts.hazards import SPIKES, HazardSystem
from scripts.rng_service import RNGService

FEET = 23  # px below the enemy's top where the ground ahead is probed
PROBE = 7  # px ahead of the enemy's center
TURRET_WINDUP = 40  # frames a turret (or thrower) waits after the player comes into sight
THROW_PAUSE = 24  # frames a thrower stands still after a throw
CHASER_GIVE_UP = 2  # a chaser stays awake up to this many times its sight


def _kind(entity: Any) -> EnemyKind:
    kind = getattr(entity, "kind", None)
    return kind if isinstance(kind, EnemyKind) else DEFAULT


def _intent() -> Dict[str, Any]:
    return {"movement": (0, 0), "shoot": False, "shoot_direction": 0, "jump": False}


def _to_player(entity: Any) -> tuple:
    player = entity.game.player
    return player.pos[0] - entity.pos[0], player.pos[1] - entity.pos[1]


def _ground_ahead(entity: Any, tilemap: Any, ahead: int = PROBE) -> bool:
    x = entity.rect().centerx + (-ahead if entity.flip else ahead)
    return bool(tilemap.solid_check((x, entity.pos[1] + FEET)))


def _spikes_ahead(entity: Any, tilemap: Any, ahead: int = PROBE) -> bool:
    """Spikes or a flame jet's reach in the tile ahead at body height: enemies
    keep out of both (a flame burns them, see HazardSystem.burn_enemies)."""
    tiles = getattr(tilemap, "tilemap", None)
    if not isinstance(tiles, dict):
        return False
    ts = tilemap.tile_size
    hazards = getattr(entity.game, "hazards", None)
    zones = hazards.zones if isinstance(hazards, HazardSystem) else {}
    x = int(entity.rect().centerx + (-ahead if entity.flip else ahead)) // ts
    for y in (entity.pos[1] + 8, entity.pos[1] + 14):
        ty = int(y) // ts
        tile = tiles.get(f"{x};{ty}")
        if tile is not None and tile["type"] == SPIKES:
            return True
        if any(cause == "flame" for _r, cause, _j in zones.get((x, ty), ())):
            return True
    return False


def _walk(entity: Any, tilemap: Any, speed: float) -> float:
    """One step of walking in the facing direction; turns at walls, edges and
    spikes. Returns the horizontal movement (0 on a turn)."""
    if tilemap.solid_check((entity.rect().centerx + (-PROBE if entity.flip else PROBE), entity.pos[1] + FEET)):
        if entity.collisions["right"] or entity.collisions["left"] or _spikes_ahead(entity, tilemap):
            entity.flip = not entity.flip
            return 0
        return -speed if entity.flip else speed
    entity.flip = not entity.flip  # edge of the platform
    return 0


def _grounded(entity: Any, tilemap: Any) -> bool:
    """Standing on solid ground (not rising). Steadier than collisions["down"],
    which is only set on the frames gravity pushes the entity into the floor."""
    r = entity.rect()
    return entity.velocity[1] >= 0 and bool(tilemap.solid_check((r.centerx, r.bottom + 1)))


def _cluster_clear(entity: Any) -> bool:
    """No other enemy close by fired a moment ago (spreads a cluster's shots)."""
    for other in getattr(entity.game, "enemies", ()):
        if other is entity or getattr(other, "since_shot", CLUSTER_HOLD) >= CLUSTER_HOLD:
            continue
        if abs(other.pos[0] - entity.pos[0]) <= CLUSTER_RADIUS and abs(other.pos[1] - entity.pos[1]) <= CLUSTER_RADIUS:
            return False
    return True


def _in_sight(kind: EnemyKind, dx: float, dy: float) -> bool:
    return abs(dx) < kind.sight_x and abs(dy) < kind.sight_y


class GunnerPolicy(Policy):
    """The classic enemy: wanders a while, stops, fires if it faces the player."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        kind = _kind(entity)
        rng = RNGService.get()
        result = _intent()
        if entity.walking:
            result["movement"] = (_walk(entity, entity.game.tilemap, kind.speed), 0)
            entity.walking = max(0, entity.walking - 1)
            if not entity.walking:
                dx, dy = _to_player(entity)
                facing = (entity.flip and dx < 0) or (not entity.flip and dx > 0)
                if facing and _in_sight(kind, dx, dy) and _cluster_clear(entity):
                    result["shoot"] = True
                    result["shoot_direction"] = -1 if entity.flip else 1
        elif rng.random() < 0.01:
            entity.walking = rng.randint(30, 120)
        return result


# Old name of the gunner (maps, tests and tools that ask for it by name)
ScriptedEnemyPolicy = GunnerPolicy


class PatrolPolicy(Policy):
    """Walks its platform from edge to edge without a pause. No gun."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        result = _intent()
        result["movement"] = (_walk(entity, entity.game.tilemap, _kind(entity).speed), 0)
        return result


class TurretPolicy(Policy):
    """Stands still, turns to the player and fires on a fixed beat while the
    player is in sight (the first shot a wind-up after they come into it)."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        kind = _kind(entity)
        result = _intent()
        dx, dy = _to_player(entity)
        entity.flip = dx < 0
        entity.cooldown = max(0, getattr(entity, "cooldown", 0) - 1)
        if not _in_sight(kind, dx, dy):
            entity.awake = False
            return result
        if not getattr(entity, "awake", False):  # the player just came into sight
            entity.awake = True
            entity.cooldown = max(entity.cooldown, TURRET_WINDUP)
        if entity.cooldown == 0 and _cluster_clear(entity):
            result["shoot"] = True
            result["shoot_direction"] = -1 if dx < 0 else 1
            entity.cooldown = kind.fire_period
        return result


# Old name of the turret
ShooterPolicy = TurretPolicy


class ChaserPolicy(Policy):
    """Sleeps until the player comes near, then runs at them; stops at walls
    and edges instead of falling. Gives up when the player is far away."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        kind = _kind(entity)
        result = _intent()
        dx, dy = _to_player(entity)
        if _in_sight(kind, dx, dy):
            entity.awake = True
        elif abs(dx) > kind.sight_x * CHASER_GIVE_UP or abs(dy) > kind.sight_y * CHASER_GIVE_UP:
            entity.awake = False
        if not getattr(entity, "awake", False) or abs(dx) < 4:
            return result
        entity.flip = dx < 0
        tilemap = entity.game.tilemap
        blocked = (
            (entity.collisions["left"] if entity.flip else entity.collisions["right"])
            or not _ground_ahead(entity, tilemap)
            or _spikes_ahead(entity, tilemap)
        )
        if not blocked:
            result["movement"] = (-kind.speed if entity.flip else kind.speed, 0)
        return result


class JumperPolicy(Policy):
    """Hops along its platform: a pause on the ground, then a hop forward.
    Turns before a hop that would land in a gap or against a wall."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        kind = _kind(entity)
        result = _intent()
        tilemap = entity.game.tilemap
        if not _grounded(entity, tilemap):
            result["movement"] = (-kind.speed if entity.flip else kind.speed, 0)
            return result
        entity.cooldown = max(0, getattr(entity, "cooldown", 0) - 1)
        if entity.cooldown:
            return result
        # Air time of a hop (up and down again) and how far it carries
        reach = int(kind.speed * (2 * -kind.hop_velocity / GRAVITY_ACCEL)) + PROBE
        for _ in range(2):
            if (
                _ground_ahead(entity, tilemap, reach)
                and not _ground_ahead_blocked(entity, tilemap, reach)
                and not _spikes_ahead(entity, tilemap, reach)
            ):
                break
            entity.flip = not entity.flip
        else:
            entity.cooldown = kind.hop_period  # boxed in: wait, try again later
            return result
        result["jump"] = True
        result["jump_velocity"] = kind.hop_velocity
        result["movement"] = (-kind.speed if entity.flip else kind.speed, 0)
        entity.cooldown = kind.hop_period
        return result


def _ground_ahead_blocked(entity: Any, tilemap: Any, reach: int) -> bool:
    """A wall at body height between the jumper and where its hop lands."""
    step = -1 if entity.flip else 1
    cx = entity.rect().centerx
    y = entity.pos[1] + 8
    return any(tilemap.solid_check((cx + step * d, y)) for d in range(PROBE, reach + 1, 8))


def throw_velocity(kind: EnemyKind, dx: float, dy: float) -> tuple | None:
    """(vx, vy) of a star thrown with the kind's upward speed and gravity that
    comes down on a target dx, dy px away (dy positive down), or None if the
    target is out of reach (too high, or further than the kind's top speed)."""
    vy, g = kind.throw_vy, kind.throw_gravity
    disc = vy * vy + 2 * g * dy
    if g <= 0 or disc < 0:
        return None
    t = (-vy + disc**0.5) / g  # frames until it comes down through the target's height
    vx = dx / t
    if abs(vx) > kind.bullet_speed:
        return None
    return vx, vy


class ThrowerPolicy(Policy):
    """Paces `kind.pace` px to either side of where it spawned (turning early at
    walls, edges and hazards) and, on a fixed beat while the player is in sight
    and in reach, stops, turns to them and throws a star in an arc that comes
    down where they stand now."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        kind = _kind(entity)
        result = _intent()
        entity.cooldown = max(0, getattr(entity, "cooldown", 0) - 1)
        player = entity.game.player
        r = entity.rect()
        dx = player.rect().centerx - r.centerx
        dy = player.rect().centery - (r.top + 3)
        if getattr(entity, "pause", 0) > 0:  # the follow-through of a throw
            entity.pause -= 1
            return result
        if _in_sight(kind, dx, dy):
            if not getattr(entity, "awake", False):  # the player just came into sight
                entity.awake = True
                entity.cooldown = max(entity.cooldown, TURRET_WINDUP)
            if entity.cooldown == 0 and _cluster_clear(entity):
                velocity = throw_velocity(kind, dx, dy)
                if velocity is not None:
                    entity.flip = dx < 0
                    result["throw"] = velocity
                    entity.cooldown = kind.fire_period
                    entity.pause = THROW_PAUSE
                    return result
        else:
            entity.awake = False
        # Pace around home
        home = getattr(entity, "home", entity.pos[0])
        if entity.pos[0] - home > kind.pace and not entity.flip:
            entity.flip = True
        elif home - entity.pos[0] > kind.pace and entity.flip:
            entity.flip = False
        result["movement"] = (_walk(entity, entity.game.tilemap, kind.speed), 0)
        return result
