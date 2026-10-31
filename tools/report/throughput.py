"""Steps per second of the training env across 1 to 8 processes.

The workload is the one of the benchmark suite (level 0, random actions)
with one difference: resets count, since a training run pays for them. All
workers start at a barrier, so the wall time covers real parallel work and
no process start-up.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import platform
import random
import statistics
import time
from typing import Any, Dict

LEVEL = 0
STEPS = 20000
REPEATS = 5
WORKERS = (1, 2, 3, 4, 5, 6, 7, 8)


def _worker(barrier: Any, queue: Any, seed: int) -> None:
    os.environ["NINJA_LOG_LEVEL"] = "WARN"  # a line per reset would measure the terminal
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("NINJA_GAME_TESTING", "1")
    from scripts.training_env import TrainingEnv

    env = TrainingEnv(seed=seed, level_id=LEVEL)
    env.reset()
    rng = random.Random(seed)
    barrier.wait()
    for _ in range(STEPS):
        _, _, done, _ = env.step(rng.randrange(8))
        if done:
            env.reset()
    queue.put(time.perf_counter())


def run_once(workers: int) -> float:
    """Aggregate steps per second of `workers` envs running at once."""
    barrier = mp.Barrier(workers + 1)
    queue: Any = mp.Queue()
    procs = [mp.Process(target=_worker, args=(barrier, queue, 42 + i)) for i in range(workers)]
    for p in procs:
        p.start()
    barrier.wait()
    t0 = time.perf_counter()
    ends = [queue.get() for _ in procs]
    for p in procs:
        p.join()
    return workers * STEPS / (max(ends) - t0)


def collect() -> Dict[str, Any]:
    rows = []
    for workers in WORKERS:
        runs = [run_once(workers) for _ in range(REPEATS)]
        median = round(statistics.median(runs))
        rows.append({"workers": workers, "steps_per_s": median, "runs": [round(r) for r in runs]})
        print(f"{workers} workers: {rows[-1]['steps_per_s']} steps/s", flush=True)
    return {
        "machine": {"cpu": platform.processor() or platform.machine(), "cores": os.cpu_count()},
        "level": LEVEL,
        "steps_per_worker": STEPS,
        "repeats": REPEATS,
        "rows": rows,
    }
