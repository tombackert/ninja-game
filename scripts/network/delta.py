from typing import Any, Dict, List
from scripts.snapshot import SimulationSnapshot, EntitySnapshot, ProjectileSnapshot


def compute_delta(prev: SimulationSnapshot, curr: SimulationSnapshot) -> Dict[str, Any]:
    """
    Computes the difference between two snapshots.
    Returns a dictionary containing only changed fields.

    Uses ID-based matching for entities (MP-02) instead of index-based matching.
    This allows proper delta compression even when entities are reordered or
    added/removed dynamically in multiplayer.
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
    if prev.collected != curr.collected:
        delta["collected"] = list(curr.collected)  # Small cumulative ID list

    # 2. Entities (Players) - ID-based matching (MP-02)
    players_delta = compute_entity_list_delta(prev.players, curr.players)
    if players_delta:
        delta.update({"players_" + k: v for k, v in players_delta.items()})

    # 3. Enemies - ID-based matching (MP-02)
    enemies_delta = compute_entity_list_delta(prev.enemies, curr.enemies)
    if enemies_delta:
        delta.update({"enemies_" + k: v for k, v in enemies_delta.items()})

    # 4. Projectiles - ID-based matching (MP-02)
    projectiles_delta = compute_projectile_list_delta(prev.projectiles, curr.projectiles)
    if projectiles_delta:
        delta.update({"projectiles_" + k: v for k, v in projectiles_delta.items()})

    return delta


def compute_entity_list_delta(prev_list: List[EntitySnapshot], curr_list: List[EntitySnapshot]) -> Dict[str, Any]:
    """Compute delta for entity list using ID-based matching."""
    result: Dict[str, Any] = {}

    # Build ID -> entity maps
    prev_by_id = {e.id: e for e in prev_list}
    curr_by_id = {e.id: e for e in curr_list}

    prev_ids = set(prev_by_id.keys())
    curr_ids = set(curr_by_id.keys())

    # Find added, removed, and potentially changed entities
    added_ids = curr_ids - prev_ids
    removed_ids = prev_ids - curr_ids
    common_ids = prev_ids & curr_ids

    # Added entities - send full data
    if added_ids:
        result["added"] = [asdict_shallow(curr_by_id[eid]) for eid in added_ids]

    # Removed entities - send IDs
    if removed_ids:
        result["removed"] = list(removed_ids)

    # Changed entities - send diffs keyed by ID
    changed = {}
    for eid in common_ids:
        diff = diff_entity(prev_by_id[eid], curr_by_id[eid])
        if diff:
            changed[eid] = diff
    if changed:
        result["diff"] = changed

    return result


def compute_projectile_list_delta(
    prev_list: List[ProjectileSnapshot], curr_list: List[ProjectileSnapshot]
) -> Dict[str, Any]:
    """Compute delta for projectile list using ID-based matching."""
    result: Dict[str, Any] = {}

    # Build ID -> projectile maps
    prev_by_id = {p.id: p for p in prev_list}
    curr_by_id = {p.id: p for p in curr_list}

    prev_ids = set(prev_by_id.keys())
    curr_ids = set(curr_by_id.keys())

    # Find added, removed, and potentially changed projectiles
    added_ids = curr_ids - prev_ids
    removed_ids = prev_ids - curr_ids
    common_ids = prev_ids & curr_ids

    # Added projectiles - send full data
    if added_ids:
        result["added"] = [asdict_shallow(curr_by_id[pid]) for pid in added_ids]

    # Removed projectiles - send IDs
    if removed_ids:
        result["removed"] = list(removed_ids)

    # Changed projectiles - send diffs keyed by ID
    changed = {}
    for pid in common_ids:
        diff = diff_projectile(prev_by_id[pid], curr_by_id[pid])
        if diff:
            changed[pid] = diff
    if changed:
        result["diff"] = changed

    return result


def apply_delta(base: SimulationSnapshot, delta: Dict[str, Any]) -> SimulationSnapshot:
    """
    Applies a delta to a base snapshot to produce a new snapshot.

    Handles ID-based entity matching (MP-02) with added/removed/diff keys.
    """
    # Globals
    tick = delta.get("tick", base.tick)
    score = delta.get("score", base.score)
    dead_count = delta.get("dead_count", base.dead_count)
    transition = delta.get("transition", base.transition)
    rng_state = delta.get("rng_state", base.rng_state)
    collected = list(delta.get("collected", base.collected))

    # Players - ID-based delta (MP-02)
    players = apply_entity_list_delta(base.players, delta, "players_")

    # Enemies - ID-based delta (MP-02)
    enemies = apply_entity_list_delta(base.enemies, delta, "enemies_")

    # Projectiles - ID-based delta (MP-02)
    projectiles = apply_projectile_list_delta(base.projectiles, delta, "projectiles_")

    return SimulationSnapshot(
        tick=tick,
        rng_state=rng_state,
        players=players,
        enemies=enemies,
        projectiles=projectiles,
        score=score,
        dead_count=dead_count,
        transition=transition,
        collected=collected,
    )


def apply_entity_list_delta(
    base_list: List[EntitySnapshot], delta: Dict[str, Any], prefix: str
) -> List[EntitySnapshot]:
    """Apply ID-based delta to entity list."""
    # Start with copies of base entities
    by_id = {e.id: copy_entity(e) for e in base_list}

    # Remove entities
    removed_ids = delta.get(prefix + "removed", [])
    for eid in removed_ids:
        by_id.pop(eid, None)

    # Apply diffs to existing entities
    diffs = delta.get(prefix + "diff", {})
    for eid_str, changes in diffs.items():
        eid = int(eid_str) if isinstance(eid_str, str) else eid_str
        if eid in by_id:
            apply_entity_diff(by_id[eid], changes)

    # Add new entities
    added = delta.get(prefix + "added", [])
    for entity_data in added:
        entity = EntitySnapshot(**entity_data)
        by_id[entity.id] = entity

    # Return as list (order by ID for consistency)
    return list(by_id.values())


def apply_projectile_list_delta(
    base_list: List[ProjectileSnapshot], delta: Dict[str, Any], prefix: str
) -> List[ProjectileSnapshot]:
    """Apply ID-based delta to projectile list."""
    # Start with copies of base projectiles
    by_id = {p.id: copy_projectile(p) for p in base_list}

    # Remove projectiles
    removed_ids = delta.get(prefix + "removed", [])
    for pid in removed_ids:
        by_id.pop(pid, None)

    # Apply diffs to existing projectiles
    diffs = delta.get(prefix + "diff", {})
    for pid_str, changes in diffs.items():
        pid = int(pid_str) if isinstance(pid_str, str) else pid_str
        if pid in by_id:
            apply_projectile_diff(by_id[pid], changes)

    # Add new projectiles
    added = delta.get(prefix + "added", [])
    for proj_data in added:
        proj = ProjectileSnapshot(**proj_data)
        by_id[proj.id] = proj

    # Return as list (order by ID for consistency)
    return list(by_id.values())


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
        owner_id=e.owner_id,
        lives=e.lives,
        air_time=e.air_time,
        jumps=e.jumps,
        wall_slide=e.wall_slide,
        dashing=e.dashing,
        shoot_cooldown=e.shoot_cooldown,
        walking=e.walking,
        coins=e.coins,
        ammo=e.ammo,
    )


def copy_projectile(p: ProjectileSnapshot) -> ProjectileSnapshot:
    return ProjectileSnapshot(
        id=p.id,
        pos=list(p.pos),
        velocity=p.velocity,
        timer=p.timer,
        owner=p.owner,
        owner_id=p.owner_id,
    )


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
    if a.owner_id != b.owner_id:
        d["owner_id"] = b.owner_id
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
    if a.coins != b.coins:
        d["coins"] = b.coins
    if a.ammo != b.ammo:
        d["ammo"] = b.ammo
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
    if a.owner_id != b.owner_id:
        d["owner_id"] = b.owner_id
    # owner (string) usually constant
    return d


def apply_projectile_diff(p: ProjectileSnapshot, diff: Dict[str, Any]):
    for k, v in diff.items():
        setattr(p, k, v)
