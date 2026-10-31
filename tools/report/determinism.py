"""Same seed, same inputs, same world: checked across separate processes.

Each case steps the training env with a seeded random policy and hashes
every observation, reward and end flag. Two fresh processes with different
Python hash seeds must print the same hash, and another seed must not.
Also re-runs the snapshot experiment, whose numbers the report quotes.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
from typing import Any, Dict

LEVELS = (0, 1, 14, 21)
SEEDS = (1, 2)
STEPS = 5000


def trace(level: int, seed: int) -> str:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("NINJA_GAME_TESTING", "1")
    os.environ["NINJA_LOG_LEVEL"] = "WARN"
    from scripts.training_env import TrainingEnv

    env = TrainingEnv(seed=seed, level_id=level, max_steps=STEPS)
    env.reset()
    rng = random.Random(seed)
    digest = hashlib.sha256()
    for _ in range(STEPS):
        obs, reward, done, _info = env.step(rng.randrange(8))
        digest.update(json.dumps([obs, reward, done], sort_keys=True).encode())
        if done:
            env.reset()
    return digest.hexdigest()[:16]


def _process(level: int, seed: int, hash_seed: int) -> str:
    env = dict(os.environ, PYTHONHASHSEED=str(hash_seed))
    cmd = [sys.executable, "-m", "tools.report.determinism", str(level), str(seed)]
    return subprocess.run(cmd, env=env, check=True, capture_output=True, text=True).stdout.split()[-1]


def _snapshots() -> Dict[str, float]:
    """FULL and LITE snapshots of the 100-enemy scene (experiments/snapshots)."""
    env = dict(os.environ, PYTHONPATH=".", NINJA_LOG_LEVEL="WARN", SDL_VIDEODRIVER="dummy")
    cmd = [sys.executable, "experiments/snapshots/benchmark_snapshot.py"]
    out = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True).stdout
    full = re.search(r"FULL Snapshot:\s+([\d.]+) ms/frame \| Size: ([\d.]+) KB", out)
    lite = re.search(r"LITE Snapshot:\s+([\d.]+) ms/frame \| Size: ([\d.]+) KB", out)
    if not full or not lite:
        raise RuntimeError(out)
    return {
        "full_ms": float(full.group(1)),
        "full_kb": float(full.group(2)),
        "lite_ms": float(lite.group(1)),
        "lite_kb": float(lite.group(2)),
    }


def collect() -> Dict[str, Any]:
    cases = []
    for level in LEVELS:
        for seed in SEEDS:
            first = _process(level, seed, 1)
            second = _process(level, seed, 2)
            cases.append({"level": level, "seed": seed, "hash": first, "same": first == second})
            print(f"level {level} seed {seed}: {'same' if first == second else 'DIFFERENT'}", flush=True)
    per_level = {c["level"]: {x["hash"] for x in cases if x["level"] == c["level"]} for c in cases}
    return {
        "steps_per_case": STEPS,
        "cases": cases,
        "all_same": all(c["same"] for c in cases),
        "seeds_differ": all(len(hashes) == len(SEEDS) for hashes in per_level.values()),
        "snapshots": _snapshots(),
    }


if __name__ == "__main__":
    print(trace(int(sys.argv[1]), int(sys.argv[2])))
