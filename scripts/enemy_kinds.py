"""Enemy kinds: the difficulty dial of a level is which enemies stand where.

Every enemy of a kind behaves the same in every level (no scaling with the
level number, as in Super Mario Bros.): a level gets harder by placing
harder kinds, more of them, or in worse spots. The kind is stored in the
map as the variant of the enemy's spawner tile, so old maps (variant 1)
keep their classic gunner and the editor places a kind by its spawner
image (data/images/tiles/spawners/<variant>.png).

    variant  kind    threat
    1        gunner  wanders, stops and fires along its line of sight
    2        patrol  walks its platform edge to edge, kills on touch, no gun
    3        turret  stands, turns to the player, fires on a fixed beat
    4        chaser  wakes when the player comes near and runs at them, kills on touch
    5        jumper  hops along its platform, kills on touch: no jumping over it
    6        thrower paces a few tiles to and fro, throws ninja stars in an arc
                     aimed at the player, on a fixed beat

"Kills on touch" means a hit like a bullet's: a life lost (Player.take_hit),
the player thrown back and blinking for a moment, no respawn. A dash kills
every kind.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnemyKind:
    name: str
    variant: int  # spawner variant in the map
    policy: str  # behavior (scripts/ai/behaviors.py)
    speed: float = 0.0  # px per frame while walking
    bullet_speed: float = 0.0  # px per frame; 0: carries no gun
    sight_x: int = 0  # fires only at a player this close horizontally (px) ...
    sight_y: int = 0  # ... and vertically
    fire_period: int = 0  # turret: frames between shots
    contact: bool = False  # touching it costs a life (unless dashing)
    hop_period: int = 0  # jumper: frames on the ground between hops
    hop_velocity: float = 0.0  # jumper: vertical speed of a hop
    projectile: str = "bullet"  # what it fires: "bullet" (straight, from a gun) or "star" (thrown in an arc)
    throw_vy: float = 0.0  # thrower: upward speed a star leaves the hand with
    throw_gravity: float = 0.0  # thrower: a star's gravity per frame
    pace: int = 0  # thrower: px it walks to either side of where it spawned

    @property
    def armed(self) -> bool:
        return self.bullet_speed > 0


# Half the view (640 px) plus a little: an enemy fires only once it is about
# to come into the picture, not from far outside it (backlog: "range should
# go just past the frame edge").
SIGHT_X = 336

GUNNER = EnemyKind("gunner", 1, "gunner", speed=0.6, bullet_speed=1.8, sight_x=SIGHT_X, sight_y=15)
PATROL = EnemyKind("patrol", 2, "patrol", speed=0.5, contact=True)
TURRET = EnemyKind("turret", 3, "turret", bullet_speed=2.2, sight_x=SIGHT_X, sight_y=24, fire_period=96)
CHASER = EnemyKind("chaser", 4, "chaser", speed=0.9, sight_x=160, sight_y=48, contact=True)
JUMPER = EnemyKind("jumper", 5, "jumper", speed=0.7, contact=True, hop_period=50, hop_velocity=-2.6)
# A turret on its feet: paces 5 tiles (2.5 to either side) and lobs stars over
# cover, so a ledge above or below it is no shelter. bullet_speed caps how
# fast a star flies sideways: at its own height a star reaches about 165 px,
# further down further; it only throws at a player it can reach.
THROWER = EnemyKind(
    "thrower",
    6,
    "thrower",
    speed=0.45,
    bullet_speed=3.0,
    sight_x=220,
    sight_y=112,
    fire_period=110,
    projectile="star",
    throw_vy=-2.2,
    throw_gravity=0.08,
    pace=40,
)

KINDS = {k.name: k for k in (GUNNER, PATROL, TURRET, CHASER, JUMPER, THROWER)}
BY_VARIANT = {k.variant: k for k in KINDS.values()}
ENEMY_VARIANTS = tuple(sorted(BY_VARIANT))
DEFAULT = GUNNER

# Tilemap.extract ids of every spawner: the player's (0) and each enemy kind's
SPAWNER_IDS = [("spawners", 0)] + [("spawners", v) for v in ENEMY_VARIANTS]

# Shot spacing within a cluster (backlog): an armed enemy holds its fire
# while another one this close fired within the last CLUSTER_HOLD frames.
CLUSTER_RADIUS = 48
CLUSTER_HOLD = 45


def kind_for_variant(variant: int) -> EnemyKind:
    """Kind of an enemy spawner variant (unknown variants: the classic gunner)."""
    return BY_VARIANT.get(variant, DEFAULT)


def get_kind(kind: "str | EnemyKind | None") -> EnemyKind:
    if isinstance(kind, EnemyKind):
        return kind
    if kind is None:
        return DEFAULT
    if kind not in KINDS:
        raise ValueError(f"unknown enemy kind {kind!r} (known: {', '.join(KINDS)})")
    return KINDS[kind]
