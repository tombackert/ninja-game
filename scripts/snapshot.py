from dataclasses import dataclass, field
from typing import Any, List, Tuple

from scripts.rng_service import RNGService


@dataclass
class EntitySnapshot:
    type: str
    id: int
    pos: List[float]
    velocity: List[float]
    flip: bool
    action: str
    lives: int = 0  # Player specific
    air_time: int = 0
    jumps: int = 0
    wall_slide: bool = False
    dashing: int = 0
    shoot_cooldown: int = 0
    walking: int = 0  # Enemy specific


@dataclass
class ProjectileSnapshot:
    pos: List[float]
    velocity: float
    timer: float
    owner: str


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


class SnapshotService:
    @staticmethod
    def capture(game) -> SimulationSnapshot:
        rng_state = RNGService.get().get_state()
        
        # Capture Players
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
                lives=lives_val,
                air_time=p.air_time,
                jumps=p.jumps,
                wall_slide=p.wall_slide,
                dashing=p.dashing,
                shoot_cooldown=p.shoot_cooldown,
            )
            players.append(player_snap)

        # Capture Enemies
        enemies: List[EntitySnapshot] = []
        for e in game.enemies:
            enemy_snap = EntitySnapshot(
                type="enemy",
                id=e.id,
                pos=list(e.pos),
                velocity=list(e.velocity),
                flip=e.flip,
                action=e.action,
                walking=e.walking,
            )
            enemies.append(enemy_snap)

        # Capture Projectiles
        projectiles: List[ProjectileSnapshot] = []
        if hasattr(game, "projectiles"):
            # Iterate over the system (yields dicts)
            for p in game.projectiles:
                proj_snap = ProjectileSnapshot(
                    pos=list(p["pos"]),
                    velocity=p["vel"][0],
                    timer=p["age"],
                    owner=p["owner"]
                )
                projectiles.append(proj_snap)

        return SimulationSnapshot(
            tick=0,  # TODO: Game needs a global tick counter
            rng_state=rng_state,
            players=players,
            enemies=enemies,
            projectiles=projectiles,
            score=game.cm.coins if hasattr(game, "cm") else 0,
            dead_count=game.dead,
            transition=game.transition
        )

    @staticmethod
    def restore(game, snapshot: SimulationSnapshot) -> None:
        # Restore RNG
        RNGService.get().set_state(snapshot.rng_state)
        
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
                        "pos": list(proj_snap.pos),
                        "vel": [proj_snap.velocity, 0.0],
                        "age": proj_snap.timer,
                        "owner": proj_snap.owner
                    }
                    game.projectiles._projectiles.append(proj)