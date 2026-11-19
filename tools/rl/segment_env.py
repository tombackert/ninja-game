"""A gym-style environment for one stretch of a level's planned route.

The planner (tools/worlds) finds a frame-exact route through every level, but
it plans without enemies: what bullets, stars and chasers cost a player is the
one thing the difficulty model does not see. This environment hands that part
to a learned policy:

- An episode starts where the planned route enters waypoint `start` and ends
  when the player reaches the stretch's last waypoint (success), loses a life
  or falls (failure), or runs out of time (`timeout`). The last waypoint is a
  fixed point the planner takes over from: `start + span - 1`, or the first
  waypoint after it that the player stands on (so a stretch through a maze
  of mid-air waypoints plays on to its exit). `handoff()` checks that the
  planner gets from where the agent arrived to the spot the route arrives at,
  from where the level's route goes on.
- The start states come from replaying the route's inputs in the real game
  with the enemies taken out; the replay hits every waypoint of the plan, so a
  start state is one a player who follows the route really is in.
- Enemies are live and seeded per episode. Before the player is put at the
  start, the world runs a random number of frames so turrets and walkers are
  met at different phases.
- Human limits: the agent decides every `action_repeat` frames and sees the
  world as it was `reaction_delay` frames ago. Jump and dash are taps on the
  first frame of a decision, as a key press is. No gear and no weapon (the
  player's own equipment from settings is ignored), and no dash wall climb:
  a jump that would be one is dropped (players almost never use it, see
  docs/level-building-findings.md section 4).

Besides moves, the agent has one action that follows the route (with
`route_action`): the planner knows the geometry, so what is left to learn is
when to leave the route (dodging, waiting, killing). The route is planned
once for the stretch without the dash wall climb, and around it a guide
(tools/rl/guide.py): the planner's move for states off the route, and by a
flame jet for each point of its beat (both cached in tools/rl/cache/, built
once per stretch). The action plays the route's next input while the player
is exactly on it, else the guide's (by a flame, the guide's way for the beat
first), else the route's input at the nearest point. Near an enemy that hurts
on touch, an enemy shot or a flame, it looks LOOK frames ahead along that way,
with the enemies where they will be as the player saw them `reaction_delay`
frames ago (a patrol walks on by its own rules, a jumper hops by its own,
a shot flies on, and a gunner whose walk ends or a turret whose cooldown
runs out fires the shot a player expects): if the way runs into one, it
waits, dashes through, jumps or backs off for a decision, whichever keeps it
clear. A way found clear is trusted for RECHECK frames while the player
follows it and nothing new shows up. As a player would, it also kills an
enemy on the way on that is a danger (one that hurts on touch and that the
way meets, or an armed one that has the player in sight): a dash at it or a
jump onto it, if that kills it, the way after it runs into nothing and it
leads back to the route (see `_attack_move`). No reward is paid for a kill.
Nothing is planned during an episode: the planner costs milliseconds per
call, the simulation microseconds per frame.

The observation is a flat float vector (see `obs_size`): the player's state,
the vector to the next waypoint, the route's next inputs and where it goes,
the nearest flame jet's beat, a local grid of solid, water and deadly
tiles, and the nearest enemies and hostile projectiles; of the last STACK
decisions (the grid only of the newest), with the agent's own last moves. Reward: progress
along the route (the furthest of its points the player has come near), a
bonus per waypoint and at the goal, a penalty for a lost life or for running
out of time.

Training starts a share of its episodes (`spread`) at a later waypoint of
the stretch, where the route arrives there, mostly at those from which the
agent fails most: a long stretch is learnt in all its parts at once, not only
as far as the agent gets from its start, and most where it is hardest.

Usage:
    env = SegmentEnv(level=27, start=10, span=4)
    obs = env.reset(seed=0)
    obs, reward, done, info = env.step(2)
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import deque
from dataclasses import dataclass

if os.environ.get("NINJA_RL_WINDOW") != "1":  # tools/rl/watch.py opens a real window
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402

import pygame  # noqa: E402

from game import Game  # noqa: E402
from scripts.ai.behaviors import FEET, PROBE, _spikes_ahead, _zone_ahead, throw_velocity  # noqa: E402
from scripts.constants import (  # noqa: E402
    DASH_MIN_ACTIVE_ABS,
    GRAVITY_ACCEL,
    MAX_FALL_SPEED,
    STOMP_BOUNCE_VELOCITY,
    STOMP_MARGIN,
)
from scripts.hazards import FLAME_WARN  # noqa: E402
from scripts.rng_service import RNGService  # noqa: E402
from scripts.settings import settings  # noqa: E402
from tools.rl import guide  # noqa: E402
from tools.worlds import physics as ph  # noqa: E402
from tools.worlds.planner import Waypoint, dash_climb_press, plan_segment  # noqa: E402
from tools.worlds.route import PLANS_DIR, load_plan  # noqa: E402

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_VERSION = 2
FIXES = {"field": True, "water_key": True, "wait": True}
GUIDE_ROUNDS = 3  # rounds (at most) of planning from the states the guide did not know ...
MISS_STOP = True  # plans from them end where they reach the route (see guide._Reach)
GUIDE_GAIN = 0.03  # ... while the last one cut the share of frames it knew no way on by this much
ATTACK_ROUNDS = 2  # rounds (at most) of planning from where the way after an attack gets lost
TIMED_LOOK = 60  # frames the guide's blind way is checked against the flames, for a timed plan
STALL = 60  # frames without progress along the route after which the state counts as missed too
# Planning the stretch once (cached): the route builder's tries, none with the
# dash wall climb, in the agent's own decisions (a move held 4 or 8 frames)
ROUTE_TRIES = (
    {"weight": 5.0, "max_expand": 8000, "durations": guide.DURATIONS},
    {"weight": 5.0, "max_expand": 20000, "durations": guide.DURATIONS, **FIXES},
    {"weight": 2.0, "max_expand": 120000, "durations": guide.DURATIONS, **FIXES},
)

PW, PH = 8, 15  # player hitbox (px), as the planner's physics
# The route action's look out for enemies that hurt on touch: how far ahead it
# looks (frames) along its way, and from how far (px) it watches one
LOOK = 20
LOOK_HOP = 32  # ... while a jumper is near
ATTACK_LOOK = 72  # frames an attack on an enemy is looked ahead (a jump onto one at the same height takes ~62)
WATCH = 96
RECHECK = 8  # frames a way found clear stays trusted while the player follows it and nothing new shows
REACH = (96, 24)  # how far off (px, sideways and up or down) an enemy is worth a dash or a jump at it
BEHIND = 0  # ... and how far back from the way on (px): going back costs the dash the way on needs
REJOIN = 240  # frames the way after an attack has to get back onto the route or to the next waypoint
RETRY = 12  # frames before an enemy no attack worked on is looked at again
GRID_W, GRID_H = 15, 11  # local tile grid around the player (tiles)
N_ENEMIES = 5
N_PROJECTILES = 5
SELF_FEATURES = 10
GOAL_FEATURES = 4
ENEMY_FEATURES = 6
PROJ_FEATURES = 5
ROUTE_FEATURES = 12
ROUTE_AHEAD = (8, 16, 32)  # frames ahead of the nearest point whose position the agent sees
FLAME_FEATURES = 6
STACK = 4  # decisions the agent sees at once (the newest grid, the rest of each)
SCALE = 256.0  # px that map to 1.0 in relative positions
# A flame jet's cells in the deadly layer, as a player sees them: out, flickering
# (it fires in FLAME_WARN frames), burning
FLAME_LEVEL = {"off": 0.3, "warn": 0.6, "burn": 1.0}

# The agent's moves: every key a player holds for a decision (left, right or
# neither, with jump and dash pressed on its first frame), the planner's moves
# too; and with `route_action`, one more: the route action (see the module doc)
ROUTE = None
ACTIONS = [(m, j, d) for d in (False, True) for j in (False, True) for m in (0, -1, 1)]

REWARD = {
    "progress": 0.02,  # per frame of the route the player gets further along (see _progress)
    "waypoint": 1.0,
    "goal": 10.0,
    "death": -5.0,
    "timeout": -5.0,  # as bad as a death: standing still is no way through
    "time": -0.002,  # per frame
}


GRID_AT = SELF_FEATURES + GOAL_FEATURES + ROUTE_FEATURES + FLAME_FEATURES  # where the grid starts
GRID_SIZE = 3 * GRID_W * GRID_H


def frame_size() -> int:
    """Floats of one decision's observation."""
    return GRID_AT + GRID_SIZE + N_ENEMIES * ENEMY_FEATURES + N_PROJECTILES * PROJ_FEATURES


def obs_size(stack: int = STACK, n_actions: int = 12) -> int:
    """Floats the agent sees: the newest grid, the rest of the last `stack`
    decisions' observations (newest first), and its own last `stack` moves
    (one-hot, newest first: a player knows what they pressed, without delay)."""
    return GRID_SIZE + stack * (frame_size() - GRID_SIZE) + stack * n_actions


@dataclass
class StartState:
    """The player's state where the route enters a waypoint."""

    frame: int  # frames into the plan
    pos: tuple
    velocity: tuple
    flip: bool
    air_time: int
    jumps: int
    dashing: int
    wall_slide: bool
    breath: int
    swim_cooldown: int


def _inputs(m: int, jump: bool, dash: bool) -> list:
    names = []
    if m < 0:
        names.append("left")
    elif m > 0:
        names.append("right")
    if jump:
        names.append("jump")
    if dash:
        names.append("dash")
    return names


def _no_items() -> None:
    """Play without gear or weapon, whatever the player has equipped (the
    Lucky Charm adds a life on level load, Moon Boots change the jump). Only
    the in-memory settings change; nothing is saved."""
    settings.selected_gear = 0
    settings.selected_weapon = 0


_TERRAIN: dict = {}


def terrain(level: int):
    """The planner's physics terrain of `level` (tools/worlds/physics.py)."""
    if level not in _TERRAIN:
        with open(os.path.join("data", "maps", f"{level}.json")) as f:
            _TERRAIN[level] = ph.terrain_from_map(json.load(f)["map_data"])
    return _TERRAIN[level]


def phys_state(p) -> tuple:
    """The game player's state as the planner's physics tuple."""
    return (
        p.pos[0],
        p.pos[1],
        p.velocity[0],
        p.velocity[1],
        p.air_time,
        p.jumps,
        p.wall_slide,
        p.dashing,
        p.flip,
        p.last_movement[0],
        p.breath,
        p.swim_cooldown,
    )


def set_phys_state(p, s: tuple) -> None:
    p.pos = [s[ph.X], s[ph.Y]]
    p.velocity = [s[ph.VX], s[ph.VY]]
    p.air_time = s[ph.AIR]
    p.jumps = s[ph.JUMPS]
    p.wall_slide = s[ph.WALL]
    p.dashing = s[ph.DASH]
    p.flip = s[ph.FLIP]
    p.last_movement = (s[ph.LASTM], 0)
    p.breath = s[ph.BREATH]
    p.swim_cooldown = s[ph.SWIM]


def plan_start(level: int, start: int) -> tuple[tuple, bool]:
    """Physics state (and on-ground flag) where the stored route enters
    segment `start`: the stored inputs replayed with the planner's physics,
    which matches the game frame for frame."""
    plan, starts = route_starts(level)
    solids = terrain(level)
    s, down = ph.spawn_state(*plan["spawn"]), True
    for m, j, d in plan["frame_list"][: starts[start].frame]:
        s, down, _dead = ph.apply_frame(s, m, j, d, solids)
    return s, down


def _cache_key(level: int) -> str:
    with open(os.path.join(PLANS_DIR, f"{level}.json"), "rb") as f:
        return f"{CACHE_VERSION}:{hashlib.sha1(f.read()).hexdigest()}"


def human_route(level: int, start: int, span: int, log=print) -> list:
    """Inputs from the start of segment `start` through its next `span`
    waypoints, planned without the dash wall climb, in the agent's decisions.
    Cached in CACHE_DIR, keyed by the stored plan, so a re-planned level is
    planned again."""
    plan, _starts = route_starts(level)
    key = _cache_key(level)
    path = os.path.join(CACHE_DIR, f"{level}_{start}_{span}.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if data["key"] == key:
            return [(m, bool(j), bool(d)) for m, j, d in data["frames"]]
    except (OSError, ValueError, KeyError):
        pass
    solids = terrain(level)
    s, down = plan_start(level, start)
    frames: list = []
    for wp in plan["waypoints"][start : start + span]:
        for kw in ROUTE_TRIES:
            res = plan_segment(s, wp, solids, kill_y=solids.kill_y, start_down=down, no_dash_climb=True, **kw)
            if res.ok:
                break
        if not res.ok:
            raise RuntimeError(f"level {level}: waypoint '{wp.label}' is not reachable without the dash wall climb")
        log(f"[route] level {level} '{wp.label}': {len(res.frames)} frames ({res.expanded:,} nodes)")
        for m, j, d in res.frames:
            s, down, _dead = ph.apply_frame(s, m, j, d, solids)
        frames.extend(res.frames)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"key": key, "frames": [[m, int(j), int(d)] for m, j, d in frames]}, f)
    return frames


def stretch_guide(level: int, start: int, span: int, env=None, log=print) -> guide.Guide:
    """The guide of the stretch (tools/rl/guide.py), cached like its route."""
    path = os.path.join(CACHE_DIR, f"{level}_{start}_{span}_guide.json")
    key = _cache_key(level)
    table = guide.load(path, key)
    if table is not None:
        return table
    if env is None or env.actions[-1] is not ROUTE:  # the rounds below play the route action
        env = SegmentEnv(level, start, span, use_guide=False, route_action=True)
    log(f"[guide] level {level} segments {start}-{env.end - 1}: planning from states around the route ...")
    if not env._loaded:
        env.reset(0)
    flames = guide.Flames.from_hazards(env.game.hazards) if getattr(env.game, "hazards", None) else None
    flames = flames if flames is not None and flames.jets else None
    with guide.planners(env.solids, env.waypoints):
        anchors: set = set()
        spine: set = set()
        table = guide.build(
            env.solids,
            env.waypoints,
            env.start_state,
            env.route_frames,
            env.route_wp_frame,
            flames,
            log=log,
            anchors=anchors,
            spine=spine,
        )
        last = 1.0
        for r in range(GUIDE_ROUNDS):
            env.guide = guide.Guide(list(table.values()), flames)
            misses, timed, rate = _guide_misses(env, r)
            if last - rate < GUIDE_GAIN:
                log(f"[guide] {len(table):,} states, no way known on {100 * rate:.1f}% of the frames: done")
                break
            last = rate
            log(
                f"[guide] {len(table):,} states, round {r + 1}: no way known on {100 * rate:.1f}% of the frames;"
                f" planning from {len(misses):,} states" + (f" ({len(timed):,} by a flame)" if timed else "")
            )
            # They end on the route, not on another plan: answers near the end
            # of one plan and the middle of another can go round in a loop
            plans = guide.plan_from(
                env.solids, env.waypoints, misses, anchors=set(spine), stop=MISS_STOP, max_expand=guide.MISS_EXPAND
            )
            for k, v in plans.items():
                table.setdefault(k, v)
            if timed:
                plans = guide.plan_from(
                    env.solids, env.waypoints, timed, flames=flames, anchors=anchors, max_expand=guide.MISS_EXPAND
                )
                for k, v in plans.items():
                    table.setdefault(k, v)
        # An attack on an enemy (see SegmentEnv._attack_move) leaves the
        # route where the rounds above, without enemies, never go: plan from
        # the states the way after one gets lost in, so it leads back
        for r in range(ATTACK_ROUNDS):
            env.guide = guide.Guide(list(table.values()), flames)
            lost = _attack_misses(env, r)
            if not lost:
                break
            log(f"[guide] {len(table):,} states, attack round {r + 1}: planning from {len(lost):,} states")
            plans = guide.plan_from(
                env.solids, env.waypoints, lost, anchors=set(spine), stop=MISS_STOP, max_expand=guide.MISS_EXPAND
            )
            for k, v in plans.items():
                table.setdefault(k, v)
    guide.save(path, key, table, flames)
    log(f"[guide] {len(table):,} states")
    return guide.load(path, key)


def _guide_misses(
    env, round_: int, episodes: int = 48, cap: int = 2000, timed_cap: int = 150
) -> tuple[list, list, float]:
    """States the route action meets but the guide does not know (or where
    it makes no progress along the route for STALL frames), from
    episodes of the route action with random detours, the world emptied of
    enemies (and in every other episode of flames too): (states it knows no
    way on from, states by a flame it knows no timed way on from, the share
    of the route action's frames it knew no way on)."""
    rng = random.Random(round_)
    route = env.n_actions - 1
    misses: dict = {}
    timed: dict = {}
    unknown = played = 0
    for e in range(episodes):
        env.reset(seed=round_ * 1000 + e)
        flames = e % 2 == 1 and env.guide.flames is not None
        if flames:
            env.game.enemies.clear()
        else:
            env.strip_dangers()
        rate = (0.05, 0.15, 0.3)[e % 3]
        done, found = False, 0
        best, stalled = env.best, 0
        while not done and found < 60:
            before, timed_before = env.unguided, env.untimed
            _obs, _r, done, _info = env.step(route if rng.random() >= rate else rng.randrange(route))
            if env.next_wp >= len(env.waypoints):
                continue
            p = env.game.player
            s, down = phys_state(p), bool(p.collisions["down"])
            stalled = 0 if env.best > best else stalled + env.action_repeat
            best = env.best
            if env.unguided > before or stalled >= STALL:
                # (stalled: the guide's answers there, each from a state near
                # this one, may go round in a loop; a plan from it leads on)
                misses.setdefault(guide.key(s, down, env.next_wp), (s, down, env.next_wp, 0))
                found += 1
                stalled = 0
            b = env.guide.beat(s, env.game.hazards.clock) if flames else None
            tick = env.game.hazards.clock
            # only where the guide's way, blind to the beat, burns now
            if b is not None and env.untimed > timed_before and env._burns(s, down, tick, frames=TIMED_LOOK):
                timed.setdefault(guide.key(s, down, env.next_wp) + b, (s, down, env.next_wp, tick))
                found += 1
        unknown += env.unguided
        played += env.on_route + env.guided + env.unguided
    out = []
    for found, n in ((misses, cap), (timed, timed_cap)):  # (plans by a flame cost ten times more)
        starts = list(found.values())
        rng.shuffle(starts)
        out.append(starts[:n])
    return out[0], out[1], unknown / max(1, played)


def _attack_misses(env, round_: int, episodes: int = 32, cap: int = 1000) -> list:
    """States the way after an attack gets to and the guide knows no way on
    from (see SegmentEnv._lost), from episodes of the route action with the
    enemies in."""
    rng = random.Random(round_)
    env.attack_misses = {}
    try:
        for e in range(episodes):
            env.reset(seed=50_000 + round_ * 1000 + e)
            done = False
            while not done and len(env.attack_misses) < cap:
                _obs, _r, done, _info = env.step(env.n_actions - 1)
        starts = list(env.attack_misses.values())
    finally:
        env.attack_misses = None
    rng.shuffle(starts)
    return starts[:cap]


def handoff_end(waypoints: list, start: int, span: int) -> int:
    """End (exclusive) of the stretch that starts at segment `start` and runs
    at least `span` waypoints: on to the first waypoint the player stands on,
    a fixed point the planner can take over from."""
    end = min(start + max(1, span), len(waypoints))
    while end < len(waypoints) and not waypoints[end - 1].ground:
        end += 1
    return end


def _capture(p, frame: int) -> StartState:
    return StartState(
        frame,
        tuple(p.pos),
        tuple(p.velocity),
        bool(p.flip),
        p.air_time,
        p.jumps,
        p.dashing,
        bool(p.wall_slide),
        getattr(p, "breath", 0),
        getattr(p, "swim_cooldown", 0),
    )


_START_CACHE: dict = {}


def route_starts(level: int) -> tuple[dict, list]:
    """The plan of `level` and the player's state at the start of every
    segment (index i: where segment i, towards waypoint i, begins), found by
    replaying the plan in the real game without enemies."""
    if level in _START_CACHE:
        return _START_CACHE[level]
    plan = load_plan(level)
    _no_items()
    g = Game(fullscreen=False)
    RNGService.get().seed(0)
    g.load_level(level)
    g.enemies.clear()
    p = g.player
    begins = {start: i for i, (start, _n) in enumerate(plan["segments"])}
    starts: list = [None] * len(plan["segments"])
    for f, (m, jump, dash) in enumerate(plan["frame_list"]):
        if f in begins:
            starts[begins[f]] = _capture(p, f)
        g.apply_inputs(_inputs(m, jump, dash))
        g.step()
        if g.dead:
            raise RuntimeError(f"level {level}: the plan's replay dies at frame {f}")
    missing = [i for i, s in enumerate(starts) if s is None]
    if missing:
        raise RuntimeError(f"level {level}: no start state for segments {missing}")
    _START_CACHE[level] = (plan, starts)
    return plan, starts


def segment_threats(level: int, margin_x: int = 12, margin_y: int = 6) -> list:
    """Per segment: (label, frames, enemies) where `enemies` counts the enemies
    that spawn within `margin_x` x `margin_y` tiles of the box the planned
    route sweeps through in that segment. Shows where the fights are."""
    plan, starts = route_starts(level)
    g = Game(fullscreen=False)
    RNGService.get().seed(0)
    g.load_level(level)
    ts = g.tilemap.tile_size
    spawns = [(e.pos[0] + 4, e.pos[1] + 7) for e in g.enemies]
    out = []
    for i, (wp, (start, n)) in enumerate(zip(plan["waypoints"], plan["segments"])):
        a = starts[i].pos
        x0 = min(a[0], wp.x0 * ts) - margin_x * ts
        x1 = max(a[0], (wp.x1 + 1) * ts) + margin_x * ts
        y0 = min(a[1], wp.y0 * ts) - margin_y * ts
        y1 = max(a[1], (wp.y1 + 1) * ts) + margin_y * ts
        count = sum(1 for x, y in spawns if x0 <= x <= x1 and y0 <= y <= y1)
        out.append((wp.label, n, count))
    return out


class _Path(list):
    """Where an enemy or a shot is at frames 1..LOOK from now (see
    `SegmentEnv._paths`), and whose it is: `owner`, the enemy (a shot's: the
    one that fires it; None: not known); `fired`, the frame from now an
    expected shot leaves the gun (0: it flies already); `hurts`, False for
    the body of an armed enemy, which does not hurt on touch but dies to a
    dash or a stomp as any enemy does."""

    __slots__ = ("owner", "fired", "hurts")

    def __init__(self, items, owner=None, fired: int = 0, hurts: bool = True):
        super().__init__(items)
        self.owner, self.fired, self.hurts = owner, fired, hurts


class _Hopper:
    """A jumper's hops ahead of time, by its own rules (scripts/ai/behaviors.py,
    JumperPolicy): on the ground it waits out its cooldown, then hops
    forward; in the air it keeps going forward and falls. Where it would
    turn before a hop (a gap, a wall) is not foreseen."""

    def __init__(self, enemy, x: float, y: float, flip: bool, vy: float, cooldown: int):
        self.tm = enemy.game.tilemap
        self.kind = enemy.kind
        self.size = enemy.size
        self.pos = [x, y]
        self.flip, self.vy, self.cooldown = flip, vy, cooldown
        w, h = self.size
        self.ground = vy >= 0 and bool(self.tm.solid_check((x + w // 2, y + h + 1)))

    def step(self) -> None:
        kind = self.kind
        if self.ground:  # waits out its cooldown, then hops
            self.cooldown = max(0, self.cooldown - 1)
            if self.cooldown:
                return
            self.vy, self.cooldown, self.ground = kind.hop_velocity, kind.hop_period, False
        w, h = self.size
        x = self.pos[0] + (-kind.speed if self.flip else kind.speed)
        y = self.pos[1] + self.vy
        if self.vy > 0 and self.tm.solid_check((x + w // 2, y + h)):
            y = (int(y + h) // ph.TS) * ph.TS - h  # lands
            self.vy, self.ground = 0.0, True
        self.vy = min(self.vy + GRAVITY_ACCEL, MAX_FALL_SPEED)
        self.pos = [x, y]


class _Walker:
    """A patrol's walk ahead of time, by its own rules
    (scripts/ai/behaviors.py, _walk): on along its platform, turning at walls,
    edges, spikes, flames and start zones."""

    def __init__(self, enemy, x: float, y: float, flip: bool):
        self.game = enemy.game
        self.kind = enemy.kind
        self.size = enemy.size
        self.pos = [x, y]
        self.flip = flip

    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.pos[0], self.pos[1], self.size[0], self.size[1])

    def step(self) -> None:
        tm = self.game.tilemap
        r = self.rect()
        if tm.solid_check((r.centerx + (-PROBE if self.flip else PROBE), self.pos[1] + FEET)):
            wall = tm.solid_check((r.left - 1 if self.flip else r.right, r.centery))
            if wall or _spikes_ahead(self, tm) or _zone_ahead(self):
                self.flip = not self.flip
            else:
                self.pos[0] += -self.kind.speed if self.flip else self.kind.speed
        else:
            self.flip = not self.flip


class SegmentEnv:
    def __init__(
        self,
        level: int,
        start: int,
        span: int = 3,
        action_repeat: int = 4,
        reaction_delay: int = 12,
        warmup: int = 120,
        timeout_factor: float = 3.0,
        reward: dict | None = None,
        spread: float = 0.0,
        use_guide: bool = True,
        route_action: bool = False,
        stack: int = STACK,
    ):
        self.level = level
        self.plan, self.starts = route_starts(level)
        n = len(self.plan["segments"])
        if not 0 <= start < n:
            raise ValueError(f"level {level} has segments 0-{n - 1}")
        self.start = start
        self.end = handoff_end(self.plan["waypoints"], start, span)  # exclusive: waypoints start .. end-1
        self.waypoints = self.plan["waypoints"][start : self.end]
        self.solids = terrain(level)
        # The stretch's own route (no dash wall climb) and the state before each of its frames
        self.start_state, _down = plan_start(level, start)
        self.span = self.end - start
        self.route_frames = human_route(level, start, self.span)
        states = [self.start_state]
        for m, j, d in self.route_frames:
            states.append(ph.apply_frame(states[-1], m, j, d, self.solids)[0])
        self.route_states = states
        self.route_trace = np.array([st[:4] for st in states], np.float32)
        self._route_at: dict = {}  # state -> first frame of the route in it
        for i, st in enumerate(states[:-1]):
            self._route_at.setdefault(st, i)
        # Frame of the route at which it reaches each waypoint
        self.route_wp_frame = []
        down, k = True, 0
        for i, st in enumerate(states):
            if i:
                down = ph.apply_frame(states[i - 1], *self.route_frames[i - 1], self.solids)[1]
            while k < len(self.waypoints) and self.waypoints[k].contains(st, down):
                self.route_wp_frame.append(i)
                k += 1
        self.route_wp_frame += [len(states) - 1] * (len(self.waypoints) - k)
        self.plan_frames = len(self.route_frames)
        self.timeout_factor = timeout_factor
        self.timeout = int(self.plan_frames * timeout_factor) + 120
        self.spread = spread
        self._starts_seen = [[0, 0] for _ in self.waypoints]  # per start waypoint: episodes, goals
        self._first_wp = 0
        self.guide = None
        self.action_repeat = max(1, action_repeat)
        self.reaction_delay = max(0, reaction_delay)
        self.warmup = max(0, warmup)
        self.reward_cfg = dict(REWARD, **(reward or {}))
        self.actions = ACTIONS + ([ROUTE] if route_action else [])
        self.n_actions = len(self.actions)
        self.stack = max(1, stack)
        self.obs_size = obs_size(self.stack, self.n_actions)
        self._stacked: deque = deque(maxlen=self.stack)
        self._moves: deque = deque(maxlen=self.stack)  # the agent's own last actions
        _no_items()
        self.game = Game(fullscreen=False)
        self.on_frame = None  # called after every simulated frame (watch.py draws it)
        self._loaded = False
        self._layers = None
        # (frame, observation) of the frames a later decision will see
        self._history: deque = deque()
        self._area = None
        # The touch-hurting enemies of the last frames (the route action sees
        # them `reaction_delay` frames late) and the rest of a dodge
        self._walkers: deque = deque(maxlen=self.reaction_delay + 2)
        self._dodge: deque = deque()
        self.look = True  # the route action's look ahead (off: it follows the way blind)
        self.expect_shots = True  # it also counts the shots it expects (see _expected_shots)
        self.attack = True  # it kills an enemy in the way when that is safe (see _attack_move)
        self.attack_misses: dict | None = None  # while the guide is built: where an attack's way got lost
        self._memo: dict = {}  # the guide's moves met while looking ahead (see _hits) ...
        self._clear = (-1, None, {})  # the way last found clear: (until frame, threats, states on it by frame)
        self._tried: dict = {}  # enemy -> frame an attack on it was last looked for in vain
        self._rejoined: dict = {}  # (state, down, waypoint, tick) -> whether the guide's way gets back (_rejoins)
        self._memo_by = None  # the guide these two are of
        if use_guide:
            self.guide = stretch_guide(level, start, self.span, env=self)

    # --- episode -----------------------------------------------------------------
    def reset(self, seed: int | None = None, from_wp: int | None = None) -> np.ndarray:
        """A new episode. `from_wp` starts it where the route arrives at that
        waypoint of the stretch (0: the stretch's start); otherwise training
        picks one for a `spread` share of its episodes."""
        rng = random.Random(seed)
        RNGService.get().seed(rng.randrange(2**31))
        _no_items()
        g = self.game
        g.load_level(self.level, respawn=self._loaded)
        self._loaded = True
        if self._layers is None:
            self._build_layers()
            self._area = self._segment_area()
        # Enemies far from this stretch play no part in it: leave them out, the
        # simulation costs about 30 us per enemy and frame
        x0, y0, x1, y1 = self._area
        g.enemies[:] = [e for e in g.enemies if x0 <= e.pos[0] <= x1 and y0 <= e.pos[1] <= y1]
        # ... and so are coins and ammo (each animates every frame)
        for items in (g.cm.coin_list, getattr(g.cm, "ammo_pickups", [])):
            items[:] = [c for c in items if x0 <= c.pos[0] <= x1 and y0 <= c.pos[1] <= y1]
        self.kills = 0  # enemies the player killed (a dash through one or a stomp)
        for e in g.enemies:
            self._count_kills(e)
        # Advance the world with the player standing in the safe start zone
        for _ in range(rng.randrange(self.warmup + 1)):
            g.apply_inputs([])
            g.step()
        p = g.player
        # Where the episode starts: the stretch's start, or (training) the
        # route's arrival at one of its waypoints
        first_wp = from_wp or 0
        if from_wp is None and self.spread > 0 and len(self.waypoints) > 1 and rng.random() < self.spread:
            # Mostly where the agent fails: by the share of the episodes from
            # each waypoint that did not reach the goal (a little for every one)
            weights = [1.1 - goals / (tries + 1) for tries, goals in self._starts_seen[1:]]
            first_wp = 1 + rng.choices(range(len(weights)), weights)[0]
        self._first_wp = first_wp
        k = self.route_wp_frame[first_wp - 1] if first_wp else 0
        set_phys_state(p, self.route_states[k])
        p.collisions["down"] = k == 0 or self.waypoints[first_wp - 1].ground
        g.projectiles.clear()
        g.transition = 0  # no fade-in: an episode starts mid-level (only the renderer reads it)
        self.lives = p.lives
        self.frames = 0
        self.next_wp = first_wp
        self.route_idx = k  # frame of the stretch's route the player was last on
        self.best = k  # furthest frame of the route the player has come near
        # route-action frames on the route / guided back / neither (nearest point)
        self.on_route = self.guided = self.unguided = 0
        self.untimed = 0  # route-action frames by a flame the guide had no timed way for
        self.dodged = 0  # route-action decisions that left the way for a walker
        self.attacked = 0  # route-action decisions that went for an enemy (see _attack_move)
        self._dodge.clear()
        if self._memo_by is not self.guide:  # what the guide says stays true while it is the same
            self._memo, self._rejoined, self._memo_by = {}, {}, self.guide
        self._clear = (-1, None, {})
        self._tried.clear()
        self._walkers.clear()
        self._walkers.append(self._walker_snapshot())
        self.timeout = int((self.plan_frames - k) * self.timeout_factor) + 120
        self.done = False
        self._history.clear()
        self._history.append((-(10**9), self._observe()))
        self._stacked.clear()
        self._moves.clear()
        self._moves.extend([-1] * self.stack)
        return self._seen()

    def _count_kills(self, enemy) -> None:
        """Count it in `kills` when the player kills `enemy` (Enemy.die)."""
        die = enemy.die

        def counted(killer=None):
            if killer is self.game.player:
                self.kills += 1
            return die(killer)

        enemy.die = counted

    def step(self, action: int):
        if self.done:
            raise RuntimeError("step() after the episode ended; call reset()")
        cfg = self.reward_cfg
        g, p = self.game, self.game.player
        route = self.actions[action] is ROUTE
        self._moves.appendleft(action)
        if not route:
            self._dodge.clear()
        reward = 0.0
        outcome = None
        self.route_idx = max(self.route_idx, self.best)
        for k in range(self.action_repeat):
            if route:
                m, jump, dash = self._route_move()
            else:
                m, jump, dash = self.actions[action]
                jump, dash = jump and k == 0, dash and k == 0
                if jump and dash_climb_press(phys_state(p), dash, self.solids):
                    jump = False  # no dash wall climb
            g.apply_inputs(_inputs(m, jump, dash))
            g.step()
            self.frames += 1
            self._walkers.append(self._walker_snapshot())
            if self.on_frame is not None:
                self.on_frame()
            reward += cfg["time"]
            if (self.frames + self.reaction_delay) % self.action_repeat == 0:
                self._history.append((self.frames, self._observe()))
            if g.dead or p.lives < self.lives:
                reward += cfg["death"]
                outcome = "death"
                break
            reward += cfg["progress"] * self._progress()
            while self.next_wp < len(self.waypoints) and self._inside(self.waypoints[self.next_wp]):
                self.next_wp += 1
                reward += cfg["waypoint"]
            if self.next_wp >= len(self.waypoints):
                reward += cfg["goal"]
                outcome = "goal"
                break
            if self.frames >= self.timeout:
                reward += cfg["timeout"]
                outcome = "timeout"
                break
        self.done = outcome is not None
        if self.done:
            seen = self._starts_seen[self._first_wp]
            seen[0] += 1
            seen[1] += outcome == "goal"
        info = {
            "outcome": outcome,
            "frames": self.frames,
            "waypoints": self.next_wp,
            "on_route": self.on_route,
            "guided": self.guided,
            "unguided": self.unguided,
            "dodged": self.dodged,
            "attacked": self.attacked,
            "kills": self.kills,
        }
        return (None if self.done else self._seen()), reward, self.done, info

    def run_plan(self, seed: int | None = None) -> dict:
        """One episode of the planned route's own inputs, frame by frame and
        blind to the enemies: what the route costs a player who does not
        react. Same start and seeding as `reset(seed)`."""
        self.reset(seed)
        g, p = self.game, self.game.player
        outcome = "timeout"
        for m, jump, dash in self.route_frames:
            g.apply_inputs(_inputs(m, jump, dash))
            g.step()
            self.frames += 1
            if self.on_frame is not None:
                self.on_frame()
            if g.dead or p.lives < self.lives:
                outcome = "death"
                break
            while self.next_wp < len(self.waypoints) and self._inside(self.waypoints[self.next_wp]):
                self.next_wp += 1
            if self.next_wp >= len(self.waypoints):
                outcome = "goal"
                break
        self.done = True
        return {"outcome": outcome, "frames": self.frames, "waypoints": self.next_wp, "kills": self.kills}

    def _seen(self) -> np.ndarray:
        """The world as the agent sees it now: `reaction_delay` frames ago,
        with the decisions before (STACK)."""
        h = self._history
        while len(h) > 1 and h[1][0] <= self.frames - self.reaction_delay:
            h.popleft()
        now = h[0][1]
        rest = np.concatenate([now[:GRID_AT], now[GRID_AT + GRID_SIZE :]])
        if not self._stacked:
            self._stacked.extend([rest] * self.stack)
        else:
            self._stacked.appendleft(rest)
        moves = np.zeros((self.stack, self.n_actions), np.float32)
        for i, a in enumerate(self._moves):
            if a >= 0:
                moves[i, a] = 1.0
        return np.concatenate([now[GRID_AT : GRID_AT + GRID_SIZE], *self._stacked, moves.ravel()])

    def teacher(self) -> int:
        """The planner's move from where the player is now, as one of the
        agent's actions (-1: the planner knows none). The planner's next
        `action_repeat` frames (the guide's, by a flame its way for the beat;
        else the route's own while the player is exactly on it) are played in
        the physics replica, then each action of the agent for as many frames:
        the one that ends nearest is the move (the planner may jump in the
        second frame of a decision, the agent only in the first). Imitation
        learns from it (tools/rl/ppo.py)."""
        p = self.game.player
        s0, down0 = phys_state(p), bool(p.collisions["down"])
        hz = getattr(self.game, "hazards", None)
        tick = hz.clock if hz is not None else 0
        i = self._route_at.get(s0)
        s, down, wp, frames, first = s0, down0, self.next_wp, 0, None
        for k in range(self.action_repeat):
            move = self._guide_at(s, down, wp, tick + k)
            if move is None and i is not None and i < len(self.route_frames):
                move = self.route_frames[i]
                i += 1
            if move is None:
                break
            if first is None:
                first = (move[0], bool(move[1]), bool(move[2]))
            s, down, dead = ph.apply_frame(s, *move, self.solids)
            frames += 1
            if dead:
                break
            while wp < len(self.waypoints) and self.waypoints[wp].contains(s, down):
                wp += 1
            if wp >= len(self.waypoints):
                break
        if not frames:
            return -1
        target = np.array([s[ph.X], s[ph.Y], 8 * s[ph.VX], 8 * s[ph.VY]])
        dists = []
        for m, jump, dash in ACTIONS:
            if jump and dash_climb_press(s0, dash, self.solids):
                jump = False
            a, a_down, dead = s0, down0, False
            for k in range(frames):
                a, a_down, dead = ph.apply_frame(a, m, jump and k == 0, dash and k == 0, self.solids)
                if dead:
                    break
            if dead:
                dists.append(float("inf"))
                continue
            d = float(((np.array([a[ph.X], a[ph.Y], 8 * a[ph.VX], 8 * a[ph.VY]]) - target) ** 2).sum())
            d += 100.0 * ((a[ph.WALL] != s[ph.WALL]) + (a[ph.JUMPS] != s[ph.JUMPS]) + (a_down != down))
            dists.append(d)
        best = min(dists)
        if best == float("inf"):
            return -1
        if first in ACTIONS and dists[ACTIONS.index(first)] <= best + 1e-6:
            return ACTIONS.index(first)
        return dists.index(best)

    def _guide_at(self, s: tuple, down: bool, wp: int, tick: int) -> tuple | None:
        """The guide's input for state `s` at `tick` (by a flame, its way for
        the beat first)."""
        if self.guide is None or wp >= len(self.waypoints):
            return None
        beat = self.guide.beat(s, tick)
        if beat is not None:
            move = self.guide.move(s, down, wp, beat)
            if move is not None:
                return move
        return self.guide.move(s, down, wp)

    def _segment_area(self, margin_x: int = 40, margin_y: int = 20) -> tuple:
        """Pixel box around the start and every waypoint of the stretch, plus
        a margin wider than any enemy's sight and walk during an episode."""
        ts = self.game.tilemap.tile_size
        sx, sy = self.starts[self.start].pos
        xs = [sx] + [v * ts for w in self.waypoints for v in (w.x0, w.x1 + 1)]
        ys = [sy] + [v * ts for w in self.waypoints for v in (w.y0, w.y1 + 1)]
        return (
            min(xs) - margin_x * ts,
            min(ys) - margin_y * ts,
            max(xs) + margin_x * ts,
            max(ys) + margin_y * ts,
        )

    def _route_index(self, s: tuple | None = None) -> int:
        """The frame of the plan whose state is nearest the player's now (or
        `s`), searched a little behind and ahead of the last one (the route
        is followed forwards, a detour may cost a few frames)."""
        if s is None:
            s = phys_state(self.game.player)
        lo = max(0, self.route_idx - 30)
        hi = min(len(self.route_frames), self.route_idx + 90)
        tr = self.route_trace[lo : hi + 1]
        d = (
            (tr[:, 0] - s[ph.X]) ** 2
            + (tr[:, 1] - s[ph.Y]) ** 2
            + 64.0 * ((tr[:, 2] - s[ph.VX]) ** 2 + (tr[:, 3] - s[ph.VY]) ** 2)
        )
        return lo + int(np.argmin(d))

    def strip_dangers(self) -> None:
        """No enemies, shots or flames (spikes stay): the world the guide is
        built in."""
        g = self.game
        g.enemies.clear()
        g.projectiles.clear()
        hz = getattr(g, "hazards", None)
        if hz is not None:
            for cell in list(hz.zones):
                hz.zones[cell] = [z for z in hz.zones[cell] if z[2] is None]

    def _guide_move(self, timed: bool = False, count: bool = False) -> tuple | None:
        """The guide's move for the player's state now, if it has seen it.
        `timed`: only by a flame, a way made with its beat (`count`: count a
        miss there in `untimed`)."""
        if self.guide is None or self.next_wp >= len(self.waypoints):
            return None
        p = self.game.player
        s, down = phys_state(p), bool(p.collisions["down"])
        if not timed:
            return self.guide.move(s, down, self.next_wp)
        hz = getattr(self.game, "hazards", None)
        beat = self.guide.beat(s, hz.clock) if hz is not None else None
        if beat is None:
            return None
        move = self.guide.move(s, down, self.next_wp, beat)
        if move is None:
            if count:
                self.untimed += 1
            if self._burns(s, down, hz.clock):
                return (0, False, False)  # the way it knows runs into the flame now: wait
        return move

    def _burns(self, s: tuple, down: bool, tick: int, frames: int = 12) -> bool:
        """Whether following the guide's way (blind to the beat) from `s` for
        `frames` frames runs into a burning flame."""
        flames = self.guide.flames
        wp = self.next_wp
        for k in range(frames):
            if flames.lethal(s, tick + k):
                return True
            move = self.guide.move(s, down, wp)
            if move is None:
                return False
            s, down, dead = ph.apply_frame(s, *move, self.solids)
            if dead:
                return False

    def _route_move(self) -> tuple:
        """The route action's input for this frame: the route's own while the
        player is exactly on it, else the guide's, else the route's input at
        the nearest point of it. By a flame, the guide's way for its beat
        comes first. Near an enemy that hurts on touch, an enemy shot or a
        flame jet, it looks LOOK frames ahead along that way: if the way runs
        into the enemy or shot where it will be, or into the burning jet, it
        dodges (see `_dodge_move`)."""
        if self._dodge:
            return self._dodge.popleft()
        move, ahead = self._way_move()
        if self.guide is None or not self.look:  # (no guide: nothing would lead back after a dodge)
            return move
        threats = self._threats()
        s = phys_state(self.game.player)
        if self.attack and (threats[0] or threats[2]):
            attack = self._attack_move(s, threats, ahead)
            if attack is not None:
                self.attacked += 1
                self._clear = (-1, None, {})
                self._dodge.extend(attack[1:])
                return attack[0]
        hz = getattr(self.game, "hazards", None)
        by_flame = hz is not None and self.guide.beat(s, hz.clock) is not None
        if not (threats[0] or threats[1] or threats[2] or by_flame):
            return move
        # The way was found clear a few frames ago, the player is where it
        # led, and nothing new has shown up: no need to look again yet
        until, seen, states = self._clear
        if self.frames < until and seen == self._threat_key(threats) and states.get(self.frames) == s:
            return move
        # A jumper comes down from above: a way under it shows its danger late
        look = LOOK_HOP if any(getattr(getattr(w[0], "kind", None), "hop_period", 0) for w in threats[0]) else LOOK
        paths = self._paths(threats, look=look)
        trace: list = []
        if self._hits(s, ahead, paths, trace, look=look):
            self._clear = (-1, None, {})
            dodge = self._dodge_move(paths, look)
            if dodge is not None:
                self.dodged += 1
                self._dodge.extend(dodge[1:])
                return dodge[0]
        else:
            self._clear = (
                self.frames + RECHECK,
                self._threat_key(threats),
                {self.frames + i + 1: st for i, st in enumerate(trace[:RECHECK])},
            )
        return move

    def _way_move(self) -> tuple[tuple, list]:
        """The route action's input for this frame without enemies, and the
        inputs it plays after it as far as it knows them (the route's while
        the player is on it; else the rest comes from the guide)."""
        p = self.game.player
        s = phys_state(p)
        i = self.route_idx
        if i >= len(self.route_frames) or self.route_states[i] != s:
            j = self._route_at.get(s)
            i = j if j is not None and self.route_idx - 30 <= j <= self.route_idx + 90 else None
        # By a flame, the guide's way past it on its beat first (the route is blind to it)
        move = self._guide_move(timed=True, count=True)
        if move is not None:
            self.guided += 1
            return move, [move]
        if i is not None:
            self.route_idx = i + 1
            self.on_route += 1
            return self.route_frames[i], self.route_frames[i : i + LOOK]
        move = self._guide_move()
        if move is not None:
            self.guided += 1
            return move, [move]
        self.unguided += 1
        i = self._route_index()
        self.route_idx = i + 1
        move = self.route_frames[i] if i < len(self.route_frames) else (0, False, False)
        return move, [move]

    # --- enemies that hurt on touch ----------------------------------------------
    def _walker_snapshot(self) -> tuple[list, list, list]:
        """The enemies a player watches this frame: those that hurt on touch,
        (enemy, x, y, facing left, vertical speed, frames to its next hop);
        the enemies' shots, (x, y, vx, vy,
        gravity); and the armed enemies, (enemy, x, y, facing left, frames
        left of its walk, frames to its next shot, awake)."""
        g = self.game
        walkers, armed = [], []
        for e in g.enemies:
            kind = getattr(e, "kind", None)
            if getattr(kind, "contact", False) is True:
                walkers.append((e, e.pos[0], e.pos[1], e.flip, e.velocity[1], e.cooldown))
            elif getattr(kind, "armed", False):
                armed.append((e, e.pos[0], e.pos[1], e.flip, e.walking, e.cooldown, e.awake))
        shots = [
            (*pr["pos"], *pr["vel"], pr.get("gravity", 0.0)) for pr in g.projectiles if pr.get("owner") != "player"
        ]
        return walkers, shots, armed

    def _threats(self, look: int = LOOK) -> tuple:
        """What the player saw `reaction_delay` frames ago near them:
        (walkers, shots, armed enemies whose shot could reach them soon,
        the walkers a frame before that, frames since)."""
        h = self._walkers
        k = max(0, len(h) - 1 - self.reaction_delay)
        seen, shots, armed = h[k]
        before = h[k - 1][0] if k else ()
        age = len(h) - 1 - k
        alive = {id(e) for e in self.game.enemies}
        px, py = self.game.player.pos
        seen = [w for w in seen if id(w[0]) in alive and abs(w[1] - px) <= WATCH and abs(w[2] - py) <= WATCH]
        shots = [sh for sh in shots if abs(sh[0] - px) <= WATCH + 64 and abs(sh[1] - py) <= WATCH]
        reach = age + look
        armed = [
            a
            for a in armed
            if id(a[0]) in alive
            and abs(a[1] - px) <= 32 + a[0].kind.bullet_speed * reach
            and abs(a[2] - py) <= max(a[0].kind.sight_y, 48) + 16
        ]
        return seen, shots, armed, before, age

    @staticmethod
    def _threat_key(threats: tuple) -> tuple:
        """What tells one look's threats from the next: which enemies, how
        many shots, which armed enemies walk or are awake."""
        seen, shots, armed, _before, _age = threats
        return (
            tuple(id(w[0]) for w in seen),
            len(shots),
            tuple((id(a[0]), a[4] > 0, a[6]) for a in armed),
        )

    def _walker_paths(self) -> list:
        """See `_paths`, for the threats the player sees now."""
        return self._paths(self._threats())

    def _paths(self, threats: tuple, bodies: bool = False, look: int = LOOK) -> list:
        """Where each touch-hurting enemy and each enemy shot near the player
        will be in the next `look` frames ((x, y, w, h, body) at frames
        1..look from now, None once a shot hit a wall; a `_Path` that knows
        whose it is), from what the player saw `reaction_delay` frames ago:
        a patrol walks on by its rules (it turns at walls, edges, spikes and
        flames), another enemy keeps the velocity it had then, a shot flies
        on. Enemies that died since are left out. Shots fired since are not
        seen yet, but the shots a player expects are in (see
        `_expected_shots`). With `bodies`, the armed enemies' bodies too
        (they do not hurt on touch; a dash or a stomp kills them): a gunner
        walks on to the end of its walk, the others stand."""
        seen, shots, armed, before, age = threats
        paths = []
        for e, x, y, flip, vy, cooldown in seen:
            w, hgt = e.size
            if e.kind.hop_period:
                hopper = _Hopper(e, x, y, flip, vy, cooldown)
                for _ in range(age):
                    hopper.step()
                path = []
                for _ in range(look):
                    hopper.step()
                    path.append((hopper.pos[0], hopper.pos[1], w, hgt, True))
            elif e.kind.name == "patrol":
                walker = _Walker(e, x, y, flip)
                for _ in range(age):
                    walker.step()
                path = []
                for _ in range(look):
                    walker.step()
                    path.append((walker.pos[0], walker.pos[1], w, hgt, True))
            else:
                vx = vy = 0.0
                for e0, x0, y0, *_ in before:
                    if e0 is e:
                        vx, vy = x - x0, y - y0
                path = [(x + vx * (age + t), y + vy * (age + t), w, hgt, True) for t in range(1, look + 1)]
            paths.append(_Path(path, e))
        if bodies:
            for e, x, y, flip, walking, _cooldown, _awake in armed:
                w, hgt = e.size
                walker = _Walker(e, x, y, flip)
                path = []
                for t in range(age + look):
                    if t < walking and e.kind.policy == "gunner":
                        walker.step()
                    if t >= age:
                        path.append((walker.pos[0], walker.pos[1], w, hgt, True))
                paths.append(_Path(path, e, hurts=False))
        # Shots fly straight on (a star falls) until they hit a wall
        for x, y, vx, vy, grav in shots:
            path = self._shot_path(x, y, vx, vy, grav, -age, look)
            if path is not None:
                paths.append(_Path(path))
        for x, y, vx, vy, grav, f, e in self._expected_shots(armed, age, look) if self.expect_shots else ():
            path = self._shot_path(x, y, vx, vy, grav, f, look)
            if path is not None:
                paths.append(_Path(path, e, fired=f))
        return paths

    def _shot_path(
        self, x: float, y: float, vx: float, vy: float, grav: float, f: int, look: int = LOOK
    ) -> list | None:
        """A shot at (x, y) at frame `f` from now (negative: before now) as
        it flies on: where it is at frames 1..look (None before it is fired
        and after it hit a wall); None if it is never there."""
        tm = self.game.tilemap
        path: list = [None] * look
        for t in range(f + 1, look + 1):
            vy += grav
            x, y = x + vx, y + vy
            if tm.solid_check((x, y)):
                break
            if t >= 1:
                path[t - 1] = (x, y, 4, 4, False)
        return path if any(path) else None

    def _expected_shots(self, armed: list, age: int, look: int = LOOK) -> list:
        """The shots a player who knows the enemies expects from what they
        saw `reaction_delay` frames ago, fired since or soon, at where the
        player is now: (x, y, vx, vy, gravity, frame from now it is fired,
        the enemy).
        A gunner fires when its walk ends, if it then faces the player in
        sight (scripts/ai/behaviors.py, GunnerPolicy); a turret or thrower
        that is awake fires each time its cooldown runs out. Whether another
        enemy close by fired just before (and holds this one's fire) is not
        counted: a player expects the shot."""
        p = self.game.player
        pr = p.rect()
        out = []
        for e, x, y, flip, walking, cooldown, awake in armed:
            kind = e.kind
            fires = []  # (frame from now, x, y, facing left)
            if kind.policy == "gunner":
                if walking > 0 and walking - age <= look:
                    w = _Walker(e, x, y, flip)
                    for _ in range(walking):
                        w.step()
                    fires.append((walking - age, w.pos[0], w.pos[1], w.flip))
            elif awake and kind.fire_period > 0:
                f = max(cooldown, 1) - age
                while f <= look:
                    fires.append((f, x, y, None))
                    f += kind.fire_period
            for f, ex, ey, left in fires:
                r = pygame.Rect(ex, ey, e.size[0], e.size[1])
                if kind.projectile == "star":
                    dx, dy = pr.centerx - r.centerx, pr.centery - (r.top + 3)
                    if not (abs(dx) < kind.sight_x and abs(dy) < kind.sight_y):
                        continue
                    v = throw_velocity(kind, dx, dy)
                    if v is not None:
                        sx = r.centerx + (6 if v[0] > 0 else -6)
                        out.append((sx, r.top + 3, v[0], v[1], kind.throw_gravity, f, e))
                    continue
                dx, dy = p.pos[0] - ex, p.pos[1] - ey
                if not (abs(dx) < kind.sight_x and abs(dy) < kind.sight_y):
                    continue
                if left is None:  # a turret turns to the player
                    left = dx < 0
                elif left != (dx < 0):
                    continue  # a gunner fires only the way it faces
                d = -1 if left else 1
                out.append((r.centerx + 15 * d, r.centery, d * kind.bullet_speed, 0.0, 0.0, f, e))
        return out

    def _hits(
        self,
        s: tuple,
        moves: list,
        paths: list,
        trace: list | None = None,
        kills: dict | None = None,
        target=None,
        look: int = LOOK,
    ) -> bool:
        """Whether playing `moves` from `s`, then the guide's way, runs into
        an enemy or shot on its `paths`, into a burning flame jet or to a
        deadly fall within `look` frames. Dashing through an enemy or landing
        on it kills it. `trace` gets the states after each frame. The
        guide's moves are kept while the guide is the same: the looks of the
        next frames and episodes go the same way. With `kills`, an enemy whose `_Path` the dash or
        the landing meets dies (into `kills`, with the frame): from then on
        its body and the shots it would fire later are gone, and a landing
        bounces the player up as in the game; the guide's way follows the
        kill of `target`; and where the guide knows no way on, the route's
        input at its nearest point is played (as the route action does), not
        taken for clear, and the way counts as a hit if it ends there or
        does not get back to the route (see `_rejoins`)."""
        guide_ = self.guide
        memo = self._memo
        if len(memo) > 100_000:
            memo.clear()
        hz = getattr(self.game, "hazards", None)
        tick = hz.clock if hz is not None else 0
        down, wp = bool(self.game.player.collisions["down"]), self.next_wp
        dead = kills if kills is not None else {}  # enemy -> frame it died
        hurting = [path for path in paths if getattr(path, "hurts", True)]
        lost = False  # the guide knew no way from the last state
        for k in range(look):
            if k < len(moves):
                move = moves[k]
            elif guide_ is None:
                return False
            else:  # the guide's way: by a flame, the one for its beat
                beat = guide_.beat(s, tick + k)
                mk = (s, down, wp, beat)
                move = memo.get(mk, False)
                if move is False:
                    move = guide_.move(s, down, wp, beat) if beat is not None else None
                    move = memo[mk] = move or guide_.move(s, down, wp)
                if move is None:  # no known way on: a look counts it clear ...
                    if kills is None:
                        return False
                    if target in dead:
                        self._lost(s, down, wp)
                    i = self._route_index(s)  # ... an attack plays on as the route action would
                    move = self.route_frames[i] if i < len(self.route_frames) else (0, False, False)
                    lost = True
                else:
                    lost = False
            bottom = s[ph.Y] + PH
            s, down, dead_fall = ph.apply_frame(s, *move, self.solids)
            if trace is not None:
                trace.append(s)
            if dead_fall:
                return True
            if guide_ is not None and guide_.flames is not None and guide_.flames.lethal(s, tick + k + 1):
                return True
            dashing = abs(s[ph.DASH]) >= DASH_MIN_ACTIVE_ABS
            x, y = int(s[ph.X]), int(s[ph.Y])
            if kills is None:  # a look: only what hurts, nothing dies
                if dashing:
                    continue
                for path in hurting:
                    at = path[k]
                    if at is None:  # a shot that hit a wall
                        continue
                    ex, ey, ew, eh, body = at
                    ex, ey = int(ex) - 1, int(ey) - 1
                    if x < ex + ew + 2 and ex < x + PW and y < ey + eh + 2 and ey < y + PH:
                        if body and s[ph.VY] > 0 and bottom <= ey + 1 + STOMP_MARGIN:
                            continue  # lands on it: a stomp
                        return True
                continue
            for path in paths:
                at = path[k]
                if at is None:  # a shot that hit a wall
                    continue
                ex, ey, ew, eh, body = at
                owner = getattr(path, "owner", None)
                if dead and owner in dead and (body or path.fired > dead[owner]):
                    continue  # killed: gone, and fires no more
                if body and owner is not None:
                    ix, iy = int(ex), int(ey)
                    if x < ix + ew and ix < x + PW and y < iy + eh and iy < y + PH:
                        if dashing or (s[ph.Y] + PH > bottom and bottom <= iy + STOMP_MARGIN):
                            dead[owner] = k
                            if owner is target:
                                moves = moves[: k + 1]  # then the guide's way
                            if not dashing:  # Player.stomp
                                s = s[: ph.VY] + (STOMP_BOUNCE_VELOCITY, 5) + s[ph.AIR + 1 :]
                            continue
                if dashing or not getattr(path, "hurts", True):
                    continue
                ex, ey = int(ex) - 1, int(ey) - 1
                if x < ex + ew + 2 and ex < x + PW and y < ey + eh + 2 and ey < y + PH:
                    if body and s[ph.VY] > 0 and bottom <= ey + 1 + STOMP_MARGIN:
                        continue  # lands on it: a stomp
                    return True
        if kills is None:
            return False
        if target is not None and target not in dead:
            return True
        return lost or not self._rejoins(s, down, wp, tick + look)  # an attack must lead back to the route

    def _rejoins(self, s: tuple, down: bool, wp: int, tick: int) -> bool:
        """Whether the guide's way from `s` (no enemies) gets back onto the
        route or to waypoint `wp` within REJOIN frames without a deadly fall
        or flame. The guide's move off its own states is the one of the
        nearest it knows, which a precise jump of the route (a dash over a
        chasm) may not forgive; the physics is exact, so playing it out
        tells. Kept while the guide is the same: the same attacks come up
        episode after episode."""
        guide_ = self.guide
        flames = guide_.flames is not None
        rk = (s, down, wp, tick if flames else 0)
        known = self._rejoined.get(rk)
        if known is not None:
            return known
        memo = self._memo
        lo = self.route_idx - 30
        goal = self.waypoints[wp] if wp < len(self.waypoints) else None
        seen = [rk]
        ok = False
        for k in range(REJOIN):
            j = self._route_at.get(s)
            if (j is not None and j >= lo) or (goal is not None and goal.contains(s, down)):
                ok = True
                break
            beat = guide_.beat(s, tick + k)
            mk = (s, down, wp, beat)
            move = memo.get(mk, False)
            if move is False:
                move = guide_.move(s, down, wp, beat) if beat is not None else None
                move = memo[mk] = move or guide_.move(s, down, wp)
            if move is None:
                self._lost(s, down, wp)
                break
            s, down, dead_fall = ph.apply_frame(s, *move, self.solids)
            if dead_fall or (flames and guide_.flames.lethal(s, tick + k + 1)):
                break
            if not flames:
                rk = (s, down, wp, 0)
                known = self._rejoined.get(rk)
                if known is not None:
                    ok = known
                    break
                seen.append(rk)
        if len(self._rejoined) > 200_000:
            self._rejoined.clear()
        for rk in seen:  # the states on the way lead back (or not) the same way
            self._rejoined[rk] = ok
        return ok

    def _lost(self, s: tuple, down: bool, wp: int) -> None:
        """Note a state the way after an attack gets to and the guide knows
        no way on from, while the guide is built (see `stretch_guide`)."""
        if self.attack_misses is not None:
            self.attack_misses.setdefault(guide.key(s, down, wp), (s, down, wp, 0))

    def _targets(self, s: tuple, threats: tuple) -> list:
        """The enemies a player would go for now, nearest first, as they
        saw them `reaction_delay` frames ago: on the way on (ahead along the
        route, or no more than BEHIND px back), in reach of a dash or a jump
        (REACH) and a danger. A danger is an enemy that hurts on touch, a
        gunner that faces the player in sight (it fires when its walk ends),
        or a turret or thrower that has them in sight (it turns to them). An
        enemy further back is left: going back for it costs the dash and
        the time the way on needs."""
        seen, _shots, armed, _before, _age = threats
        px, py = s[ph.X], s[ph.Y]
        ahead = 1 if self._ahead_x(s) >= px else -1
        out = []
        for e, x, y, *_ in seen:
            dx = (x - px) * ahead
            if -BEHIND <= dx <= REACH[0] and abs(y - py) <= REACH[1]:
                out.append((abs(dx), e))
        for e, x, y, flip, _walking, _cooldown, _awake in armed:
            dx, dy = (x - px) * ahead, py - y
            if not (-BEHIND <= dx <= REACH[0] and abs(dy) <= REACH[1] and abs(dy) < max(e.kind.sight_y, 16) + 8):
                continue
            if e.kind.policy == "gunner" and flip != (px < x):
                continue  # faces away: no danger
            out.append((abs(dx), e))
        return [e for _d, e in sorted(out, key=lambda o: o[0])]

    def _ahead_x(self, s: tuple) -> float:
        """Where along x the route goes on from the player (LOOK frames on
        from its nearest point)."""
        i = min(self.route_idx + LOOK, len(self.route_states) - 1)
        return self.route_states[i][ph.X]

    def _attack_move(self, s: tuple, threats: tuple, ahead: list) -> list | None:
        """The inputs that kill an enemy in the way, as a player would: a
        dash at it, or a jump onto it (holding toward it for a while, then
        letting go), turning to it first if need be. Only for an enemy that
        is a danger (see `_targets`; one that hurts on touch only if the way
        on, `ahead` then the guide's, meets it within ATTACK_LOOK frames;
        an armed one in sight will fire on the way on), and only if the
        attack kills it and, from the kill on, the guide's way runs into
        nothing (its later shots counted out) up to ATTACK_LOOK frames from
        now and gets back to the route (see `_rejoins`). The inputs end with
        the kill. None: no such attack."""
        if self.frames % self.action_repeat:
            return None  # a player picks a fight when they decide, not mid-move
        tried = self._tried
        targets = [e for e in self._targets(s, threats) if tried.get(e, -RETRY) + RETRY <= self.frames]
        if not targets:
            return None
        threats = self._threats(ATTACK_LOOK)
        paths = self._paths(threats, bodies=True, look=ATTACK_LOOK)
        for e in targets:
            body = next((path for path in paths if path.owner is e and path[0][4]), None)
            if body is None:
                continue  # died since
            if body.hurts and not self._hits(s, ahead, [body], look=ATTACK_LOOK):
                tried[e] = self.frames
                continue  # hurts on touch, but the way on does not meet it: no need
            ex = body[-1][0] + body[-1][2] / 2  # its middle when a jump comes down on it
            m = 1 if body[0][0] + body[0][2] / 2 > s[ph.X] + PW / 2 else -1
            turn = [(m, False, False)] if s[ph.FLIP] != (m < 0) else []
            at = ph.apply_frame(s, *turn[0], self.solids)[0] if turn else s
            for moves in self._attacks(at, m, ex, stomp=not e.kind.hop_period):
                moves = turn + moves
                kills: dict = {}
                if not self._hits(s, moves, paths, kills=kills, target=e, look=ATTACK_LOOK) and e in kills:
                    return moves[: kills[e] + 1]
            tried[e] = self.frames  # none worked: the player walks on a little before trying again
        return None

    def _attacks(self, s: tuple, m: int, ex: float, stomp: bool = True) -> list:
        """The ways to go for an enemy on side `m` from `s` whose middle will
        be at x `ex`: a dash (held while it lasts); a jump held toward it
        about as long as it takes to get above it at walking speed (1 px a
        frame), then let go (a stomp; not on a jumper, whose hops the look
        does not foresee); and a jump with a dash in the air."""
        hold = [(m, False, False)] * ATTACK_LOOK
        out = []
        if not s[ph.DASH]:
            out.append([(m, False, True)] + hold[:12])
        if stomp and ph.can_jump(s, self.solids) and not dash_climb_press(s, False, self.solids):
            dx = int(abs(ex - (s[ph.X] + PW / 2)))
            for h in sorted({max(1, min(60, dx + d)) for d in (-4, 0, 4)}):
                out.append([(m, True, False)] + hold[: h - 1] + [(0, False, False)] * ATTACK_LOOK)
            if not s[ph.DASH] and not dash_climb_press(s, True, self.solids):
                out.append([(m, True, True)] + hold[:12])  # (a jump into a dash is a dash in the air)
        return out

    def _dodge_move(self, paths: list, look: int = LOOK) -> list | None:
        """A decision's inputs (one move held `action_repeat` frames, jump and
        dash pressed on its first) after which the guide's way runs into no
        enemy and no flame: wait, dash through the nearest enemy, jump, or
        back off. None: there is none."""
        p = self.game.player
        s = phys_state(p)
        ex = min((path[0][0] for path in paths if path[0] is not None), key=lambda v: abs(v - s[ph.X]), default=s[ph.X])
        toward = 1 if ex > s[ph.X] else -1
        n = self.action_repeat
        for m, jump, dash in (
            (0, False, False),
            (toward, False, True),
            (0, True, False),
            (-toward, False, False),
            (-toward, True, False),
            (toward, True, False),
            (-toward, False, True),
        ):
            if jump and dash_climb_press(s, dash, self.solids):
                continue
            moves = [(m, jump, dash)] + [(m, False, False)] * (n - 1)
            if not self._hits(s, moves, paths, look=look):
                return moves
        return None

    def handoff(self, max_expand: int = 3000) -> bool:
        """After a goal: can the planner take over from where the agent stands?
        It plans, on a small budget, to the fixed point the route itself
        arrives at (standing, the tile of the route's last state), from where
        the level's route goes on."""
        p = self.game.player
        x, y = self.route_trace[-1][:2]
        tx, ty = int((x + PW / 2) // ph.TS), int((y + PH / 2) // ph.TS)
        res = plan_segment(
            phys_state(p),
            Waypoint(tx, ty, tx, ty, ground=True, label="handoff"),
            self.solids,
            kill_y=self.solids.kill_y,
            start_down=bool(p.collisions["down"]),
            no_dash_climb=True,
            weight=5.0,
            max_expand=max_expand,
        )
        return res.ok

    # --- route -------------------------------------------------------------------
    def _center(self) -> tuple:
        p = self.game.player
        return p.pos[0] + PW / 2, p.pos[1] + PH / 2

    def _inside(self, wp) -> bool:
        ts = self.game.tilemap.tile_size
        cx, cy = self._center()
        inside = wp.x0 * ts <= cx <= (wp.x1 + 1) * ts and wp.y0 * ts <= cy <= (wp.y1 + 1) * ts
        return inside and (not wp.ground or self.game.player.collisions["down"])

    def _progress(self, near: float = 24.0) -> int:
        """Frames of the route gained: the furthest point of the route (up to
        90 frames on from the furthest so far) within `near` px of the player."""
        p = self.game.player
        lo = self.best + 1
        hi = min(len(self.route_trace), self.best + 91)
        if lo >= hi:
            return 0
        tr = self.route_trace[lo:hi]
        close = np.nonzero((tr[:, 0] - p.pos[0]) ** 2 + (tr[:, 1] - p.pos[1]) ** 2 <= near * near)[0]
        if not len(close):
            return 0
        gained = int(close[-1]) + 1
        self.best += gained
        return gained

    # --- observation -------------------------------------------------------------
    def _build_layers(self) -> None:
        """The level's static layers (solid, water, deadly) as arrays padded by
        half a grid on every side; flames and fallen blocks are patched in per
        observation."""
        g, tm = self.game, self.game.tilemap
        ts = tm.tile_size
        cells = [tuple(t["pos"]) for t in tm.tilemap.values()] + list(getattr(tm, "water", {}) or {})
        xs = [c[0] for c in cells] or [0]
        ys = [c[1] for c in cells] or [0]
        px, py = GRID_W, GRID_H
        self._ox, self._oy = min(xs) - px, min(ys) - py
        w, h = max(xs) - min(xs) + 1 + 2 * px, max(ys) - min(ys) + 1 + 2 * py
        layers = np.zeros((3, h, w), np.float32)
        for x in range(w):
            for y in range(h):
                if tm.solid_type(x + self._ox, y + self._oy) is not None:
                    layers[0, y, x] = 1.0
        for tx, ty in getattr(tm, "water", {}) or {}:
            layers[1, ty - self._oy, tx - self._ox] = 1.0
        hz = getattr(g, "hazards", None)
        self._jet_cells = []
        for (tx, ty), zones in (hz.zones if hz is not None else {}).items():
            for _rect, _cause, jet in zones:
                if jet is None:
                    layers[2, ty - self._oy, tx - self._ox] = 1.0
                else:
                    self._jet_cells.append((ty - self._oy, tx - self._ox, jet))
        kill_y = getattr(tm, "kill_y", None)
        if kill_y is not None:
            row = int(kill_y // ts) + 1 - self._oy
            layers[2, max(row, 0) :, :] = 1.0
        self._layers = layers

    def _grid(self, tx: int, ty: int) -> np.ndarray:
        x0 = tx - GRID_W // 2 - self._ox
        y0 = ty - GRID_H // 2 - self._oy
        _c, h, w = self._layers.shape
        x0 = min(max(x0, 0), w - GRID_W)
        y0 = min(max(y0, 0), h - GRID_H)
        grid = self._layers[:, y0 : y0 + GRID_H, x0 : x0 + GRID_W].copy()
        hz = getattr(self.game, "hazards", None)
        if hz is not None:
            for y, x, jet in self._jet_cells:
                if y0 <= y < y0 + GRID_H and x0 <= x < x0 + GRID_W:
                    level = FLAME_LEVEL[jet.state(hz.clock)]
                    grid[2, y - y0, x - x0] = max(grid[2, y - y0, x - x0], level)
            for tile, _left in hz.fallen.values():
                x, y = tile["pos"][0] - self._ox - x0, tile["pos"][1] - self._oy - y0
                if 0 <= y < GRID_H and 0 <= x < GRID_W:
                    grid[0, y, x] = 0.0
        return grid

    def _flame(self, cx: float, cy: float) -> list:
        """The nearest flame jet: where its nozzle is, its state and how far
        into that state it is (the beat a player picks up after one cycle)."""
        hz = getattr(self.game, "hazards", None)
        jets = getattr(hz, "jets", None) if hz is not None else None
        if not jets:
            return [0.0] * FLAME_FEATURES
        ts = self.game.tilemap.tile_size
        jet = min(jets, key=lambda j: ((j.pos[0] + 0.5) * ts - cx) ** 2 + ((j.pos[1] + 0.5) * ts - cy) ** 2)
        t = (hz.clock + jet.phase) % jet.period
        warn = max(1, min(FLAME_WARN, jet.period - jet.on))
        state = jet.state(hz.clock)
        if state == "burn":
            elapsed = t / max(1, jet.on)
        elif state == "warn":
            elapsed = (t - (jet.period - warn)) / warn
        else:
            elapsed = (t - jet.on) / max(1, jet.period - warn - jet.on)
        return [
            float(np.clip(((jet.pos[0] + 0.5) * ts - cx) / SCALE, -2, 2)),
            float(np.clip(((jet.pos[1] + 0.5) * ts - cy) / SCALE, -2, 2)),
            1.0 if state == "off" else 0.0,
            1.0 if state == "warn" else 0.0,
            1.0 if state == "burn" else 0.0,
            float(elapsed),
        ]

    def _observe(self) -> np.ndarray:
        g, p = self.game, self.game.player
        tm = g.tilemap
        ts = tm.tile_size
        cx, cy = self._center()
        head_wet = p.head_in_water(tm)
        out = [
            p.velocity[0] / 3.0,
            p.velocity[1] / 5.0,
            1.0 if p.flip else -1.0,
            min(p.air_time, 120) / 120.0,
            p.jumps / 2.0,
            p.dashing / 60.0,
            1.0 if p.wall_slide else 0.0,
            1.0 if p.collisions["down"] else 0.0,
            1.0 if head_wet else 0.0,
            getattr(p, "breath", 0) / 600.0 if head_wet else 1.0,
        ]
        # Goal: the next waypoint's centre and the final one's
        last = self.waypoints[-1]
        wp = self.waypoints[min(self.next_wp, len(self.waypoints) - 1)]
        for w in (wp, last):
            gx = (w.x0 + w.x1 + 1) / 2 * ts
            gy = (w.y0 + w.y1 + 1) / 2 * ts
            out.append(float(np.clip((gx - cx) / SCALE, -2, 2)))
            out.append(float(np.clip((gy - cy) / SCALE, -2, 2)))
        # The planned route: where it is and what it does next
        i = self._route_index()
        ahead = self.route_frames[i : i + 8]
        ahead = ahead or [(0, False, False)]
        tr = self.route_trace[i]
        near = ahead[:4]
        out += [
            float(np.clip((tr[0] - p.pos[0]) / SCALE, -2, 2)),
            float(np.clip((tr[1] - p.pos[1]) / SCALE, -2, 2)),
            sum(m for m, _j, _d in near) / len(near),
            1.0 if any(j for _m, j, _d in near) else 0.0,
            1.0 if any(d for _m, _j, d in near) else 0.0,
            sum(m for m, _j, _d in ahead) / len(ahead),
        ]
        last = len(self.route_trace) - 1
        for k in ROUTE_AHEAD:  # where the route goes: the way through a maze
            tk = self.route_trace[min(i + k, last)]
            out.append(float(np.clip((tk[0] - p.pos[0]) / SCALE, -2, 2)))
            out.append(float(np.clip((tk[1] - p.pos[1]) / SCALE, -2, 2)))
        out += self._flame(cx, cy)
        # Local grid: solid, water, deadly (flames by their state, FLAME_LEVEL)
        out.extend(self._grid(int(cx // ts), int(cy // ts)).ravel())
        # Enemies, nearest first
        enemies = sorted(g.enemies, key=lambda e: (e.pos[0] - cx) ** 2 + (e.pos[1] - cy) ** 2)[:N_ENEMIES]
        for e in enemies:
            kind = getattr(e, "kind", None)
            out.extend(
                [
                    float(np.clip((e.pos[0] + 4 - cx) / SCALE, -2, 2)),
                    float(np.clip((e.pos[1] + 7 - cy) / SCALE, -2, 2)),
                    e.velocity[0] / 2.0,
                    e.velocity[1] / 3.0,
                    1.0 if kind is not None and kind.armed else 0.0,
                    1.0,
                ]
            )
        out.extend([0.0] * ENEMY_FEATURES * (N_ENEMIES - len(enemies)))
        # Hostile projectiles, nearest first
        shots = [pr for pr in g.projectiles if pr.get("owner") != "player"]
        shots.sort(key=lambda pr: (pr["pos"][0] - cx) ** 2 + (pr["pos"][1] - cy) ** 2)
        for pr in shots[:N_PROJECTILES]:
            out.extend(
                [
                    float(np.clip((pr["pos"][0] - cx) / SCALE, -2, 2)),
                    float(np.clip((pr["pos"][1] - cy) / SCALE, -2, 2)),
                    pr["vel"][0] / 3.0,
                    pr["vel"][1] / 3.0,
                    1.0,
                ]
            )
        out.extend([0.0] * PROJ_FEATURES * (N_PROJECTILES - min(len(shots), N_PROJECTILES)))
        return np.asarray(out, dtype=np.float32)
