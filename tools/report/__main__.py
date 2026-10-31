"""Collect the data behind the technical report.

Every figure of the report reads a JSON file written here, so a number on
the page traces back to a command and a commit. Nothing here changes
baselines, maps, plans or player data. Run it in a clean clone: the real
game and the planner run as they do in development, and `difficulty` wants
data/replays/8.json to 10.json (your best runs, the human reference).

Usage:
    python -m tools.report all --out out/report
    python -m tools.report netbench levels --out out/report
    python -m tools.worlds.play 11 12 ... 25 --out out/play
    python -m tools.report play --play-dir out/play --out out/report
    python tools/mp_netbench.py --out head.json
    python -m tools.report netbench --netbench-run head.json --out out/report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Callable, Dict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _determinism(args: argparse.Namespace) -> dict:
    from tools.report import determinism

    return determinism.collect()


def _difficulty(args: argparse.Namespace) -> dict:
    from tools.report import levels

    return levels.difficulty(args.out)


def _levels(args: argparse.Namespace) -> dict:
    from tools.report import levels

    return levels.collect()


def _netbench(args: argparse.Namespace) -> dict:
    from tools.report import netbench

    return netbench.collect(args.netbench_run)


def _performance(args: argparse.Namespace) -> dict:
    from tools.report import performance

    return performance.collect()


def _physics(args: argparse.Namespace) -> dict:
    from tools.report import physics

    return physics.collect(args.frames)


def _play(args: argparse.Namespace) -> dict:
    from tools.report import levels

    return levels.play_results(args.play_dir)


def _routes(args: argparse.Namespace) -> dict:
    from tools.report import routes

    return routes.collect(args.out)


def _search(args: argparse.Namespace) -> dict:
    from tools.report import search

    return search.collect(args.out, args.search_level, args.search_label, args.search_occurrence)


def _throughput(args: argparse.Namespace) -> dict:
    from tools.report import throughput

    return throughput.collect()


SECTIONS: Dict[str, Callable[[argparse.Namespace], dict]] = {
    "netbench": _netbench,
    "determinism": _determinism,
    "levels": _levels,
    "physics": _physics,
    "difficulty": _difficulty,
    "throughput": _throughput,
    "performance": _performance,
    "play": _play,
    "routes": _routes,
    "search": _search,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect the data behind the technical report")
    parser.add_argument("sections", nargs="+", choices=[*SECTIONS, "all"])
    parser.add_argument("--out", default="out/report", help="directory for the JSON files")
    parser.add_argument("--netbench-run", help="results of tools/mp_netbench.py --out, shown as the current state")
    parser.add_argument("--frames", type=int, default=20000, help="frames per map of the physics check")
    parser.add_argument("--play-dir", default="out/play", help="--out of a tools.worlds.play run")
    parser.add_argument("--search-level", type=int, default=21, help="level of the traced route segment")
    parser.add_argument("--search-label", default="chimney", help="waypoint label of the traced route segment")
    parser.add_argument("--search-occurrence", type=int, default=0, help="which of several waypoints of that label")
    args = parser.parse_args()

    os.chdir(REPO)
    sys.path.insert(0, REPO)
    os.makedirs(args.out, exist_ok=True)
    names = list(SECTIONS) if "all" in args.sections else args.sections
    for name in names:
        path = os.path.join(args.out, f"{name}.json")
        data = SECTIONS[name](args)
        with open(path, "w") as f:
            json.dump(data, f, indent=1)
        print(f"{name}: {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
