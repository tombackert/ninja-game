"""Benchmark suite: how fast the game starts, loads, plays and draws.

Usage (from the repo root):
    python -m tools.bench                  # 3 sessions, compared with the baseline
    python -m tools.bench --quick          # one short session, for a quick look
    python -m tools.bench --check          # exit 1 if a metric got worse beyond noise
    python -m tools.bench --save           # record as the new baseline + history point,
                                           # rebuild BENCHMARKS.md and its charts
    python -m tools.bench --save --reference   # ... and make it the score's 1000
    python -m tools.bench --profile        # cProfile one session, top functions
    python -m tools.bench history          # backfill the history from git (see history.py)
    python -m tools.bench report           # rebuild BENCHMARKS.md from the stored results

A session (session.py) plays a campaign through levels 0-6 the way a player
does, from start-up to the last level-complete screen, and times every
frame; a probe (probe.py) times any version of the game as a black box,
which is what the history back to the first commit is made of.

Every session runs in a fresh process in a throwaway sandbox: the working
tree's code and assets, but none of data/'s player files (best times,
coins, replays, settings), which the game would otherwise read and write.
Results are only comparable on the same machine; BENCHMARKS.md names it.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time

from .metrics import BY_KEY, GROUPS, METRICS, change, fmt, score
from .runner import (
    BASELINE,
    BENCH_DIR,
    HISTORY,
    ROOT,
    commit_info,
    keep_awake,
    load,
    machine,
    power_warning,
    run_probes,
    run_sessions,
    sandbox,
    save_json,
    working_tree_dirty,
)


# --- reporting -----------------------------------------------------------------
def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def compare(result: dict, baseline: dict | None) -> list[str]:
    """Print the results next to the baseline; return the metrics that got worse."""
    now = result["metrics"]
    before = (baseline or {}).get("metrics", {})
    worse = []
    # Sessions of this run disagree by more than the tolerance: something else
    # loaded the machine, so a change of these says nothing
    noisy = [m for m in METRICS if result.get("spread", {}).get(m.key, 0) / 2 > max(m.tolerance, 0.05)]
    if baseline:
        print(f"\nBaseline: {baseline['commit']} ({baseline['measured'][:10]}), {baseline['sessions']} sessions")
        if baseline.get("machine") != machine():
            print(color("  measured on another machine: differences say little", "33"))
    print(f"{'':34}{'baseline':>16}{'now':>16}{'change':>10}")
    for group, title in GROUPS:
        print(f"\n{title}")
        for m in [m for m in METRICS if m.group == group]:
            if m.key not in now and m.key not in before:
                continue
            b, n = before.get(m.key), now.get(m.key)
            mark = ""
            if b is not None and n is not None:
                verdict = change(m, b, n)
                pctg = (n - b) / b * 100 if b else 0
                mark = {"better": color(f"{pctg:+.1f}%", "32"), "worse": color(f"{pctg:+.1f}%", "31")}.get(
                    verdict, f"{pctg:+.1f}%"
                )
                if m in noisy:
                    mark = f"{pctg:+.1f}% ~"
                elif verdict == "worse":
                    worse.append(m.key)
            print(f"  {m.label:32}{fmt(m, b):>16}{fmt(m, n):>16}{mark:>10}")
    reference = (baseline or {}).get("reference")
    if reference:
        s = score(now, reference["metrics"])
        print(f"\nScore {s:.0f}  (reference {reference['commit']} = 1000; higher is faster)" if s else "")
    if noisy:
        print(
            color(
                "\n~ sessions disagreed (another program busy?), not counted: "
                + ", ".join(f"{m.label} ±{result['spread'][m.key] * 50:.0f}%" for m in noisy),
                "33",
            )
        )
    if result.get("wakes"):
        print(
            color(
                f"\nThe machine slept {result['wakes']}x: Frame max, Frames > 16.7 ms and Hitches are unreliable", "33"
            )
        )
    if result.get("nondeterministic"):
        print(color(f"\nSimulation differed between sessions in: {', '.join(result['nondeterministic'])}", "31"))
    if baseline and baseline.get("fingerprint"):
        changed = [k for k, v in result["fingerprint"].items() if baseline["fingerprint"].get(k, v) != v]
        if changed:
            print(color(f"\nGameplay changed against the baseline in: {', '.join(changed)}", "33"))
            print("  (same inputs, different outcome: expected after gameplay or map changes, a bug otherwise)")
    if result.get("errors"):
        print(color("\nScenarios that failed:", "31"))
        for name, err in result["errors"].items():
            print(f"  {name}: {err}")
    return worse


def save(result: dict, probe: dict, new_reference: bool = False) -> None:
    """Record a full run: new baseline, history point, BENCHMARKS.md."""
    info = commit_info()
    dirty = working_tree_dirty()
    old = load(BASELINE, None)
    baseline = {
        "commit": info["commit"] + ("+" if dirty else ""),
        "subject": info["subject"],
        "measured": datetime.datetime.now().isoformat(timespec="seconds"),
        "machine": machine(),
        **result,
        "probe": probe,
    }
    # The score's reference stays the first saved run on this machine
    if not new_reference and old and old.get("reference") and old.get("machine") == baseline["machine"]:
        baseline["reference"] = old["reference"]
    else:
        baseline["reference"] = {"commit": baseline["commit"], "metrics": result["metrics"]}
    save_json(BASELINE, baseline)

    history = load(HISTORY, {"machine": machine(), "entries": []})
    entry = {
        **info,
        "commit": baseline["commit"],
        "probe": probe,
        "suite": result["metrics"],
        "suite_quick": result["quick"],
    }
    history["entries"] = [e for e in history["entries"] if e["commit"] != entry["commit"]] + [entry]
    save_json(HISTORY, history)
    from . import report

    report.write()
    print(f"\nSaved: {os.path.relpath(BASELINE, ROOT)}, {os.path.relpath(HISTORY, ROOT)}, BENCHMARKS.md")


def profile(quick: bool) -> None:
    """cProfile a session and print where the time goes."""
    box = sandbox()
    prof = os.path.join(box, "session.prof")
    try:
        env = dict(os.environ, BENCH_T0=repr(time.perf_counter()))
        args = ["--root", box, "--out", os.path.join(box, "r.json")] + (["--quick"] if quick else [])
        subprocess.run(
            [sys.executable, "-m", "cProfile", "-o", prof, os.path.join(BENCH_DIR, "session.py"), *args],
            env=env,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        import pstats

        pstats.Stats(prof).sort_stats("tottime").print_stats(25)
    finally:
        shutil.rmtree(box, ignore_errors=True)


def main() -> None:
    if sys.argv[1:2] == ["history"]:  # its own options (and --help)
        from . import history

        history.main(sys.argv[2:])
        return
    ap = argparse.ArgumentParser(
        prog="python -m tools.bench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("command", nargs="?", choices=["run", "report"], default="run")
    ap.add_argument("--sessions", type=int, default=3, help="sessions to take the median of (default 3)")
    ap.add_argument("--quick", action="store_true", help="one short session (levels 0-2), for a quick look")
    ap.add_argument("--check", action="store_true", help="exit 1 if a metric got worse than the baseline")
    ap.add_argument("--save", action="store_true", help="record as baseline + history point, rebuild BENCHMARKS.md")
    ap.add_argument("--reference", action="store_true", help="with --save: make this run the score's 1000")
    ap.add_argument("--profile", action="store_true", help="cProfile a session instead")
    ap.add_argument("--json", metavar="PATH", help="also write the merged result to PATH")
    args, rest = ap.parse_known_args()

    if args.command == "report":
        from . import report

        report.write()
        print("BENCHMARKS.md and docs/benchmarks/*.svg rebuilt")
        return
    if rest:
        ap.error(f"unrecognized arguments: {' '.join(rest)}")
    if args.profile:
        profile(args.quick)
        return
    if args.save and args.quick:
        ap.error("--save records full runs only (drop --quick)")
    if args.reference and not args.save:
        ap.error("--reference only goes with --save")

    sessions = 1 if args.quick else args.sessions
    t0 = time.time()
    keep_awake()
    print(f"Benchmark: {sessions} session(s){' (quick)' if args.quick else ''} on {machine()['cpu']}")
    if power_warning():
        print(color(power_warning() or "", "33"))
    result = run_sessions(sessions, args.quick)
    probe = run_probes(3) if args.save else None
    print(f"done in {time.time() - t0:.0f} s")
    if args.json:
        save_json(os.path.abspath(args.json), result)
    baseline = load(BASELINE, None)
    worse = compare(result, baseline)
    if args.save:
        save(result, probe or {}, new_reference=args.reference)
    if args.check and worse:
        print(color(f"\nWorse than the baseline: {', '.join(BY_KEY[k].label for k in worse)}", "31"))
        sys.exit(1)


if __name__ == "__main__":
    main()
