"""Store-items end-to-end orchestrator (real process, isolated save data).

Builds a disposable sandbox working directory whose data/ contains:
- symlinks to the repo's static assets (images, maps, music, sfx, ...)
- fresh copies of the writable JSON save files (test wallet: 50000 coins)

Then spawns tools/items_e2e_bot.py as a real OS process with cwd=sandbox,
so every relative "data/..." read & write in the game hits the sandbox and
the developer's real save files stay untouched.

Usage:
    python tools/items_e2e.py [--out DIR] [--keep]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYMLINKS = ["images", "maps", "maps-old", "music", "sfx", "thumbnails", "font.ttf", "music.wav"]
COPIES = ["strings.json", "menu.json", "best_times.json"]
EMPTY_DIRS = ["saves", "replays"]

TEST_COLLECTABLES = {"coins": 50000}

TEST_SETTINGS = {
    "music_volume": 0.0,
    "sound_volume": 0.0,
    "selected_level": 0,
    "selected_editor_level": 0,
    "selected_skin": 0,
    "selected_weapon": 0,
    "selected_gear": 0,
    "playable_levels": {"0": True},
    "show_perf_overlay": False,
    "ghost_enabled": False,
    "ghost_mode": "best",
}


def build_sandbox(root: str) -> None:
    data = os.path.join(root, "data")
    os.makedirs(data)
    for name in SYMLINKS:
        src = os.path.join(REPO, "data", name)
        if os.path.exists(src):
            os.symlink(src, os.path.join(data, name))
    for name in COPIES:
        src = os.path.join(REPO, "data", name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(data, name))
    for name in EMPTY_DIRS:
        os.makedirs(os.path.join(data, name), exist_ok=True)
    with open(os.path.join(data, "collectables.json"), "w") as f:
        json.dump(TEST_COLLECTABLES, f)
    with open(os.path.join(data, "settings.json"), "w") as f:
        json.dump(TEST_SETTINGS, f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="output dir for report + screenshots")
    ap.add_argument("--keep", action="store_true", help="keep the sandbox dir")
    args = ap.parse_args()

    sandbox = tempfile.mkdtemp(prefix="items_e2e_")
    out = os.path.abspath(args.out) if args.out else os.path.join(sandbox, "out")
    os.makedirs(out, exist_ok=True)
    build_sandbox(sandbox)
    print(f"[e2e] sandbox: {sandbox}")
    print(f"[e2e] output:  {out}")

    env = dict(os.environ)
    env["PYTHONPATH"] = REPO
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")

    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, "tools", "items_e2e_bot.py"), "--out", out],
        cwd=sandbox,
        env=env,
        timeout=300,
    )

    report_path = os.path.join(out, "report.json")
    if os.path.exists(report_path):
        with open(report_path) as f:
            report = json.load(f)
        print(f"[e2e] {report['passed']} passed, {report['failed']} failed")
    else:
        print("[e2e] no report written — bot crashed?")

    if not args.keep and proc.returncode == 0:
        shutil.rmtree(sandbox, ignore_errors=True)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
