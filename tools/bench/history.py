"""Backfill the benchmark history from git: `python -m tools.bench history`.

    python -m tools.bench history                  # the default selection (below)
    python -m tools.bench history --all            # every commit that changed code
    python -m tools.bench history --commits a1b2c3d 4e5f6a7
    python -m tools.bench history --list           # only show what would be measured

The default selection is the last commit of every day that changed code
(*.py, maps, images), every `perf` commit and HEAD: one point per working
day, all the performance work, ~65 commits. Measuring every commit would
add merges, docs-only and broken in-between commits for 5x the time.

Each commit is checked out in a throwaway clone (the repo itself is not
touched) and measured with the probe (black box, works back to the first
commit; median of --runs). Commits from SUITE_FROM on also run one full
session (the campaign), where the replays in tools/trailer_replays/ still
play the levels to the finish. Results go to docs/benchmarks/history.json
after every commit; commits already measured on this machine are skipped,
so the history can be extended (or resumed) at any time.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from .runner import HISTORY, ROOT, git, keep_awake, load, machine, run_probes, run_sessions, save_json

# First commit whose maps and physics let the trailer replays finish their levels
SUITE_FROM = "c70d5b2"
CODE = ["*.py", "data/maps/*", "data/images/*"]
# Older commits tracked data/settings.json; play level 0 with the default kit everywhere
NORMALIZE = {"selected_level": 0, "selected_skin": 0, "selected_weapon": 0, "selected_gear": 0}


def select(all_commits: bool = False) -> list[str]:
    """Commits to measure, oldest first."""
    log = git("log", "--no-merges", "--reverse", "--format=%h %cs %s", "--", *CODE).splitlines()
    rows = [line.split(" ", 2) for line in log]
    if all_commits:
        picked = {sha for sha, _, _ in rows}
    else:
        last_of_day = {day: sha for sha, day, _ in rows}  # later rows overwrite: the day's last commit
        picked = set(last_of_day.values()) | {sha for sha, _, subject in rows if subject.startswith("perf")}
    picked.add(git("rev-parse", "--short", "HEAD"))
    order = git("log", "--reverse", "--format=%h").splitlines()
    return [sha for sha in order if sha in picked]


def has_suite(clone: str, sha: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", SUITE_FROM, sha], cwd=clone).returncode == 0


def reset(clone: str) -> None:
    """Back to the commit as checked in (bytecode kept, like an installed game)."""
    subprocess.run(["git", "reset", "-q", "--hard"], cwd=clone, check=True)
    subprocess.run(["git", "clean", "-q", "-fdx", "-e", "__pycache__"], cwd=clone, check=True)
    settings = os.path.join(clone, "data", "settings.json")
    if os.path.exists(settings):
        try:
            with open(settings) as f:
                data = json.load(f)
            data.update({k: v for k, v in NORMALIZE.items() if k in data})
            with open(settings, "w") as f:
                json.dump(data, f)
        except (ValueError, OSError):
            pass


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="python -m tools.bench history", description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="every commit that changed code")
    ap.add_argument("--commits", nargs="+", metavar="REV", help="exactly these commits")
    ap.add_argument("--runs", type=int, default=3, help="probe runs per commit (median, default 3)")
    ap.add_argument("--no-suite", action="store_true", help="probe only, skip the campaign sessions")
    ap.add_argument("--force", action="store_true", help="measure again commits already in the history")
    ap.add_argument("--list", action="store_true", help="only list the selected commits")
    args = ap.parse_args(argv)

    commits = [git("rev-parse", "--short", c) for c in args.commits] if args.commits else select(args.all)
    history = load(HISTORY, {"machine": machine(), "entries": []})
    if history.get("machine") != machine():
        sys.exit(f"{os.path.relpath(HISTORY, ROOT)} was measured on another machine; move it away to start over")
    done = {e["commit"]: e for e in history["entries"]}
    todo = [c for c in commits if args.force or c not in done]
    for c in commits:
        if args.list:
            print(c, git("log", "-1", "--format=%cs %s", c), "(measured)" if c in done else "")
    if args.list:
        print(f"{len(commits)} selected, {len(todo)} to measure")
        return
    print(f"{len(commits)} commits selected, {len(todo)} to measure ({args.runs} probe runs each)")

    keep_awake()
    clone = tempfile.mkdtemp(prefix="ninja-bench-history-")
    try:
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", ROOT, clone], check=True)
        t_start = time.time()
        for i, sha in enumerate(todo):
            t0 = time.time()
            subprocess.run(["git", "checkout", "-q", "-f", "--detach", sha], cwd=clone, check=True)
            subprocess.run([sys.executable, "-m", "compileall", "-q", clone], capture_output=True)
            date, subject = git("log", "-1", "--format=%cI%x00%s", sha).split("\0")
            entry: dict = {"commit": sha, "date": date, "subject": subject}
            try:
                entry["probe"] = run_probes(args.runs, root=clone, reset=lambda: reset(clone))
            except Exception as e:  # noqa: BLE001 - a broken commit is a result too
                entry["probe"] = {"error": str(e)[-500:]}
            if not args.no_suite and has_suite(clone, sha):
                try:
                    suite = run_sessions(1, quick=False, root=clone, log=lambda *a: None, reset=lambda: reset(clone))
                    entry["suite"] = suite["metrics"]
                    entry["suite_quick"] = False
                    if suite["errors"]:
                        entry["suite_errors"] = suite["errors"]
                except Exception as e:  # noqa: BLE001
                    entry["suite_errors"] = {"session": str(e)[-500:]}
            history["entries"] = [e for e in history["entries"] if e["commit"] != sha] + [entry]
            history["entries"].sort(key=lambda e: e["date"])
            save_json(HISTORY, history)
            p = entry["probe"]
            left = (time.time() - t_start) / (i + 1) * (len(todo) - i - 1)
            print(
                f"[{i + 1}/{len(todo)}] {sha} {date[:10]} {subject[:44]:44} "
                + (f"frame {p['frame_p50_ms']:.2f} ms" if "frame_p50_ms" in p else p.get("error", "no gameplay")[:40])
                + (
                    f" | campaign {entry['suite']['frame.p50_ms']:.2f} ms"
                    if "frame.p50_ms" in entry.get("suite", {})
                    else ""
                )
                + f" ({time.time() - t0:.0f} s, ~{left / 60:.0f} min left)",
                flush=True,
            )
    finally:
        shutil.rmtree(clone, ignore_errors=True)
    from . import report

    report.write()
    print("BENCHMARKS.md, docs/benchmarks/*.svg and docs/benchmarks/dashboard.html rebuilt")
