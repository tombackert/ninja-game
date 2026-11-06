"""Difficulty from timing windows: how precisely each key press of a level must land.

A level's route is cut into elements: the stretch from one place a player
can stand still (a ground waypoint, or one where a player who lets go of
all keys comes to rest) to the next. For each element the most forgiving
way to play it is searched, the way players converge on it: start settled
(standing on the ledge before it), try many input programs (the route
planner with coarse and fine input macros, with and without dashes, from
several spots on the ledge, then its tightest presses moved and the rest
planned anew) and keep the one most likely to be played through.

The timing window of a key press (a jump, a dash, starting, stopping or
turning) is the number of frames it can be pressed on with the element
still played through: every shift of that one press is replayed in the
physics replica, either alone (the other presses keep their frames) or
with the presses after it (they are timed from it), whichever forgives
more. An element succeeds if the player reaches its waypoint(s) in order
(standing, for a ground waypoint) without dying.

A press with a window of w frames hits with p(w) = erf(w / (2 sqrt 2 sigma)):
a player aims at the middle and is off by a gaussian error of sigma frames
(1 sd); with a small chance (lapse) the press is a blunder instead. An
element is played through with the product over its presses; a miss is a
death if no quick correction lands the player where the element can be
gone on from, else the element is simply tried again. `first_clear` turns
that into minutes and deaths to the first clear, with the level's
checkpoint banners and the manual checkpoint P (assess.time_to_beat). The
skill profiles are fitted to real playtests (tools/worlds/calibrate.py,
docs/difficulty-rating-brainstorm.md).

    python -m tools.worlds.assess 26 --windows
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from scripts.constants import RESPAWN_DEAD_THRESHOLD
from tools.worlds import physics as ph
from tools.worlds.planner import Waypoint, plan_segment

CAP = 12  # frames a press is shifted at most either way: a window of 2 * CAP + 1 is "free"
FREE = 2 * CAP + 1
TAIL = 60  # frames a program may run on (last direction held) to reach its goal
SETTLE = 90  # frames a player who lets go of all keys has to come to rest
REACT = 10  # frames until a correction after a miss takes effect
SIGMA_REF = 1.5  # timing error the search for the most forgiving program optimizes for
LENGTH_COST = 1e-4  # log-chance a frame of extra length is worth

# Skill profiles: timing error of a press (frames, 1 sd, in the units of the
# windows measured here), chance that a press is a blunder instead (anywhere
# within CAP frames either way), pace (play time over the most forgiving
# programs' time) and seconds of hesitation before a press of PAUSE_WINDOW
# frames or less. "expert" is fitted (tools/worlds/calibrate.py) to the main
# tester's session of 2026-11-03 (levels 13-25: 8 of 13 cleared without a
# death before, 6.8 min lost to failed attempts, runs 1.2x the programs'
# time); "average" (the developer, level 26 on 2026-11-05) has 1.5x the
# expert's error and lapses, as one playtest cannot fit it. See
# docs/difficulty-rating-brainstorm.md.
PROFILES = {
    "expert": {"sigma": 0.4, "pace": 1.2, "pause": 0.0, "lapse": 0.08},
    "average": {"sigma": 0.6, "pace": 1.26, "pause": 0.0, "lapse": 0.12},
}

# Planner settings the candidates of an element come from: (weight, macro
# durations, dash allowed). Coarse macros give the simple programs people
# play (hold a direction, one jump), fine ones the tight ones.
CONFIGS = (
    (5.0, (4, 8, 16), False),
    (5.0, (4, 8, 16), True),
    (5.0, (6, 12, 24), False),
    (5.0, (6, 12, 24), True),
    (5.0, (1, 3, 8), True),
    (2.0, (2, 6, 12), True),
    (5.0, (1, 3, 8), False),
)

# --- input programs and their key presses ---------------------------------


@dataclass(frozen=True)
class Event:
    """One key press of a program: a jump or dash press, or a change of the held direction."""

    frame: int
    kind: str  # "jump", "dash" or "move"


def events(frames: list, lastm: int = 0) -> list[Event]:
    """The presses of a program (`lastm`: the direction held before it)."""
    out = []
    prev = lastm
    for i, (m, j, d) in enumerate(frames):
        if m != prev:
            out.append(Event(i, "move"))
        if j:
            out.append(Event(i, "jump"))
        if d:
            out.append(Event(i, "dash"))
        prev = m
    return out


def shifted(frames: list, ev: Event, delta: int, carry: bool, lastm: int = 0) -> list | None:
    """`frames` with the press `ev` moved by `delta` frames, alone or (`carry`) with
    everything after it. None if the press would cross another one."""
    n = len(frames)
    f = ev.frame
    if carry:
        if delta > 0:
            before = frames[f - 1][0] if f > 0 else lastm
            return frames[:f] + [(before, False, False)] * delta + frames[f:]
        lo = f + delta
        if lo < 0:
            return None
        prev_m = frames[lo - 1][0] if lo > 0 else lastm
        for m, j, d in frames[lo:f]:
            if j or d or m != prev_m:
                return None
        return frames[:lo] + frames[f:]
    out = list(frames)
    if ev.kind in ("jump", "dash"):
        k = 1 if ev.kind == "jump" else 2
        g = f + delta
        if not 0 <= g < n or frames[g][k]:
            return None
        m, j, d = out[f]
        out[f] = (m, False, d) if k == 1 else (m, j, False)
        m, j, d = out[g]
        out[g] = (m, True, d) if k == 1 else (m, j, True)
        return out
    old = frames[f - 1][0] if f > 0 else lastm
    new = frames[f][0]
    if delta > 0:
        if f + delta > n:
            return None
        for i in range(f, f + delta):
            if frames[i][0] != new:
                return None
            out[i] = (old, frames[i][1], frames[i][2])
        return out
    if f + delta < 0:
        return None
    prev_m = frames[f + delta - 1][0] if f + delta > 0 else lastm
    if prev_m != old:
        return None  # the shift would swallow an earlier direction change
    for i in range(f + delta, f):
        out[i] = (new, frames[i][1], frames[i][2])
    return out


# --- playing an element ---------------------------------------------------


def _key(s: tuple) -> tuple:
    return tuple(round(v, 6) if isinstance(v, float) else v for v in s)


@dataclass
class Outcome:
    ok: bool
    dead: bool
    frames: int  # frames played until the goal, death or the time limit
    end: tuple
    states: list = field(default_factory=list)  # state after each frame from `first` on (when recorded)
    progress: list = field(default_factory=list)  # goals reached after each of those frames
    first: int = 0

    def state_at(self, i: int) -> tuple:
        """Recorded state after frame i (clamped to the recorded ones)."""
        if not self.states:
            return self.end
        return self.states[min(len(self.states) - 1, max(0, i - self.first))]


def play(
    start: tuple,
    frames: list,
    goals: list,
    solids,
    *,
    limit: int | None = None,
    record: bool = False,
    resume: tuple | None = None,
    ref: Outcome | None = None,
    ref_offset: int = 0,
    converge_from: int = 0,
) -> Outcome:
    """Play `frames` from `start` until all `goals` are reached in order (standing,
    for ground ones); past the last frame the last direction is held. With `ref`
    (the recorded outcome of a program that succeeds), a state equal to the
    reference's at frame i - ref_offset, from frame `converge_from` on, ends the
    run as a success: from there both play alike. `resume` = (frame, state, goals
    reached) starts later on, from a recorded state."""
    n = len(frames)
    limit = n + TAIL if limit is None else limit
    last_m = frames[-1][0] if frames else 0
    i0, s, g = resume if resume else (0, start, 0)
    states, progress = [], []
    ng = len(goals)
    if g >= ng:
        return Outcome(True, False, i0, s, states, progress, i0)
    goal = goals[g]
    for i in range(i0, limit):
        m, j, d = frames[i] if i < n else (last_m, False, False)
        s, down, dead = ph.apply_frame(s, m, j, d, solids)
        if dead:
            return Outcome(False, True, i + 1, s, states, progress, i0)
        while goal.contains(s, down):
            g += 1
            if g == ng:
                if record:
                    states.append(s)
                    progress.append(g)
                return Outcome(True, False, i + 1, s, states, progress, i0)
            goal = goals[g]
        if record:
            states.append(s)
            progress.append(g)
        if ref is not None and i >= converge_from:
            r = i - ref_offset
            if 0 <= r < len(ref.states) and ref.progress[r] == g and _key(ref.states[r]) == _key(s):
                return Outcome(True, False, ref.frames + ref_offset, ref.end, states, progress, i0)
    return Outcome(False, False, limit, s, states, progress, i0)


@dataclass
class Window:
    event: Event
    lo: int  # earliest shift that still plays through (<= 0)
    hi: int  # latest (>= 0)
    carry: bool  # the window counts the later presses as timed from this one
    fails: list = field(default_factory=list)  # (shift, died, state REACT frames after the press)

    @property
    def width(self) -> int:
        return min(FREE, self.hi - self.lo + 1)


def _shift_run(start, frames, goals, solids, nominal, ev, delta, carry, lastm, cap_limit) -> Outcome | None:
    """The program with one press shifted, played from where it starts to differ
    (None if that shift is not possible)."""
    alt = shifted(frames, ev, delta, carry, lastm)
    if alt is None:
        return None
    first = min(ev.frame, ev.frame + delta)
    last = max(ev.frame, ev.frame + delta)
    resume = None
    if first > 0 and first - 1 < len(nominal.states):
        resume = (first, nominal.states[first - 1], nominal.progress[first - 1])
    off = delta if carry else 0
    limit = cap_limit + max(0, off)
    return play(
        start,
        alt,
        goals,
        solids,
        limit=limit,
        resume=resume,
        ref=nominal,
        ref_offset=off,
        converge_from=last + 1,
        record=True,
    )


def press_windows(
    start: tuple, frames: list, goals: list, solids, *, floor: float | None = None
) -> list[Window] | None:
    """Timing window of every press of a program that plays the element through
    (None if it does not). With `floor`, gives up (None) as soon as the presses so
    far score below it (`score`): a candidate that cannot beat the best one."""
    nominal = play(start, frames, goals, solids, record=True)
    if not nominal.ok:
        return None
    limit = len(frames) + TAIL
    lastm = start[ph.LASTM]
    out = []
    total = 0.0
    evs = events(frames, lastm)
    free_first = bool(evs) and stationary(start, solids)
    for n, ev in enumerate(evs):
        if n == 0 and free_first and all(f == (lastm, False, False) for f in frames[: ev.frame]):
            out.append(Window(ev, -CAP, CAP, True))  # from standing still: start whenever
            continue
        best = None
        for carry in (False, True):
            lo = hi = 0
            fails = []
            for sign in (-1, 1):
                for k in range(1, CAP + 1):
                    res = _shift_run(start, frames, goals, solids, nominal, ev, sign * k, carry, lastm, limit)
                    if res is None:
                        break
                    if not res.ok:
                        at = ev.frame + (sign * k if not carry else min(0, sign * k)) + REACT
                        fails.append((sign * k, res.dead, res.state_at(at)))
                        break
                    if sign < 0:
                        lo = -k
                    else:
                        hi = k
            w = Window(ev, lo, hi, carry, fails)
            if best is None or w.width > best.width:
                best = w
            if best.width >= FREE:
                break
        out.append(best)
        total += math.log(max(p_hit(best.width, SIGMA_REF), 1e-9))
        if floor is not None and total < floor:
            return None
    return out


def score(windows: list, n_frames: int) -> float:
    """How forgiving a program is: log of its chance to be played through by a
    player with SIGMA_REF, less a little for its length (a much longer way
    round is not worth a sliver of safety)."""
    return sum(math.log(max(p_hit(w.width, SIGMA_REF), 1e-9)) for w in windows) - LENGTH_COST * n_frames


def narrowest(windows: list[Window]) -> int:
    return min((w.width for w in windows), default=FREE)


# --- elements of a route ----------------------------------------------------

MAX_SPAN = 8  # waypoints an element may take at most


def settle(s: tuple, box: Waypoint, solids) -> tuple | None:
    """Let go of all keys: the state the player comes to rest in (just landed on
    the ground, no speed left, dash ready), if that is within a tile of `box` and
    alive."""
    for _ in range(SETTLE):
        s, down, dead = ph.apply_frame(s, 0, False, False, solids)
        if dead:
            return None
        if down and s[ph.VX] == 0 and s[ph.DASH] == 0:
            cx, cy = (s[ph.X] + ph.PW / 2) / ph.TS, (s[ph.Y] + ph.PH / 2) / ph.TS
            if box.x0 - 1 <= cx <= box.x1 + 2 and box.y0 - 1 <= cy <= box.y1 + 2:
                return s
            return None
    return None


def stationary(s: tuple, solids) -> bool:
    """Standing still: letting go of the keys leaves the player where it is (on
    the ground gravity pulls it a fraction of a pixel down and the ground puts it
    back every few frames), so any moment to start is as good as another."""
    if s[ph.VX] != 0 or s[ph.DASH] != 0 or s[ph.AIR] > 4:
        return False
    x, y = int(s[ph.X]), int(s[ph.Y])
    landed = False
    for _ in range(6):
        s, down, dead = ph.apply_frame(s, 0, False, False, solids)
        if dead or (int(s[ph.X]), int(s[ph.Y])) != (x, y):
            return False
        landed |= down
    return landed


def stable_waypoints(route: list, arrivals: list, solids) -> list[bool]:
    """Where a player can stop: ground waypoints, and those where the designed run,
    letting go of the keys on arrival, comes to rest (a maze cell's floor; not
    the top of a chimney)."""
    return [wp.ground or settle(s, wp, solids) is not None for wp, s in zip(route, arrivals)]


def element_spans(stable: list[bool]) -> list[tuple[int, int]]:
    """(first, last) waypoint index of each element: up to the next stable waypoint."""
    spans, a = [], 0
    for k, ok in enumerate(stable):
        if ok or k == len(stable) - 1 or k - a + 1 >= MAX_SPAN:
            spans.append((a, k))
            a = k + 1
    return spans


def element_label(route: list, a: int, b: int) -> str:
    return route[b].label if a == b else f"{route[a].label} .. {route[b].label}"


# --- the most forgiving way through an element ---------------------------------

IDLE = CAP + 1  # frames a player stands still after walking somewhere, before the next move


def _run(s: tuple, frames: list, solids) -> tuple | None:
    for m, j, d in frames:
        s, _down, dead = ph.apply_frame(s, m, j, d, solids)
        if dead:
            return None
    return s


def come_to_rest(s: tuple, solids) -> tuple[list, tuple] | None:
    """Let go of the keys until standing still, then stand for IDLE frames more:
    (frames, state), or None if that falls or dies."""
    frames = []
    for _ in range(SETTLE):
        s, down, dead = ph.apply_frame(s, 0, False, False, solids)
        if dead:
            return None
        frames.append((0, False, False))
        if down and stationary(s, solids):
            idle = [(0, False, False)] * IDLE
            s = _run(s, idle, solids)
            return (frames + idle, s) if s is not None else None
    return None


def walks(start: tuple, toward: int, solids) -> list[tuple[list, tuple]]:
    """Places on the ground a player standing at `start` can walk to and stop at
    first: the spot itself, the edge towards the goal, a few steps short of it and
    a run-up back the other way. (frames, state) each."""
    rest = come_to_rest(start, solids)
    if rest is None:
        return []
    pre, here = rest
    out = [(pre, here)]
    y0 = here[ph.Y]
    for m, steps in ((toward, (4, 8, 16, 24, 32, 48, 64, 96, 128)), (-toward, (16, 32))):
        reached = []
        for k in steps:
            s = _run(here, [(m, False, False)] * k, solids)
            back = come_to_rest(s, solids) if s is not None else None
            if back is None or abs(back[1][ph.Y] - y0) > 1:
                break
            reached.append((pre + [(m, False, False)] * k + back[0], back[1]))
        if m == toward:
            out += reached[-1:] + reached[-3:-2] + reached[len(reached) // 2 - 1 : len(reached) // 2]
        else:
            out += reached
    seen, uniq = set(), []
    for frames, s in out:
        key = round(s[ph.X])
        if key not in seen:
            seen.add(key)
            uniq.append((frames, s))
    return uniq


def plan_through(start: tuple, goals: list, solids, cfg: tuple, max_expand: int) -> tuple[list | None, int]:
    """The route planner chained through `goals` with one setting (CONFIGS):
    (frames or None, search nodes spent)."""
    weight, durations, dash = cfg
    frames: list = []
    spent = 0
    s = start
    for goal in goals:
        res = plan_segment(
            s, goal, solids, weight=weight, durations=durations, allow_dash=dash, max_expand=max_expand - spent
        )
        spent += res.expanded
        if not res.ok:
            return None, spent
        frames += res.frames
        s = res.end
    return frames, spent


@dataclass
class Choice:
    frames: list
    windows: list
    score: float


DEBUG = False  # print where each better program of the search came from
SEARCH_NODES = 15000  # planner nodes the search for one element may spend (~5 s)
HARD = 6  # narrowest window (frames) below which an element is searched three times as long


def _apex_shift(start: tuple, frames: list, ev: Event, solids, reach: int = 24) -> int | None:
    """Frames to move a dash by to press it at the top of the jump it is in."""
    s = start
    vys = []
    for m, j, d in frames[: ev.frame + reach]:
        vys.append(s[ph.VY])
        s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
    best = None
    for i in range(max(1, ev.frame - reach), len(vys)):
        if vys[i - 1] < 0 <= vys[i] and (best is None or abs(i - ev.frame) < abs(best - ev.frame)):
            best = i
    return None if best is None or best == ev.frame else best - ev.frame


def most_forgiving(
    start: tuple, goals: list, solids, *, seeds: tuple = (), nodes: int = SEARCH_NODES, rounds: int = 3
) -> Choice | None:
    """The input program through `goals` from `start` whose presses leave the most
    room (`score`): planner programs with every setting, from where the player
    stands and from spots on the ledge walked to first, then improved by moving
    its tightest presses a few frames (a dash to the top of its jump) and
    planning the rest anew. Spends at most `nodes` planner search nodes. `seeds`
    are programs to start from (the designed route's, an earlier search's)."""
    best: Choice | None = None
    tried: set = set()
    spent = 0
    working: list = []  # settings that found a way

    def consider(frames, src=""):
        nonlocal best
        if frames is None:
            return False
        key = tuple(frames)
        if key in tried:
            return False
        tried.add(key)
        floor = None if best is None else best.score + LENGTH_COST * len(frames)
        ws = press_windows(start, frames, goals, solids, floor=floor)
        if ws is None:
            return False
        sc = score(ws, len(frames))
        if best is None or sc > best.score:
            best = Choice(frames, ws, sc)
            if DEBUG:
                print("    better:", src, round(sc, 3), narrowest(ws), "spent", spent)
            return True
        return False

    def plan(s, gs, cfg, budget):
        nonlocal spent
        budget = min(budget, nodes - spent)
        if budget <= 0:
            return None
        frames, used = plan_through(s, gs, solids, cfg, budget)
        spent += used
        return frames

    def done():
        return spent >= nodes or (best is not None and all(w.width >= IDLE for w in best.windows))

    for seed in seeds:
        consider(seed, "seed")
    gx = (goals[0].x0 + goals[0].x1 + 1) / 2 * ph.TS
    toward = 1 if gx >= start[ph.X] + ph.PW / 2 else -1
    still = stationary(start, solids)
    for cfg in CONFIGS:
        frames = plan(start, goals, cfg, nodes // 8)
        if frames is not None:
            working.append(cfg)
            consider(frames, f"planner {cfg}")
        if done():
            return best
    working = working[:3] or [CONFIGS[1]]
    if still or start[ph.AIR] <= 1:
        spots = walks(start, toward, solids)[1:]
        for pre, s in spots:
            for cfg in working:
                rest = plan(s, goals, cfg, nodes // 24)
                consider(pre + rest if rest is not None else None, f"walk {round(s[ph.X] - start[ph.X])} {cfg}")
            if done():
                return best
    for _round in range(rounds):
        if best is None or done():
            break
        improved = False
        moves = []
        for w in sorted(best.windows, key=lambda w: w.width)[:2]:
            if w.width >= IDLE:
                continue
            if w.event.kind == "dash":
                apex = _apex_shift(start, best.frames, w.event, solids)
                if apex is not None:
                    moves.append((w.event, apex))
            moves += [(w.event, delta) for delta in (-4, -2, -1, 1, 2, 4)]
        base = best.frames
        for ev, delta in moves:
            alt = shifted(base, ev, delta, False, start[ph.LASTM])
            if alt is None:
                continue
            cut = ev.frame + max(0, delta) + 1
            head = play(start, alt[:cut], goals, solids, limit=cut, record=True)
            if head.dead or not head.states:
                continue
            if head.ok:
                improved |= consider(alt[: head.frames], f"shift {ev} {delta}")
                continue
            for cfg in working[:2]:
                rest = plan(head.states[-1], goals[head.progress[-1] :], cfg, nodes // 40)
                improved |= consider(alt[:cut] + rest if rest is not None else None, f"repair {ev} {delta} {cfg}")
            if done():
                break
        if not improved:
            break
    return best


# --- a level, element by element -------------------------------------------------


@dataclass
class Element:
    label: str
    section: str
    first: int  # waypoint indices it spans
    last: int
    settled: bool  # starts standing still (else on the move, from the element before)
    frames: list  # the most forgiving program
    windows: list
    fatal: list  # per press: share of its misses no quick correction saves
    plan_frames: int  # frames the designed (fastest) route takes for it
    start: tuple = ()  # the state it is played from

    @property
    def narrowest(self) -> int:
        return narrowest(self.windows)

    @property
    def seconds(self) -> float:
        return len(self.frames) / 60

    def presses(self) -> list[tuple[int, float]]:
        return [(w.width, f) for w, f in zip(self.windows, self.fatal)]


def saved(s: tuple, solids, floor: float | None = None, frames: int = 240) -> bool:
    """Whether a player in trouble at `s` can still land somewhere: steer either
    way or not at all, jump once or not (after REACT frames, until then keep on).
    With `floor` (px), only a landing no lower than that counts: deeper down is a
    pit the element cannot be gone on from (a restart, as good as a death). A
    swimmer still alive in the water at the end is saved too: it can swim on."""
    water = getattr(solids, "water", None)
    for m in (-1, 0, 1):
        for jump_at in (None, 0, 8, 16):
            cur, at = s, jump_at
            dead = False
            for f in range(frames):
                mm = m if f >= REACT else cur[ph.LASTM]
                jump = at is not None and f >= REACT + at and ph.can_jump(cur, solids)
                if jump:
                    at = None
                cur, down, dead = ph.apply_frame(cur, mm, jump, False, solids)
                if dead:
                    break
                if down:
                    if floor is None or cur[ph.Y] + ph.PH <= floor:
                        return True
                    dead = True
                    break
            if not dead and water and ph.water_at(cur[ph.X], cur[ph.Y], water)[0] is not None:
                return True
    return False


def landing_floor(start: tuple, goals: list) -> float:
    """The lowest a player may land on in an element and still go on: a tile
    below the lower of where it starts and where it ends (px, feet)."""
    goal_bottom = (goals[-1].y1 + 1) * ph.TS
    return max(start[ph.Y] + ph.PH, goal_bottom) + ph.TS


def fatal_shares(windows: list, solids, floor: float | None = None) -> list[float]:
    """Per press, the share of its misses (just outside its window) that kill or
    end in a pit below `floor`."""
    per = []
    for w in windows:
        kills = [not saved(st, solids, floor) for _shift, _died, st in w.fails]
        per.append(sum(kills) / len(kills) if kills else None)
    known = [f for f in per if f is not None]
    mean = sum(known) / len(known) if known else 0.0
    return [mean if f is None else f for f in per]


def analyse_route(solids, spawn_px: tuple, route: list, plan_frames: list, segments: list, verbose=False) -> list:
    """Elements of a route with their most forgiving programs. `plan_frames` and
    `segments` ((start, n) per waypoint) are the designed route's plan."""
    from tools.worlds.assess import section_name
    from tools.worlds.route import LEAD_IN

    s = ph.spawn_state(*spawn_px)
    states = [s]
    for m, j, d in plan_frames:
        s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
        states.append(s)
    arrivals = [states[a + n] for a, n in segments]
    stable = stable_waypoints(route, arrivals, solids)
    s = states[LEAD_IN]
    settled = True
    out = []
    for a, b in element_spans(stable):
        goals = route[a : b + 1]
        pa, pb = segments[a][0], segments[b][0] + segments[b][1]
        seeds = [plan_frames[pa:pb]] if _same(s, states[pa]) else []
        t0 = time.time()
        choice = most_forgiving(s, goals, solids, seeds=seeds)
        if choice is None:  # from where the element before left off it cannot be done: as designed
            s, settled = states[pa], False
            choice = most_forgiving(s, goals, solids, seeds=[plan_frames[pa:pb]])
        if choice is None:
            raise RuntimeError(f"element {element_label(route, a, b)!r} cannot be played")
        if narrowest(choice.windows) < HARD:  # a hard one: look harder before calling it hard
            choice = most_forgiving(s, goals, solids, seeds=[choice.frames], nodes=3 * SEARCH_NODES, rounds=6)
        ws = press_windows(s, choice.frames, goals, solids)
        el = Element(
            element_label(route, a, b),
            section_name(route[b].label),
            a,
            b,
            settled,
            choice.frames,
            ws,
            fatal_shares(ws, solids, landing_floor(s, goals)),
            pb - pa,
            s,
        )
        out.append(el)
        if verbose:
            print(
                f"  {el.label[:44]:44s} {el.seconds:5.1f} s (route {el.plan_frames / 60:4.1f} s) "
                f"narrowest {el.narrowest:2d}  presses {sorted(w.width for w in ws)[:6]}  ({time.time() - t0:.1f} s)",
                flush=True,
            )
        end = play(s, choice.frames, goals, solids).end
        rest = settle(end, route[b], solids) if stable[b] else None
        s, settled = (rest, True) if rest is not None else (end, False)
    return out


def _same(a: tuple, b: tuple) -> bool:
    return _key(a) == _key(b)


# --- precision model ------------------------------------------------------


def p_hit(width: int, sigma: float, lapse: float = 0.0) -> float:
    """Chance to press within a window of `width` frames, aiming at its middle
    with a gaussian timing error of `sigma` frames; with chance `lapse` the press
    is a blunder instead (anywhere within CAP frames either way)."""
    if width >= FREE:
        return 1.0
    return (1 - lapse) * math.erf(width / (2 * math.sqrt(2) * sigma)) + lapse * width / FREE


def element_odds(widths_fatal: list, sigma: float, lapse: float = 0.0) -> tuple:
    """(chance to play an element through on one try, chance to die on it) from
    its presses' (window width, share of misses that kill)."""
    hit, survive = 1.0, 1.0
    for width, fatal in widths_fatal:
        p = p_hit(width, sigma, lapse)
        hit *= p
        survive *= 1 - (1 - p) * fatal
    die = min(1 - hit, 1 - survive)
    return hit, die


DEATH_S = 1.0 + RESPAWN_DEAD_THRESHOLD / 60  # seconds a death costs on top of the try: the fall, the fade
PAUSE_WINDOW = 4  # a press this tight (frames) makes a player stop and look first (the profile's pause)


def element_costs(elements: list, profile: dict) -> tuple[list, list, list]:
    """Per element: seconds spent on it per arrival (tries until through or dead,
    deaths included), chance to get through it without dying, chance to die."""
    costs, passes, deaths = [], [], []
    for el in elements:
        hit, die = element_odds(el.presses(), profile["sigma"], profile.get("lapse", 0.0))
        hit = max(hit, 1e-6)
        t = el.seconds * profile["pace"] + profile.get("pause", 0.0) * sum(
            1 for w in el.windows if w.width <= PAUSE_WINDOW
        )
        costs.append((t + die * DEATH_S) / (hit + die))
        passes.append(hit / (hit + die))
        deaths.append(die / (hit + die))
    return costs, passes, deaths


def first_clear(elements: list, profile: dict, cuts=()) -> dict:
    """Expected minutes and deaths until a player with `profile` clears a level
    for the first time: a death sends the player back to the last checkpoint
    passed (`cuts`: indices of the elements the level's banners stand before),
    with the manual checkpoint P put where it saves the most, and without it."""
    from tools.worlds.assess import time_to_beat

    costs, passes, _deaths = element_costs(elements, profile)
    n = len(costs)
    fixed = sorted({c for c in cuts if 0 < c < n})

    def stretches(extra):
        edges = [0, *sorted({*fixed, *extra}), n]
        return [(a, b) for a, b in zip(edges, edges[1:]) if b > a]

    def minutes(extra=()):
        return sum(time_to_beat(costs[a:b], passes[a:b]) for a, b in stretches(extra)) / 60

    def deaths(extra=()):
        total = 0.0
        for a, b in stretches(extra):
            reach = math.prod(passes[a:b])
            total += 1 / reach - 1 if reach > 0 else float("inf")
        return total

    best_p = min(range(1, n), key=lambda k: minutes([k])) if n > 1 else 0
    clean = sum(el.seconds * profile["pace"] for el in elements)
    return {
        "minutes": round(minutes([best_p]), 2),
        "deaths": round(deaths([best_p]), 2),
        "p_at": elements[best_p].label if elements else "",
        "minutes_without_p": round(minutes(), 2),
        "deaths_without_p": round(deaths(), 2),
        "clean_run_minutes": round(clean / 60, 2),
        "first_try": round(math.prod(passes), 3),
    }


def exposed_presses(elements: list) -> int:
    """Presses whose misses mostly kill (no quick correction lands the player),
    free ones left out: each costs a share of a death however wide its window."""
    return sum(1 for e in elements for w, f in zip(e.windows, e.fatal) if f >= 0.5 and w.width < FREE)


WINDOW_BANDS = (2, 4, 8, 12)  # narrowest-window classes of the per-level histogram


def window_profile(elements: list) -> dict:
    """Histogram of the elements' narrowest windows: how many need a press within
    <= 2, <= 4, <= 8, <= 12 frames, and how many are free of tight presses."""
    hist = {f"le{b}": 0 for b in WINDOW_BANDS}
    hist["free"] = 0
    for el in elements:
        w = el.narrowest
        band = next((b for b in WINDOW_BANDS if w <= b), None)
        hist[f"le{band}" if band else "free"] += 1
    return hist


def checkpoint_cuts(elements: list, boxes: list, solids) -> list[int]:
    """Index of the element each checkpoint banner (px boxes) stands before: the
    one whose program touches it first (or after it, if touched late in it)."""
    cuts = []
    for x0, y0, x1, y1 in boxes:
        for k, el in enumerate(elements):
            hit = None
            s = el.start
            for i, (m, j, d) in enumerate(el.frames):
                s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
                rx, ry = int(s[ph.X]), int(s[ph.Y])
                if rx < x1 and x0 < rx + ph.PW and ry < y1 and y0 < ry + ph.PH:
                    hit = i
                    break
            if hit is not None:
                cuts.append(k if hit < len(el.frames) / 2 else k + 1)
                break
    return sorted(cuts)


def summary(level, elements: list, route_frames: int, boxes=(), solids=None, profiles=None) -> dict:
    """A level's window profile and first-clear estimates, JSON-ready."""
    profiles = profiles or PROFILES
    cuts = checkpoint_cuts(elements, boxes, solids) if boxes else []
    hardest = sorted(elements, key=lambda e: (e.narrowest, -len(e.windows)))[:5]
    by_section: dict = {}
    for el in elements:
        by_section.setdefault(el.section, []).append(el.narrowest)
    return {
        "level": level,
        "elements": len(elements),
        "route_seconds": round(route_frames / 60, 1),
        "forgiving_seconds": round(sum(e.seconds for e in elements), 1),
        "windows": window_profile(elements),
        "presses_le4": sum(1 for e in elements for w in e.windows if w.width <= 4),
        "exposed": exposed_presses(elements),
        "hardest": [[e.label, e.narrowest, round(max(e.fatal, default=0.0), 2)] for e in hardest],
        "sections": [[k, min(v), len(v)] for k, v in sorted(by_section.items(), key=lambda kv: min(kv[1]))],
        "checkpoints": cuts,
        "first_clear": {name: first_clear(elements, prof, cuts) for name, prof in profiles.items()},
        "element_list": [
            [e.label, e.narrowest, round(e.seconds, 2), [w.width for w in e.windows], [round(f, 2) for f in e.fatal]]
            for e in elements
        ],
    }


def analyse_map(map_id: int, verbose: bool = False) -> tuple:
    """(elements, designed route frames, checkpoint banner boxes, terrain) of a saved level."""
    from tools.worlds.assess import _map_data, checkpoint_boxes, load_map
    from tools.worlds.route import load_plan

    solids, _tiles = load_map(map_id)
    plan = load_plan(map_id)
    els = analyse_route(solids, plan["spawn"], plan["waypoints"], plan["frame_list"], plan["segments"], verbose)
    return els, len(plan["frame_list"]), checkpoint_boxes(_map_data(map_id)), solids


def profile_map(map_id: int, verbose: bool = False, profiles=None) -> dict:
    """Window profile and first-clear estimates of a saved level (with a designed route)."""
    els, n, boxes, solids = analyse_map(map_id, verbose)
    return summary(map_id, els, n, boxes, solids, profiles)


def profile_built(lv, verbose: bool = False, profiles=None) -> dict | None:
    """The same for a tools.worlds.builder.Level that only exists in memory
    (None if its route cannot be planned)."""
    from tools.worlds.assess import checkpoint_boxes
    from tools.worlds.route import plan_route

    solids = lv.solids()
    spawn = (lv.spawn_tile[0] * ph.TS, lv.spawn_tile[1] * ph.TS)
    res = plan_route(solids, spawn, lv.route, solids.kill_y, verbose=False)
    if not res.ok:
        return None
    segments = [(start, n) for _label, start, n, _exp in res.segments]
    els = analyse_route(solids, spawn, lv.route, res.frames, segments, verbose)
    boxes = checkpoint_boxes({"tilemap": {}, "offgrid": lv.offgrid})
    return summary(lv.map_id, els, len(res.frames), boxes, solids, profiles)


def print_summary(r: dict) -> None:
    """A level's window profile as readable lines."""
    w = r["windows"]
    print(
        f"  level {r['level']}: {r['elements']} elements, narrowest window <=2: {w['le2']}, <=4: {w['le4']}, "
        f"<=8: {w['le8']}, <=12: {w['le12']}, free: {w['free']}; {r['exposed']} exposed presses "
        f"(route {r['route_seconds']} s, played safe {r['forgiving_seconds']} s)"
    )
    hard = ", ".join(f"{label} {n}" for label, n, _f in r["hardest"] if n < FREE)
    print(f"  level {r['level']} hardest elements (narrowest window, frames): {hard or '-'}")
    for name, fc in r["first_clear"].items():
        print(
            f"  level {r['level']} {name}: ~{fc['minutes']} min to the first clear, ~{fc['deaths']} deaths, "
            f"first try {round(100 * fc['first_try'])} % (clean run {fc['clean_run_minutes']} min; "
            f"without P {fc['minutes_without_p']} min)"
        )
