from typing import Any, Dict
from scripts.snapshot import SimulationSnapshot, EntitySnapshot, ProjectileSnapshot


def compute_delta(prev: SimulationSnapshot, curr: SimulationSnapshot) -> Dict[str, Any]:
    """
    Computes the difference between two snapshots.
    Returns a dictionary containing only changed fields.
    """
    delta = {}

    # 1. Global Fields
    if prev.tick != curr.tick:
        delta["tick"] = curr.tick
    if prev.score != curr.score:
        delta["score"] = curr.score
    if prev.dead_count != curr.dead_count:
        delta["dead_count"] = curr.dead_count
    if prev.transition != curr.transition:
        delta["transition"] = curr.transition
    if prev.rng_state != curr.rng_state:
        delta["rng_state"] = curr.rng_state  # Full tuple if changed

    # 2. Entities (Players) - Assumes ID stability and order matching for MVP
    # Ideally we map by ID. Here we assume list indices match for simplicity if count is same.
    # If counts differ, send full list (fallback).
    if len(prev.players) != len(curr.players):
        delta["players"] = [asdict_shallow(p) for p in curr.players]
    else:
        p_deltas = {}
        changed = False
        for i, (p_prev, p_curr) in enumerate(zip(prev.players, curr.players)):
            diff = diff_entity(p_prev, p_curr)
            if diff:
                p_deltas[i] = diff
                changed = True
        if changed:
            delta["players_diff"] = p_deltas

    # 3. Enemies - Same logic
    if len(prev.enemies) != len(curr.enemies):
        delta["enemies"] = [asdict_shallow(e) for e in curr.enemies]
    else:
        e_deltas = {}
        changed = False
        for i, (e_prev, e_curr) in enumerate(zip(prev.enemies, curr.enemies)):
            diff = diff_entity(e_prev, e_curr)
            if diff:
                e_deltas[i] = diff
                changed = True
        if changed:
            delta["enemies_diff"] = e_deltas

    # 4. Projectiles - High churn, usually easier to resend full list if count small
    # But we can try diffing if counts match.
    if len(prev.projectiles) != len(curr.projectiles):
        delta["projectiles"] = [asdict_shallow(p) for p in curr.projectiles]
    else:
        proj_deltas = {}
        changed = False
        for i, (p_prev, p_curr) in enumerate(zip(prev.projectiles, curr.projectiles)):
            diff = diff_projectile(p_prev, p_curr)
            if diff:
                proj_deltas[i] = diff
                changed = True
        if changed:
            delta["projectiles_diff"] = proj_deltas

    return delta


def apply_delta(base: SimulationSnapshot, delta: Dict[str, Any]) -> SimulationSnapshot:
    """
    Applies a delta to a base snapshot to produce a new snapshot.
    """
    # Start with a shallow copy of base? No, deep copy needed for lists?
    # Actually, we construct a new SimulationSnapshot.

    # Globals
    tick = delta.get("tick", base.tick)
    score = delta.get("score", base.score)
    dead_count = delta.get("dead_count", base.dead_count)
    transition = delta.get("transition", base.transition)
    rng_state = delta.get("rng_state", base.rng_state)

    # Players
    if "players" in delta:
        players = [EntitySnapshot(**p) for p in delta["players"]]
    else:
        # Copy base players, applying diffs
        players = [copy_entity(p) for p in base.players]
        diffs = delta.get("players_diff", {})
        for idx_str, changes in diffs.items():
            idx = int(idx_str)
            if 0 <= idx < len(players):
                apply_entity_diff(players[idx], changes)

    # Enemies
    if "enemies" in delta:
        enemies = [EntitySnapshot(**e) for e in delta["enemies"]]
    else:
        enemies = [copy_entity(e) for e in base.enemies]
        diffs = delta.get("enemies_diff", {})
        for idx_str, changes in diffs.items():
            idx = int(idx_str)
            if 0 <= idx < len(enemies):
                apply_entity_diff(enemies[idx], changes)

    # Projectiles
    if "projectiles" in delta:
        projectiles = [ProjectileSnapshot(**p) for p in delta["projectiles"]]
    else:
        projectiles = [copy_projectile(p) for p in base.projectiles]
        diffs = delta.get("projectiles_diff", {})
        for idx_str, changes in diffs.items():
            idx = int(idx_str)
            if 0 <= idx < len(projectiles):
                apply_projectile_diff(projectiles[idx], changes)

    return SimulationSnapshot(
        tick=tick,
        rng_state=rng_state,
        players=players,
        enemies=enemies,
        projectiles=projectiles,
        score=score,
        dead_count=dead_count,
        transition=transition,
    )


# --- Helpers ---


def asdict_shallow(obj):
    return obj.__dict__.copy()


def copy_entity(e: EntitySnapshot) -> EntitySnapshot:
    # Dataclass, mutable fields (lists) need copy
    return EntitySnapshot(
        type=e.type,
        id=e.id,
        pos=list(e.pos),
        velocity=list(e.velocity),
        flip=e.flip,
        action=e.action,
        lives=e.lives,
        air_time=e.air_time,
        jumps=e.jumps,
        wall_slide=e.wall_slide,
        dashing=e.dashing,
        shoot_cooldown=e.shoot_cooldown,
        walking=e.walking,
    )


def copy_projectile(p: ProjectileSnapshot) -> ProjectileSnapshot:
    return ProjectileSnapshot(pos=list(p.pos), velocity=p.velocity, timer=p.timer, owner=p.owner)


def diff_entity(a: EntitySnapshot, b: EntitySnapshot) -> Dict[str, Any]:
    d = {}
    if a.pos != b.pos:
        d["pos"] = list(b.pos)  # Always send full vector if changed
    if a.velocity != b.velocity:
        d["velocity"] = list(b.velocity)
    if a.flip != b.flip:
        d["flip"] = b.flip
    if a.action != b.action:
        d["action"] = b.action
    if a.lives != b.lives:
        d["lives"] = b.lives
    if a.air_time != b.air_time:
        d["air_time"] = b.air_time
    if a.jumps != b.jumps:
        d["jumps"] = b.jumps
    if a.wall_slide != b.wall_slide:
        d["wall_slide"] = b.wall_slide
    if a.dashing != b.dashing:
        d["dashing"] = b.dashing
    if a.shoot_cooldown != b.shoot_cooldown:
        d["shoot_cooldown"] = b.shoot_cooldown
    if a.walking != b.walking:
        d["walking"] = b.walking
    return d


def apply_entity_diff(e: EntitySnapshot, diff: Dict[str, Any]):
    for k, v in diff.items():
        setattr(e, k, v)


def diff_projectile(a: ProjectileSnapshot, b: ProjectileSnapshot) -> Dict[str, Any]:
    d = {}
    if a.pos != b.pos:
        d["pos"] = list(b.pos)
    if a.velocity != b.velocity:
        d["velocity"] = b.velocity
    if a.timer != b.timer:
        d["timer"] = b.timer
    # owner usually constant
    return d


def apply_projectile_diff(p: ProjectileSnapshot, diff: Dict[str, Any]):
    for k, v in diff.items():
        setattr(p, k, v)
