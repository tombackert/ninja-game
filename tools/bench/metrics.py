"""What the benchmark reports: labels, units, which way is better, how much noise to allow.

Shared by the comparison table (`python -m tools.bench`), the regression
check (`--check`) and BENCHMARKS.md, so a metric reads the same everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str = "ms"
    lower_is_better: bool = True
    # A change counts as real only beyond both the relative and the absolute
    # tolerance (run-to-run noise on the same machine)
    tolerance: float = 0.10
    floor: float = 0.3
    score: bool = False  # part of the score
    group: str = ""
    help: str = ""


GROUPS = [
    ("play", "Gameplay (campaign: levels 0-6 played to the finish)"),
    ("stalls", "Loading and stalls (what the player waits for)"),
    ("screens", "Screens"),
    ("features", "Features and tools"),
    ("caches", "Caches and memory"),
]

METRICS = [
    # --- gameplay ----------------------------------------------------------
    Metric(
        "frame.p50_ms",
        "Frame p50",
        score=True,
        tolerance=0.08,
        floor=0.15,
        group="play",
        help="Typical cost of a gameplay frame (update + render + flip); budget 16.7 ms at 60 FPS",
    ),
    Metric(
        "frame.p99_ms",
        "Frame p99",
        score=True,
        floor=0.3,
        group="play",
        help="1 in 100 gameplay frames is slower than this",
    ),
    Metric(
        "frame.max_ms",
        "Frame max",
        tolerance=0.5,
        floor=3,
        group="play",
        help="Slowest gameplay frame (stalls such as respawns included)",
    ),
    Metric("update.p50_ms", "Update p50", floor=0.05, group="play", help="Simulation, camera, replay recording"),
    Metric("render.p50_ms", "Render p50", floor=0.15, group="play", help="Renderer.render, everything drawn"),
    Metric(
        "frame.budget_pct",
        "Budget used",
        unit="%",
        floor=1,
        group="play",
        help="Frame p50 as a share of the 16.7 ms a 60 FPS frame may take",
    ),
    Metric(
        "frames.over_budget",
        "Frames > 16.7 ms",
        unit="",
        tolerance=0.5,
        floor=2,
        group="play",
        help="Frames of the whole campaign (stalls included) that would miss a 60 Hz refresh",
    ),
    Metric(
        "frames.hitches",
        "Hitches > 25 ms",
        unit="",
        tolerance=0.5,
        floor=1,
        group="play",
        help="As the F1 HUD counts them: a visibly dropped frame",
    ),
    # --- stalls -------------------------------------------------------------
    Metric(
        "startup.to_menu_ms",
        "Start-up to menu",
        score=True,
        tolerance=0.25,  # reads files: other programs' disk and CPU use show up here first
        floor=25,
        group="stalls",
        help="Launching the game until the menu is on screen (interpreter start included)",
    ),
    Metric(
        "level_start.first_ms",
        "First level start",
        score=True,
        tolerance=0.25,
        floor=10,
        group="stalls",
        help="Menu -> Play: the frame that builds the first level and loads every asset",
    ),
    Metric(
        "level_start.p50_ms",
        "Level start p50",
        score=True,
        floor=1,
        group="stalls",
        help="Level-complete -> next level: the stalled frame, levels 1-6",
    ),
    Metric(
        "levels.start_max_ms",
        "Level start, worst level",
        score=True,
        floor=3,
        group="stalls",
        help="Slowest start of any level (all 13, the 4 MB maps of levels 9 and 10 included)",
    ),
    Metric(
        "levels.respawn_max_ms",
        "Respawn, worst level",
        score=True,
        floor=1,
        group="stalls",
        help="Dying and coming back: the respawn stall of the slowest level",
    ),
    Metric(
        "level_finish.max_ms",
        "Level finish, worst",
        floor=2,
        group="stalls",
        help="The frame that ends a level: replay and best time saved, level-complete screen built",
    ),
    Metric(
        "first_frame.render_p50_ms",
        "First frame render",
        floor=0.5,
        group="stalls",
        help="Rendering the first frame of a level (one-time work such as scaling the background)",
    ),
    Metric(
        "gc.max_pause_ms",
        "Longest GC pause",
        tolerance=0.5,
        floor=2,
        group="stalls",
        help="Python's garbage collector stops the game this long at most (campaign)",
    ),
    # --- screens ------------------------------------------------------------
    Metric("menu.frame_p50_ms", "Menu frame", score=True, floor=0.15, group="screens"),
    Metric("pause.frame_p50_ms", "Pause frame", score=True, floor=0.1, group="screens"),
    Metric("pause.first_ms", "Opening the pause screen", floor=2, group="screens"),
    Metric("complete_screen.frame_p50_ms", "Level-complete frame", floor=0.15, group="screens"),
    # --- features -----------------------------------------------------------
    Metric(
        "hud.overhead_ms",
        "F1 perf HUD cost",
        floor=0.2,
        tolerance=0.2,
        group="features",
        help="Extra frame time p50 with the HUD on (level 1 played with and without it)",
    ),
    Metric("replay.save_ms", "Save a replay", floor=0.5, group="features", help="Level 5's best run, ~4900 ticks"),
    Metric("replay.load_ms", "Load a replay", floor=0.5, group="features"),
    Metric(
        "sim.steps_per_s",
        "Training env",
        unit="steps/s",
        lower_is_better=False,
        score=True,
        floor=200,
        group="features",
        help="TrainingEnv.step() per second, headless (snapshot + features included)",
    ),
    # --- caches -------------------------------------------------------------
    Metric(
        "cache.text_hit_pct",
        "Text cache hits",
        unit="%",
        lower_is_better=False,
        tolerance=0.02,
        floor=1,
        group="caches",
        help="UI outline-text cache over the campaign",
    ),
    Metric(
        "hud.text_cache_hit_pct",
        "Text cache hits, HUD on",
        unit="%",
        lower_is_better=False,
        tolerance=0.02,
        floor=1,
        group="caches",
    ),
    Metric("cache.text_evictions", "Text cache evictions", unit="", tolerance=0.2, floor=50, group="caches"),
    Metric(
        "memory.campaign_peak_mb",
        "Peak memory",
        unit="MB",
        tolerance=0.1,
        floor=10,
        group="caches",
        help="Most memory the process held from start-up to the end of the campaign",
    ),
]

BY_KEY = {m.key: m for m in METRICS}

# Black-box probe (every version of the game, see probe.py)
PROBE = [
    Metric("frame_p50_ms", "Frame p50", floor=0.15),
    Metric("frame_p99_ms", "Frame p99", floor=0.3),
    Metric("startup_ms", "Start-up to first frame", floor=25),
    Metric("level_start_ms", "Level start (menu -> play)", floor=5),
    Metric("peak_rss_mb", "Peak memory", unit="MB", floor=10),
]


def score(metrics: dict, reference: dict) -> float | None:
    """1000 x the geometric mean of the speed-ups against the reference run.

    1000 = as fast as the reference; 1100 = 10% faster on average across
    the score metrics. Only for comparing runs on the same machine.
    """
    ratios = []
    for m in METRICS:
        if not m.score:
            continue
        now, ref = metrics.get(m.key), reference.get(m.key)
        if not now or not ref:
            continue
        ratios.append(ref / now if m.lower_is_better else now / ref)
    if not ratios:
        return None
    product = 1.0
    for r in ratios:
        product *= r
    return 1000 * product ** (1 / len(ratios))


def change(metric: Metric, before: float, now: float) -> str:
    """'better', 'worse' or 'same' beyond the metric's noise tolerance."""
    diff = now - before
    if abs(diff) <= metric.floor or abs(diff) <= metric.tolerance * abs(before):
        return "same"
    return "better" if (diff < 0) == metric.lower_is_better else "worse"


def fmt(metric: Metric, value) -> str:
    if value is None:
        return "-"
    unit = metric.unit
    if unit == "steps/s":
        return f"{value:,.0f} steps/s"
    if unit == "":
        return f"{value:.0f}"
    if unit in ("%", "MB"):
        return f"{value:.1f} {unit}" if unit == "MB" else f"{value:.1f}%"
    return f"{value:.2f} ms" if value < 100 else f"{value:.0f} ms"
