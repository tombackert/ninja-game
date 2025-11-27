#!/usr/bin/env python3
"""
Performance Benchmark Tool for Ninja Game.

Usage:
    python3 tools/benchmark.py

This script:
1. Enables performance logging via environment variable.
2. Launches the game.
3. Analyzes the generated CSV log after the game exits.
"""

import os
import sys
import csv
import json
import statistics
import time

# Ensure we can import app from root
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.insert(0, root_dir)

LOG_FILE = os.path.join(root_dir, "performance_data.csv")


def analyze_log(filename: str):
    """Reads the CSV log and prints a performance report."""
    if not os.path.exists(filename):
        print(f"No log file found at {filename}")
        return

    work_ms = []
    full_ms = []
    fps = []
    particles = []
    enemies = []

    last_timestamp = None

    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    w = float(row['work_ms'])
                    f_val = float(row['full_ms']) if row['full_ms'] else 0.0
                    current_timestamp = float(row['timestamp'])

                    # Calculate FPS from timestamp delta
                    if last_timestamp is not None:
                        delta = current_timestamp - last_timestamp
                        if delta > 0:
                            current_fps = 1.0 / delta
                            fps.append(current_fps)

                    last_timestamp = current_timestamp

                    counts = json.loads(row['counts'])

                    work_ms.append(w)
                    full_ms.append(f_val)
                    particles.append(counts.get('particles', 0))
                    enemies.append(counts.get('enemies', 0))
                except (ValueError, json.JSONDecodeError):
                    continue
    except Exception as e:
        print(f"Error reading log file: {e}")
        return

    if not work_ms:
        print("No valid samples found in log.")
        return

    count = len(work_ms)

    # Statistics
    avg_fps = statistics.mean(fps) if fps else 0.0
    min_fps = min(fps) if fps else 0.0
    max_fps = max(fps) if fps else 0.0
    p01_fps = sorted(fps)[int(len(fps) * 0.01)] if fps else 0.0

    avg_work = statistics.mean(work_ms)
    max_work = max(work_ms)

    valid_full = [f for f in full_ms if f > 0]
    avg_full = statistics.mean(valid_full) if valid_full else 0.0

    # Report
    print("\n" + "=" * 40)
    print(f" PERFORMANCE REPORT")
    print("=" * 40)
    print(f"Total Frames: {count}")
    print("-" * 20)
    print(f"FPS (Calculated):")
    print(f"  Avg:     {avg_fps:.2f}")
    print(f"  Max:     {max_fps:.2f}")
    print(f"  Min:     {min_fps:.2f}")
    print(f"  1% Low:  {p01_fps:.2f}")
    print("-" * 20)
    print(f"Frame Times (ms):")
    print(f"  Avg Work (CPU): {avg_work:.2f} ms")
    print(f"  Max Work (CPU): {max_work:.2f} ms")
    print(f"  Avg Full Frame: {avg_full:.2f} ms")

    # Spikes
    spikes = [w for w in work_ms if w > 16.0]
    print("-" * 20)
    if spikes:
        print(f"WARNING: {len(spikes)} CPU spikes detected (>16ms).")
    else:
        print("Status: Clean. No CPU spikes (>16ms) detected.")

    # Load
    max_parts = max(particles) if particles else 0
    print("-" * 20)
    print(f"Peak Load:")
    print(f"  Particles: {max_parts}")
    print(f"  Enemies:   {max(enemies) if enemies else 0}")

    if max_parts > 10:
        threshold = max_parts * 0.5
        high_load_work = [w for w, p in zip(work_ms, particles) if p > threshold]
        if high_load_work:
            avg_high = statistics.mean(high_load_work)
            print(f"  Avg CPU @ >50% particles: {avg_high:.2f} ms")

    print("=" * 40 + "\n")


def main():
    # Clean previous log
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    # Set env var for app
    os.environ["PERF_LOG_FILE"] = LOG_FILE

    print(f"Starting benchmark...")
    print(f"Logging to: {LOG_FILE}")
    print("Play the game. Close window or Quit to finish.")

    try:
        import app

        app.main()
    except KeyboardInterrupt:
        print("\nBenchmark interrupted.")
    except Exception as e:
        print(f"\nGame crashed: {e}")

    print("\nProcessing data...")
    analyze_log(LOG_FILE)

    # Cleanup option
    # os.remove(LOG_FILE)


if __name__ == "__main__":
    main()
