from dataclasses import dataclass, field, asdict
from typing import Any, List, Tuple, Dict

from scripts.rng_service import RNGService


def _int_attr(obj: Any, name: str) -> int:
    """Read an optional int attribute; non-int values (mocks) become 0."""
    value = getattr(obj, name, 0)
    return value if isinstance(value, int) else 0


@dataclass
class EntitySnapshot:
    type: str
    id: int
    pos: List[float]
    velocity: List[float]
    flip: bool
    action: str
    owner_id: int | None = None  # Player ID who controls this entity (for multiplayer authority)
    lives: int = 0  # Player specific
    air_time: int = 0
    jumps: int = 0
    wall_slide: bool = False
    dashing: int = 0
    shoot_cooldown: int = 0
    walking: int = 0  # Enemy specific
    coins: int = 0  # Player specific (multiplayer score)
    ammo: int = 0  # Player specific (multiplayer)


@dataclass
class ProjectileSnapshot:
    id: int  # Unique projectile ID for network sync
    pos: List[float]
    velocity: float
    timer: float
    owner: str
    owner_id: int | None = None  # Player ID who fired this projectile


@dataclass
class SimulationSnapshot:
    tick: int
    rng_state: Tuple[Any, ...]
    players: List[EntitySnapshot] = field(default_factory=list)
    enemies: List[EntitySnapshot] = field(default_factory=list)
    projectiles: List[ProjectileSnapshot] = field(default_factory=list)
    score: int = 0
    dead_count: int = 0
    transition: int = 0
    # IDs of collectables picked up so far this level (cumulative, multiplayer)
    collected: List[int] = field(default_factory=list)


class SnapshotService:
    @staticmethod
    def capture(game, optimized: bool = False, include_rng: bool = True) -> SimulationSnapshot:
        """Capture the current simulation state.

        Args:
            game: Game-like object with players/enemies/projectiles.
            optimized: Skip enemies, projectiles and RNG (fast player-only capture).
            include_rng: Capture RNG state. Network snapshots set this to False —
                the Mersenne state is ~5KB of JSON and clients never restore it.
        """
        rng_state = () if (optimized or not include_rng) else RNGService.get().get_state()

        # Capture Players (Always needed)
        players: List[EntitySnapshot] = []
        for p in game.players:
            # Handle both property and direct attribute for lives during migration
            lives_val = getattr(p, "lives", getattr(p, "lifes", 0))
            player_snap = EntitySnapshot(
                type="player",
                id=p.id,
                pos=list(p.pos),
                velocity=list(p.velocity),
                flip=p.flip,
                action=p.action,
                owner_id=p.id,  # Players own themselves
                lives=lives_val,
                air_time=p.air_time,
                jumps=p.jumps,
                wall_slide=p.wall_slide,
                dashing=p.dashing,
                shoot_cooldown=p.shoot_cooldown,
                coins=_int_attr(p, "mp_coins"),
                ammo=_int_attr(p, "mp_ammo"),
            )
            players.append(player_snap)

        # Capture Enemies (Skip if optimized)
        enemies: List[EntitySnapshot] = []
        if not optimized:
            for e in game.enemies:
                enemy_snap = EntitySnapshot(
                    type="enemy",
                    id=e.id,
                    pos=list(e.pos),
                    velocity=list(e.velocity),
                    flip=e.flip,
                    action=e.action,
                    owner_id=None,  # Enemies are server-owned in multiplayer
                    walking=e.walking,
                )
                enemies.append(enemy_snap)

        # Capture Projectiles (Skip if optimized)
        projectiles: List[ProjectileSnapshot] = []
        if not optimized and hasattr(game, "projectiles"):
            # Iterate over the system (yields dicts)
            for p in game.projectiles:
                proj_snap = ProjectileSnapshot(
                    id=p.get("id", 0),
                    pos=list(p["pos"]),
                    velocity=p["vel"][0],
                    timer=p["age"],
                    owner=p["owner"],
                    owner_id=p.get("owner_id"),
                )
                projectiles.append(proj_snap)

        return SimulationSnapshot(
            tick=getattr(game, "tick", 0),
            rng_state=rng_state,
            players=players,
            enemies=enemies,
            projectiles=projectiles,
            score=game.cm.coins if hasattr(game, "cm") else 0,
            dead_count=game.dead,
            transition=game.transition,
            collected=list(getattr(game, "collected_ids", [])),
        )

    @staticmethod
    def restore(game, snapshot: SimulationSnapshot) -> None:
        # Restore RNG (only if captured)
        if snapshot.rng_state:
            RNGService.get().set_state(snapshot.rng_state)

        # Restore tick counter
        if hasattr(game, "tick"):
            game.tick = snapshot.tick

        # Restore Globals
        game.dead = snapshot.dead_count
        game.transition = snapshot.transition
        if hasattr(game, "cm"):
            game.cm.coins = snapshot.score

        # Restore Players
        for i, p_snap in enumerate(snapshot.players):
            if i < len(game.players):
                p = game.players[i]
                p.pos = list(p_snap.pos)
                p.velocity = list(p_snap.velocity)
                p.flip = p_snap.flip
                p.set_action(p_snap.action)
                # Set lives (using canonical setter)
                p.lives = p_snap.lives
                p.air_time = p_snap.air_time
                p.jumps = p_snap.jumps
                p.wall_slide = p_snap.wall_slide
                p.dashing = p_snap.dashing
                p.shoot_cooldown = p_snap.shoot_cooldown

        # Restore Enemies
        for i, e_snap in enumerate(snapshot.enemies):
            if i < len(game.enemies):
                e = game.enemies[i]
                e.pos = list(e_snap.pos)
                e.velocity = list(e_snap.velocity)
                e.flip = e_snap.flip
                e.set_action(e_snap.action)
                e.walking = e_snap.walking

        # Restore Projectiles
        if hasattr(game, "projectiles"):
            game.projectiles.clear()
            # Rehydrate dicts directly into the system's private list
            # to avoid side effects of spawn() (sparks/sounds).
            if hasattr(game.projectiles, "_projectiles"):
                for proj_snap in snapshot.projectiles:
                    proj = {
                        "id": proj_snap.id,
                        "pos": list(proj_snap.pos),
                        "vel": [proj_snap.velocity, 0.0],
                        "age": proj_snap.timer,
                        "owner": proj_snap.owner,
                        "owner_id": proj_snap.owner_id,
                    }
                    game.projectiles._projectiles.append(proj)

    @staticmethod
    def serialize(snapshot: SimulationSnapshot) -> Dict[str, Any]:
        return asdict(snapshot)

    @staticmethod
    def deserialize(data: Dict[str, Any]) -> SimulationSnapshot:
        # Reconstruct nested dataclasses
        players = [EntitySnapshot(**p) for p in data.get("players", [])]
        enemies = [EntitySnapshot(**e) for e in data.get("enemies", [])]
        projectiles = [ProjectileSnapshot(**p) for p in data.get("projectiles", [])]

        # Handle tuple conversion for rng_state if it came back as a list from JSON
        rng_state = data.get("rng_state")
        if isinstance(rng_state, list):
            # RNG state is (version, internal_state, gaussian_next)
            # internal_state is also a tuple/list.
            # We need to ensure deeply nested structure is tuple where expected?
            # python's random.setstate is picky.
            # format: (3, (val, val, ...), None)
            if len(rng_state) >= 2 and isinstance(rng_state[1], list):
                rng_state[1] = tuple(rng_state[1])
            rng_state = tuple(rng_state)
        if rng_state is None:
            rng_state = ()

        return SimulationSnapshot(
            tick=data.get("tick", 0),
            rng_state=rng_state,
            players=players,
            enemies=enemies,
            projectiles=projectiles,
            score=data.get("score", 0),
            dead_count=data.get("dead_count", 0),
            transition=data.get("transition", 0),
            collected=list(data.get("collected", [])),
        )
