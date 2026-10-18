"""Running sessions and probes in sandboxes, and merging their results.

Shared by the CLI (__main__.py) and the history backfill (history.py).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BENCH_DIR))
DATA_DIR = os.path.join(ROOT, "docs", "benchmarks")
BASELINE = os.path.join(DATA_DIR, "baseline.json")
HISTORY = os.path.join(DATA_DIR, "history.json")


def git(*args, cwd=ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def sandbox(src: str = ROOT) -> str:
    """A throwaway game root: links to the working tree's code and the
    assets git tracks in data/, but none of the player files there."""
    box = tempfile.mkdtemp(prefix="ninja-bench-")
    for name in os.listdir(src):
        if name not in ("data", ".git"):
            os.symlink(os.path.join(src, name), os.path.join(box, name))
    os.mkdir(os.path.join(box, "data"))
    for name in sorted({p.split("/")[1] for p in git("ls-files", "data", cwd=src).splitlines()}):
        os.symlink(os.path.join(src, "data", name), os.path.join(box, "data", name))
    return box


def spawn(script: str, root: str, extra=(), timeout=3600) -> dict:
    """Run session.py or probe.py on `root` in a fresh process; its JSON result."""
    fd, out = tempfile.mkstemp(suffix=".json", prefix="ninja-bench-")
    os.close(fd)
    os.remove(out)
    try:
        # The child times its start-up from here (perf_counter is system-wide)
        env = dict(os.environ, BENCH_T0=repr(time.perf_counter()))
        proc = subprocess.run(
            [sys.executable, os.path.join(BENCH_DIR, script), "--root", root, "--out", out, *extra],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        if not os.path.exists(out):
            raise RuntimeError(f"{script} wrote no result:\n{proc.stderr[-2000:]}")
        with open(out) as f:
            return json.load(f)
    finally:
        if os.path.exists(out):
            os.remove(out)


def run_sessions(n: int, quick: bool, root: str | None = None, log=print, reset=None) -> dict:
    """n sessions (each in a fresh sandbox, or in `root` after `reset()`), merged."""
    results = []
    for i in range(n):
        box = root or sandbox()
        if root and reset:
            reset()
        t0 = time.time()
        try:
            results.append(spawn("session.py", box, ["--quick"] if quick else []))
        finally:
            if root is None:
                shutil.rmtree(box, ignore_errors=True)
        r = results[-1]
        log(
            f"  session {i + 1}/{n}: {time.time() - t0:.0f} s, frame p50 "
            f"{r['metrics'].get('frame.p50_ms', float('nan')):.2f} ms"
            + (f", the machine slept {r['wakes']}x (frames after each wake left out)" if r.get("wakes") else "")
            + (f", errors in {', '.join(r['errors'])}" if r["errors"] else "")
        )
    return merge_sessions(results)


def run_probes(n: int, root: str | None = None, reset=None) -> dict:
    """n probe runs (each in a fresh sandbox, or in `root` after `reset()`), merged."""
    results = []
    for _ in range(n):
        for attempt in range(3):  # again if the machine slept during the run
            box = root or sandbox()
            if root and reset:
                reset()
            try:
                result = spawn("probe.py", box, timeout=1200)
            finally:
                if root is None:
                    shutil.rmtree(box, ignore_errors=True)
            if not result.get("slept"):
                break
        results.append(result)
    merged = {k: v for k, v in results[0].items() if not isinstance(v, (int, float)) or isinstance(v, bool)}
    merged.update(median([{k: v for k, v in r.items() if isinstance(v, (int, float))} for r in results]))
    merged["runs"] = n
    return merged


def merge_sessions(results: list[dict]) -> dict:
    """Median of every number across sessions; how far they spread; whether
    the simulation came out the same in each (it is deterministic)."""
    metrics = median([r["metrics"] for r in results])
    spread = {}
    for key, mid in metrics.items():
        vals = [r["metrics"][key] for r in results if key in r["metrics"]]
        if len(vals) > 1 and mid:
            spread[key] = (max(vals) - min(vals)) / abs(mid)
    prints = [r["fingerprint"] for r in results]
    unstable = sorted({k for p in prints for k in p if any(q.get(k) != p.get(k) for q in prints)})
    errors = {}
    for r in results:
        errors.update(r["errors"])
    return {
        "sessions": len(results),
        "quick": results[0]["quick"],
        "metrics": metrics,
        "spread": spread,
        "detail": median([{k: v for k, v in r["detail"].items() if k != "tracebacks"} for r in results]),
        "fingerprint": prints[0],
        "nondeterministic": unstable,
        "errors": errors,
        "env": results[0]["env"],
        "wakes": sum(r.get("wakes", 0) for r in results),
    }


def median(dicts: list[dict]) -> dict:
    """Key-wise median of numbers, recursing into nested dicts."""
    out: dict = {}
    for key in dict.fromkeys(k for d in dicts for k in d):
        vals = [d[key] for d in dicts if key in d]
        if all(isinstance(v, dict) for v in vals):
            out[key] = median(vals)
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            out[key] = statistics.median(vals)
        else:
            out[key] = vals[0]
    return out


def keep_awake() -> None:
    """Keep the machine from idle-sleeping while this process runs (macOS).

    Sleep stops perf_counter, so frames stay right, but the frames after a
    wake run slow; on battery a Mac idle-sleeps after a minute.
    """
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])


def power_warning() -> str | None:
    """A note when the power settings slow the machine down."""
    if sys.platform != "darwin":
        return None
    out = subprocess.run(["pmset", "-g"], capture_output=True, text=True).stdout
    if any(line.split()[:2] == ["lowpowermode", "1"] for line in out.splitlines()):
        return "Low Power Mode is on: numbers will be slower than the reference"
    return None


def machine() -> dict:
    cpu = platform.processor() or platform.machine()
    try:
        if sys.platform == "darwin":
            cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout
        elif os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo") as f:
                cpu = next((ln.split(":", 1)[1] for ln in f if ln.startswith("model name")), cpu)
    except OSError:
        pass
    return {"cpu": cpu.strip(), "cores": os.cpu_count(), "os": platform.platform(terse=True)}


def commit_info(rev: str = "HEAD", cwd: str = ROOT) -> dict:
    sha, date, subject = git("log", "-1", "--format=%h%x00%cI%x00%s", rev, cwd=cwd).split("\0")
    return {"commit": sha, "date": date, "subject": subject}


def working_tree_dirty() -> bool:
    """Uncommitted changes that can change what the game does (docs and the benchmark itself cannot)."""
    changed = [line[3:] for line in git("status", "--porcelain", "--untracked-files=no").splitlines()]
    return any(not (path.startswith(("docs/", "tools/bench/")) or path.endswith(".md")) for path in changed)


def load(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1, sort_keys=False)
        f.write("\n")
