# Benchmark Brainstorm

**Date:** 2026-10-18
**Status:** Open question

The benchmark suite (`python -m tools.bench`, results in [BENCHMARKS.md](../BENCHMARKS.md)) plays levels 0-6 the way a player does, times every frame, load and stall, checks that the simulation stays deterministic, and has a history back to the first commit. This document keeps the question of whether it is worth its weight, and the answer as it stands.

---

## 1. The Question

> sind die metriken / benchmark im jetzigen stand wertvoll für die weitere entwicklung oder ist sie jetzt einfach schon zu klobig und overpowered um uns in der entwicklung einen vorteil zu bringen?

Are the metrics and the benchmark, as they stand, valuable for further development, or already too clunky and overpowered to give us an advantage?

## 2. Answer: Yes, It Is Valuable

The value is already shown, not only in theory:

- **Regression found:** 68c2a6d (camera glide) costs +1.3 ms per frame instead of the stated ~0.4 ms. Nobody would have noticed without the suite.
- **Cause of the HUD cost found:** also 68c2a6d.
- **Perf fixes backed by numbers:** respawn -67%, level finish -71%, pause -98%, each as a number instead of a feeling.
- **False alarm cleared:** the suspected load-time regression of 3fcaedc was only measurement noise.
- **Determinism check:** it fires when an optimization changes how the game plays. Very useful for a perf workflow.

## 3. Where It Is Clunky

- **Run time:** a full run takes ~4 minutes. Too long to run after every change.
- **Too many metrics:** 28 of them is more than anyone reads day to day. Text-cache evictions, replay loading, GC collections, peak memory or training throughput are rarely needed.
- **Sensitive to noise:** start-up values and outliers move with the machine's state (battery, sleep, VS Code in the background). The marking of noisy metrics helps, but the numbers still need some judgement to read.
- **Code size:** ~2200 lines is a lot for a hobby project. When APIs such as `GameState`, `LevelCompleteState` or `trailer.Run` change, `session.py` has to follow.
- **History machinery:** mostly a one-time investment. It costs nothing to keep; it just sits there.

## 4. Recommendation: Keep It, Use It in Three Tiers

1. **Day to day:** `--quick` (~15 s) after changes to rendering or loading, looking at ~5 values only: frame p50/p99, level start, respawn and the first level start.
2. **Before a perf commit or a feature merge:** a full run with `--check`, plugged in.
3. **After a real gain:** `--save`, so the curve in BENCHMARKS.md keeps growing.

## 5. If It Feels Too Heavy: Slimming Down

- Cut the default output to the core metrics and put the rest behind an `--all`.
- Show the score only as a side note.
- Make the quick mode the default.

Leave the measuring core alone: the campaign with real replays plus the determinism check is exactly what made the findings above possible.

---

## 6. Related Question

> also ist das game jetzt zuletzt garnicht schneller sondern sogar langsamer geworden?

So did the game recently not get faster but even slower?

For the cost of a frame, yes. Across the perf work of 2026-10-17 the campaign frame p50 went from 2.82 ms (eb55db4) to 3.20 ms (89764d0): the world silhouette (aef97cf) and the font cache (277aa65) saved 0.74 ms together, the camera glide (68c2a6d) added 1.3 ms. Everything a player waits for got much faster in the same day: respawn 34 -> 11 ms, level finish 45 -> 13 ms, pause frame 9.7 -> 0.15 ms. At 3.2 ms a frame still uses only ~19% of the 16.7 ms a 60 FPS frame may take.
