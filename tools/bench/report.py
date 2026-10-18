"""BENCHMARKS.md and its charts, built from docs/benchmarks/{baseline,history}.json.

Rebuilt by `--save`, `history` and `report`; edit this file, not the output.
The charts are plain SVG (no plotting library), light and dark.
"""

from __future__ import annotations

import os
from dataclasses import replace
from html import escape

from .metrics import BY_KEY, GROUPS, METRICS, change, fmt, score
from .runner import BASELINE, DATA_DIR, HISTORY, ROOT, load

MD = os.path.join(ROOT, "BENCHMARKS.md")
FONT = 'system-ui,-apple-system,"Segoe UI",sans-serif'
# Light and dark charts are separate files with an opaque background: a
# media query inside one SVG follows the OS, not GitHub's theme setting
THEMES = {
    "light": dict(
        bg="#ffffff",
        ink="#0b0b0b",
        ink2="#52514e",
        muted="#898781",
        grid="#e1e0d9",
        axis="#c3c2b7",
        band="#0b0b0b",
        band_opacity=0.035,
        s1="#2a78d6",
        s2="#eb6834",
    ),
    "dark": dict(
        bg="#0d1117",
        ink="#f0efec",
        ink2="#c3c2b7",
        muted="#898781",
        grid="#2c2c2a",
        axis="#383835",
        band="#ffffff",
        band_opacity=0.05,
        s1="#3987e5",
        s2="#d95926",
    ),
}


def style(t: dict) -> str:
    return (
        f"<style>text{{font-family:{FONT}}}"
        f".t{{font-size:15px;font-weight:600;fill:{t['ink']}}} .s{{font-size:12px;fill:{t['ink2']}}}"
        f".a{{font-size:11px;fill:{t['muted']}}} .v{{font-size:11px;font-weight:600;fill:{t['ink']}}}"
        f".g{{stroke:{t['grid']};stroke-width:1}} .b{{stroke:{t['axis']};stroke-width:1}}"
        f".band{{fill:{t['band']};fill-opacity:{t['band_opacity']}}} .tick{{stroke:{t['muted']};stroke-width:1}}"
        f".l1{{stroke:{t['s1']}}} .d1{{fill:{t['s1']}}} .l2{{stroke:{t['s2']}}} .d2{{fill:{t['s2']}}}"
        f".ring{{stroke:{t['bg']};stroke-width:2}}</style>"
    )


ENTRY_LABEL = {"game.py": "game.py", "menu.py": "menu.py", "app.py": "app.py, state machine"}


# --- svg helpers -------------------------------------------------------------
def save_svg(name: str, w: float, h: float, body: list[str], title: str) -> str:
    """Write docs/benchmarks/<name>.svg and <name>-dark.svg; the markdown that shows the right one."""
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        t = THEMES[theme]
        with open(os.path.join(DATA_DIR, f"{name}{suffix}.svg"), "w") as f:
            f.write(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" '
                f'height="{h:.0f}" role="img"><title>{escape(title)}</title>{style(t)}'
                f'<rect width="100%" height="100%" rx="8" fill="{t["bg"]}"/>' + "".join(body) + "</svg>\n"
            )
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="docs/benchmarks/{name}-dark.svg">'
        f'<img alt="{escape(title)}" src="docs/benchmarks/{name}.svg"></picture>'
    )


def nice_max(v: float) -> tuple[float, float]:
    """A round axis maximum >= v and its tick step."""
    if v <= 0:
        return 1.0, 0.25
    mag = 10 ** len(str(int(v))) / 10 if v >= 1 else 0.1
    for step in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10):
        s = step * mag
        if v / s <= 5:
            top = s * -(-v // s)
            return top, s
    return v, v / 4


def num(v: float) -> str:
    return f"{v:.0f}" if v >= 10 or v == int(v) else f"{v:.1f}" if v >= 1 else f"{v:.2f}"


def line_chart(
    name: str, title: str, subtitle: str, entries: list[dict], series: list[tuple[str, int, list]], unit: str = "ms"
) -> str:
    """One line per series over the measured commits, in commit order.

    Background bands mark which entry point the version had; ticks at the
    bottom mark `perf` commits.
    """
    W, H, L, R, T, B = 760, 300, 48, 92, 62, 44
    pw, ph = W - L - R, H - T - B
    n = len(entries)
    x = [L + (pw * i / (n - 1) if n > 1 else pw / 2) for i in range(n)]
    vals = [v for _, _, vs in series for v in vs if v is not None]
    top, step = nice_max(max(vals) * 1.05 if vals else 1)

    def y(v: float) -> float:
        return T + ph - ph * v / top

    out = [
        f'<text class="t" x="{L}" y="22">{escape(title)}</text>',
        f'<text class="s" x="{L}" y="40">{escape(subtitle)}</text>',
    ]
    # eras: runs of commits with the same entry point, every other one shaded
    eras: list[list] = []  # [first index, last index, entry point]
    for i, e in enumerate(entries):
        entry = e.get("probe", {}).get("entry")
        if eras and eras[-1][2] == entry:
            eras[-1][1] = i
        else:
            eras.append([i, i, entry])
    half = (x[1] - x[0]) / 2 if n > 1 else pw / 2
    for k, (a, b, entry) in enumerate(eras):
        x0, x1 = max(L, x[a] - half), min(L + pw, x[b] + half)
        if k % 2 == 0:
            out.append(f'<rect class="band" x="{x0:.1f}" y="{T}" width="{x1 - x0:.1f}" height="{ph}"/>')
        if entry and x1 - x0 > 7 * len(ENTRY_LABEL.get(entry, entry)) + 8:
            out.append(f'<text class="a" x="{x0 + 4:.1f}" y="{T + 12}">{escape(ENTRY_LABEL.get(entry, entry))}</text>')
    # grid and y axis
    v = 0.0
    while v <= top + 1e-9:
        out.append(f'<line class="g" x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        out.append(f'<text class="a" x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{num(v)}</text>')
        v += step
    out.append(f'<text class="a" x="{L - 6}" y="{T - 8}" text-anchor="end">{unit}</text>')
    out.append(f'<line class="b" x1="{L}" x2="{L + pw}" y1="{T + ph}" y2="{T + ph}"/>')
    # x labels: the month, where it changes and there is room
    last_x = -99.0
    for i, e in enumerate(entries):
        month = e["date"][:7]
        if (i == 0 or month != entries[i - 1]["date"][:7]) and x[i] - last_x > 52:
            out.append(f'<text class="a" x="{x[i]:.1f}" y="{T + ph + 16}" text-anchor="middle">{month}</text>')
            last_x = x[i]
        if e.get("subject", "").startswith("perf"):
            out.append(f'<line class="tick" x1="{x[i]:.1f}" x2="{x[i]:.1f}" y1="{T + ph}" y2="{T + ph + 5}"/>')
    out.append(
        f'<text class="a" x="{L + pw}" y="{H - 6}" text-anchor="end">'
        "each step = one measured commit · ticks = perf commits</text>"
    )
    # lines, end dots, end labels
    for label, slot, vs in series:
        d, pen = [], "M"
        for xi, vi in zip(x, vs):
            if vi is None:
                pen = "M"
                continue
            d.append(f"{pen}{xi:.1f},{y(vi):.1f}")
            pen = "L"
        out.append(
            f'<path class="l{slot}" d="{" ".join(d)}" fill="none" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        last = max((i for i, vi in enumerate(vs) if vi is not None), default=None)
        if last is not None:
            cx, cy = x[last], y(vs[last])
            out.append(f'<circle class="d{slot} ring" cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>')
            if slot == series[0][1]:  # ends converge: only the main series is labelled, the legend names both
                out.append(f'<text class="v" x="{cx + 8:.1f}" y="{cy + 4:.1f}">{num(vs[last])} {unit}</text>')
                out.append(f'<text class="a" x="{cx + 8:.1f}" y="{cy + 17:.1f}">{escape(label)} now</text>')
    if len(series) > 1:  # legend
        lx = L + pw
        for label, slot, _ in reversed(series):
            w = 7 * len(label) + 22
            lx -= w
            out.append(f'<rect class="d{slot}" x="{lx:.1f}" y="13" width="12" height="3" rx="1.5"/>')
            out.append(f'<text class="s" x="{lx + 16:.1f}" y="19">{escape(label)}</text>')
    return save_svg(name, W, H, out, title)


def small_multiples(
    name: str, title: str, subtitle: str, entries: list[dict], panels: list[tuple[str, str, str]]
) -> str:
    """A small line chart per metric (each on its own scale) over the same commits."""
    W, T, cols, ph, gap = 760, 58, 3, 96, 28
    pw = (W - 32 - gap * (cols - 1)) / cols  # a panel: y labels, plot, end label
    plot_w = pw - 30 - 44
    rows = -(-len(panels) // cols)
    H = T + rows * (ph + 62)
    out = [
        f'<text class="t" x="16" y="22">{escape(title)}</text>',
        f'<text class="s" x="16" y="40">{escape(subtitle)}</text>',
    ]
    n = len(entries)
    for k, (key, label, unit) in enumerate(panels):
        ox = 16 + (k % cols) * (pw + gap) + 30
        oy = T + (k // cols) * (ph + 62) + 24
        vals = [e.get("suite", {}).get(key) for e in entries]
        have = [v for v in vals if v is not None]
        out.append(f'<text class="s" x="{ox - 30}" y="{oy - 8}">{escape(label)}</text>')
        if not have:
            continue
        top, step = nice_max(max(have) * 1.1)
        xs = [ox + plot_w * i / (n - 1 if n > 1 else 1) for i in range(n)]

        def y(v: float, oy=oy, top=top) -> float:
            return oy + ph - ph * v / top

        mid = (top / 2,) if (top / 2 / step).is_integer() else ()  # only a round middle tick
        for v in (0, *mid, top):
            out.append(f'<line class="g" x1="{ox}" x2="{ox + plot_w}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
            out.append(f'<text class="a" x="{ox - 5}" y="{y(v) + 4:.1f}" text-anchor="end">{num(v)}</text>')
        d, pen = [], "M"
        for xi, vi in zip(xs, vals):
            if vi is None:
                pen = "M"
                continue
            d.append(f"{pen}{xi:.1f},{y(vi):.1f}")
            pen = "L"
        out.append(f'<path class="l1" d="{" ".join(d)}" fill="none" stroke-width="2" stroke-linejoin="round"/>')
        last = max(i for i, v in enumerate(vals) if v is not None)
        out.append(f'<circle class="d1 ring" cx="{xs[last]:.1f}" cy="{y(vals[last]):.1f}" r="4"/>')
        out.append(f'<text class="v" x="{xs[last] + 7:.1f}" y="{y(vals[last]) + 4:.1f}">{num(vals[last])}</text>')
        out.append(f'<text class="a" x="{ox}" y="{oy + ph + 15}">{entries[0]["date"][:10]}</text>')
        out.append(f'<text class="a" x="{ox + plot_w}" y="{oy + ph + 15}" text-anchor="end">{unit}</text>')
    return save_svg(name, W, H, out, title)


def bars(name: str, title: str, subtitle: str, panels: list[tuple[str, dict[str, float]]]) -> str:
    """Horizontal bars per level, one panel per measure, value at the tip."""
    W, T, gap = 760, 58, 24
    pw = (W - 32 - gap * (len(panels) - 1)) / len(panels)
    rows = max(len(p[1]) for p in panels)
    H = T + 20 + rows * 20 + 10
    out = [
        f'<text class="t" x="16" y="22">{escape(title)}</text>',
        f'<text class="s" x="16" y="40">{escape(subtitle)}</text>',
    ]
    for k, (label, data) in enumerate(panels):
        ox = 16 + k * (pw + gap)
        out.append(f'<text class="s" x="{ox}" y="{T + 8}">{escape(label)}</text>')
        top = max(data.values()) or 1
        bar_x, bar_w = ox + 30, pw - 30 - 56
        for i, (lvl, v) in enumerate(data.items()):
            cy = T + 20 + i * 20
            w = max(2.0, bar_w * v / top)
            out.append(f'<text class="a" x="{ox + 22}" y="{cy + 12}" text-anchor="end">{escape(lvl)}</text>')
            out.append(
                f'<path class="d1" d="M{bar_x},{cy + 3}h{w - 3:.1f}a3,3 0 0 1 3,3v6a3,3 0 0 1 -3,3h{-(w - 3):.1f}z"/>'
            )
            out.append(f'<text class="v" x="{bar_x + w + 5:.1f}" y="{cy + 12}">{num(v)}</text>')
    return save_svg(name, W, H, out, title)


# --- the document ------------------------------------------------------------
# Metrics scanned for steps between consecutive commits of the campaign history
WATCH = [
    "frame.p50_ms",
    "frame.p99_ms",
    "startup.to_menu_ms",
    "level_start.first_ms",
    "level_start.p50_ms",
    "levels.start_max_ms",
    "levels.respawn_max_ms",
    "level_finish.max_ms",
    "first_frame.render_p50_ms",
    "menu.frame_p50_ms",
    "pause.frame_p50_ms",
    "hud.overhead_ms",
    "sim.steps_per_s",
    "memory.campaign_peak_mb",
]


def changes(suite: list[dict]) -> list[str]:
    """Steps from one measured commit to the next, beyond twice the noise
    tolerance (history points are a single session each)."""
    rows = []
    for before, after in zip(suite, suite[1:]):
        for key in WATCH:
            m = BY_KEY[key]
            b, a = before["suite"].get(key), after["suite"].get(key)
            if not b or a is None:
                continue
            wide = replace(m, tolerance=2 * m.tolerance, floor=2 * m.floor)
            verdict = change(wide, b, a)
            if verdict != "same":
                rows.append(
                    f"| `{after['commit']}` {escape(after['subject'][:60])} | {m.label} | {fmt(m, b)} → {fmt(m, a)} | "
                    f"{(a - b) / b * 100:+.0f}% {'better' if verdict == 'better' else '**worse**'} |"
                )
    if not rows:
        return []
    return [
        "Steps between consecutive measured commits, beyond twice the noise tolerance:",
        "",
        "| Commit | Metric | Before → after | Change |",
        "|---|---|---:|---:|",
        *rows,
        "",
    ]


def windows(entries: list[dict]) -> str:
    """When the window the probe ran in changed size."""
    seen, parts = None, []
    for e in entries:
        w = e["probe"].get("window")
        if w and w != seen:
            parts.append(f"{w[0]}x{w[1]} from {e['date'][:10]}")
            seen = w
    return ", ".join(parts)


def level_sort(d: dict) -> dict:
    return dict(sorted(d.items(), key=lambda kv: int("".join(c for c in kv[0] if c.isdigit()) or 0)))


def write() -> None:
    base = load(BASELINE, None)
    history = load(HISTORY, {"entries": []})
    entries = [e for e in history["entries"] if "frame_p50_ms" in e.get("probe", {})]
    os.makedirs(DATA_DIR, exist_ok=True)
    md = [
        "# Benchmarks",
        "",
        "<!-- Generated by `python -m tools.bench --save` (tools/bench/report.py); do not edit. -->",
        "",
    ]

    if base:
        m = base["metrics"]
        ref = base.get("reference")
        s = score(m, ref["metrics"]) if ref else None
        md += [
            f"**Reference point: `{base['commit']}`** ({base['subject']}), measured {base['measured'][:10]} on "
            f"{base['machine']['cpu']} · {base['env'].get('platform', '')} · Python {base['env'].get('python', '?')} · "
            f"pygame-ce {base['env'].get('pygame', '?')}, median of {base['sessions']} sessions."
            + (f" **Score {s:.0f}** (reference `{ref['commit']}` = 1000, higher is faster)." if s else ""),
            "",
            "Compare your working tree against it with `python -m tools.bench` (or `--check` to fail on a"
            " regression); record a new reference with `--save`.",
            "",
            "| | Now | |",
            "|---|---:|---|",
        ]
        headline = [
            ("frame.p50_ms", "of the 16.7 ms a 60 FPS frame may take" if "frame.budget_pct" in m else ""),
            ("frame.p99_ms", ""),
            ("startup.to_menu_ms", ""),
            ("level_start.first_ms", "menu -> Play, every asset loaded"),
            ("level_start.p50_ms", "next level, levels 1-6"),
            ("levels.start_max_ms", "slowest of all levels"),
            ("levels.respawn_max_ms", "slowest of all levels"),
            ("pause.frame_p50_ms", ""),
            ("hud.overhead_ms", "per frame with F1 on"),
            ("sim.steps_per_s", "headless, for training"),
        ]
        by_key = {mm.key: mm for mm in METRICS}
        for key, note in headline:
            if key in m:
                if key == "frame.p50_ms" and "frame.budget_pct" in m:
                    note = f"{m['frame.budget_pct']:.0f}% {note}"
                md.append(f"| {by_key[key].label} | **{fmt(by_key[key], m[key])}** | {note} |")
        if base.get("nondeterministic"):
            md += ["", f"> Simulation differed between sessions in {', '.join(base['nondeterministic'])}."]
        if base.get("wakes"):
            md += [
                "",
                f"> The machine slept {base['wakes']}x during this run. Medians and stalls hold up, but the tail"
                " (Frame max, Frames > 16.7 ms, Hitches) is likely inflated by slow frames around the wakes:"
                " run `--save` again plugged in and awake for a clean reference.",
            ]
        md.append("")

    if entries:
        first, last = entries[0], entries[-1]
        md += ["## Over time", ""]
        md.append(
            f"Every version of the game from the first commit ({first['date'][:10]}) to `{last['commit']}`"
            f" ({last['date'][:10]}), {len(entries)} commits, run as a black box: its own entry point, level 0,"
            " 10 s of scripted play, frames back to back (`tools/bench/probe.py`). Each version is measured with"
            " the maps, window and features it had, so this is what it cost to run that version - more game"
            " made later versions slower as much as code made them faster. The window it drew"
            f" (headless, so fullscreen versions got the dummy display's size): {windows(entries)}."
        )
        md.append("")
        md.append(
            line_chart(
                "history-frame",
                "Gameplay frame time, every version",
                "Black box: own entry point, level 0, 10 s of scripted play · lower is faster",
                entries,
                [
                    ("p50", 1, [e["probe"].get("frame_p50_ms") for e in entries]),
                    ("p99", 2, [e["probe"].get("frame_p99_ms") for e in entries]),
                ],
            )
        )
        md.append("")
        md.append(
            line_chart(
                "history-loading",
                "Start-up and level start, every version",
                "Launch to first frame, and the stalled frame from menu to level 0 · lower is faster",
                entries,
                [
                    ("start-up", 1, [e["probe"].get("startup_ms") for e in entries]),
                    ("level start", 2, [e["probe"].get("level_start_ms") for e in entries]),
                ],
            )
        )
        md.append("")
        suite = [e for e in history["entries"] if e.get("suite", {}).get("frame.p50_ms")]
        if len(suite) > 1:
            md += [
                f"The campaign (below) runs on every measured commit since `{suite[0]['commit']}`"
                f" ({suite[0]['date'][:10]}), the first whose maps let the recorded runs reach the finish:",
                "",
                small_multiples(
                    "history-campaign",
                    "Campaign, recent commits",
                    f"Levels 0-6 played to the finish, one session per commit,"
                    f" {suite[0]['date'][:10]} to {suite[-1]['date'][:10]}",
                    suite,
                    [
                        ("frame.p50_ms", "Frame p50", "ms"),
                        ("frame.p99_ms", "Frame p99", "ms"),
                        ("level_start.p50_ms", "Level start p50", "ms"),
                        ("levels.respawn_max_ms", "Respawn, worst level", "ms"),
                        ("pause.frame_p50_ms", "Pause frame", "ms"),
                        ("level_finish.max_ms", "Level finish, worst", "ms"),
                    ],
                ),
                "",
            ]
            md += changes(suite)

    if base and base.get("detail", {}).get("level_start_ms"):
        d = base["detail"]
        panels = [("Level start (ms)", level_sort(d["level_start_ms"])), ("Respawn (ms)", level_sort(d["respawn_ms"]))]
        if d.get("campaign_frame_ms"):
            panels.append(
                ("Frame p50 in the campaign (ms)", {k: v["p50"] for k, v in level_sort(d["campaign_frame_ms"]).items()})
            )
        md += [
            "## Per level",
            "",
            bars("levels", "Per level, now", f"Reference point {base['commit']} · lower is faster", panels),
            "",
        ]

    if base:
        m = base["metrics"]
        md += ["## All metrics", ""]
        for group, gtitle in GROUPS:
            rows = [mm for mm in METRICS if mm.group == group and mm.key in m]
            if not rows:
                continue
            md += [f"**{gtitle}**", "", "| Metric | Now | Noise | What it measures |", "|---|---:|---:|---|"]
            for mm in rows:
                noise = base.get("spread", {}).get(mm.key)
                md.append(
                    f"| {mm.label}{' ★' if mm.score else ''} | {fmt(mm, m[mm.key])} | "
                    f"{f'±{noise * 50:.0f}%' if noise is not None else ''} | {mm.help} |"
                )
            md.append("")
        md += [
            "★ = part of the score. Noise = half the spread between sessions of this run.",
            "",
            "Stalls the player waits for, slowest first (where to look next):",
            "",
            "| Stall | ms |",
            "|---|---:|",
        ]
        stalls = []
        d = base.get("detail", {})
        for lvl, v in d.get("level_start_ms", {}).items():
            stalls.append((f"Start of level {lvl}", v))
        for lvl, v in d.get("respawn_ms", {}).items():
            stalls.append((f"Respawn in level {lvl}", v))
        for lvl, v in d.get("campaign_finish_ms", {}).items():
            stalls.append((f"Finish of {lvl}", v))
        for key, label in (
            ("level_start.first_ms", "First level start of a session"),
            ("pause.first_ms", "Opening the pause screen"),
            ("startup.to_menu_ms", "Start-up to menu"),
            ("gc.max_pause_ms", "Longest GC pause"),
        ):
            if key in m:
                stalls.append((label, m[key]))
        for label, v in sorted(stalls, key=lambda s: -s[1])[:8]:
            md.append(f"| {label} | {v:.1f} |")
        md.append("")

    md += [
        "## How it works",
        "",
        "- **Campaign** (`tools/bench/session.py`): start-up, menu, Play, then levels 0-6 one after another through"
        " the level-complete screen, each played to the finish by a real best run from `tools/trailer_replays/`;"
        " level 2 is replayed once against the ghost of the run just finished, level 3 is paused for 1.5 s. The"
        " frame loop is app.py's without the frame pacer, so a frame's time is its cost (update + render + flip),"
        " headless at 1280x720. Every frame is labelled (play, level start, level finish, pause, menu ...).",
        "- **Isolated scenarios**: start and respawn of every level, level 1 with and without the F1 HUD, saving and"
        " loading a replay, `TrainingEnv` steps per second.",
        "- **Sandbox**: each session runs in a fresh process on links to the working tree, without data/'s player"
        " files (best times, coins, replays, settings), so it starts like a fresh install and never changes yours.",
        "- **Sleep**: a machine that sleeps mid-run (on battery, macOS does so after a minute idle) stops perf_counter"
        " but not the wall clock; the frames right after each wake run slow and are left out, and a probe run is"
        " repeated. The suite keeps the Mac from idle-sleeping (caffeinate), which does not stop maintenance sleep:"
        " plug in for long runs.",
        "- **Determinism check**: the outcome of every level (ticks, position, coins, enemies, a hash of the world"
        " picture) must match between sessions; a difference against the reference means gameplay changed.",
        "- **History** (`python -m tools.bench history`): older commits in a throwaway clone, measured with the"
        " black-box probe and, where the replays still finish, the campaign. Results: `docs/benchmarks/history.json`.",
        "- **Real window**: the benchmark measures CPU cost. Frame pacing and vsync in a real window are"
        " `tools/frame_pacing.py`'s job; the F1 HUD shows the same quantities live (Render = its *full* time,"
        " Interval, Hitches > 25 ms).",
        "",
        "Numbers are only comparable on the same machine. Close other heavy apps while measuring; a full run takes"
        " about 4 minutes (`--quick`: 15 s).",
        "",
    ]
    with open(MD, "w") as f:
        f.write("\n".join(md))
