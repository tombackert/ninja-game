# Snapshot System Performance Analysis

**Date:** 2025-12-01
**Experiment:** `experiments/snapshots/benchmark_snapshot.py`

## Goal
Assess the runtime cost and memory footprint of the Replay/Ghost system's snapshotting mechanism to verify the necessity and impact of the "Lite" (Optimized) mode.

## Methodology
*   **Environment:** Python 3.12, single-threaded.
*   **Scenario:** A heavy scene with 1 Player, **100 Enemies**, and **20 Projectiles**.
*   **Metric 1 (Time):** Average execution time per `capture_frame` call (in milliseconds).
*   **Metric 2 (Size):** Serialized JSON size per frame (in KB).
*   **Modes:**
    *   **FULL:** Captures all entities (used for Save/Load, AI, Netcode).
    *   **LITE:** Captures only Player state (used for Ghost visuals).

## Results (Iteration 2 - Push Filtering Down)

| Mode | Time (ms/frame) | Size (KB/frame) | Speedup |
| :--- | :--- | :--- | :--- |
| **Baseline** (No Capture) | 0.0000 | 0 | - |
| **FULL Snapshot** | 0.7022 | 30.09 | 1.0x |
| **LITE Snapshot** | **0.0102** | **0.33** | **68.57x** |

## Analysis

### 1. Storage Efficiency
The LITE mode achieves a **98.9% reduction** in storage size (0.33KB vs 30KB per frame).
*   **Impact:** A 60-second run at 60fps (3600 frames) would take:
    *   FULL: ~108 MB (Unacceptable for a replay file)
    *   LITE: ~1.2 MB (Perfectly acceptable)
*   **Conclusion:** The LITE mode is **mandatory** for the Ghost system to prevent massive disk usage.

### 2. Runtime Performance
The optimized LITE mode is **~68x faster** than FULL mode (0.01ms vs 0.70ms).
*   **Why:** By pushing the `optimized=True` flag into `SnapshotService.capture`, we skip iterating over the enemy/projectile lists entirely. This avoids the O(N) object creation overhead.
*   **Impact:** 0.01ms is negligible (0.06% of a 16ms frame). This means we can afford to snapshot frequently (e.g., 6Hz or even 30Hz) without frame drops.

## Conclusion
The snapshot system is now highly optimized for both storage and runtime performance. The `optimized` flag is a critical feature for the Ghost system.

Current Status: **Optimized & Approved**.
