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

## Results

| Mode | Time (ms/frame) | Size (KB/frame) |
| :--- | :--- | :--- |
| **Baseline** (No Capture) | 0.0000 | 0 |
| **FULL Snapshot** | 0.6990 | 30.10 |
| **LITE Snapshot** | 0.5502 | 0.33 |

## Analysis

### 1. Storage Efficiency
The LITE mode achieves a **98.9% reduction** in storage size (0.33KB vs 30KB per frame).
*   **Impact:** A 60-second run at 60fps (3600 frames) would take:
    *   FULL: ~108 MB (Unacceptable for a replay file)
    *   LITE: ~1.2 MB (Perfectly acceptable)
*   **Conclusion:** The LITE mode is **mandatory** for the Ghost system to prevent massive disk usage.

### 2. Runtime Performance
The LITE mode is **~1.27x faster** than FULL mode (0.55ms vs 0.70ms).
*   **Why not faster?** The `SnapshotService.capture()` method currently iterates over all 100 enemies to build the initial `SimulationSnapshot` object *before* the `ReplayRecording.capture_frame` method strips them out.
*   **Bottleneck:** The cost is dominated by object creation (`EntitySnapshot`) in the capture phase, not the serialization phase.
*   **Optimization Opportunity:** We could pass a flag to `SnapshotService.capture(optimized=True)` to skip iterating enemies entirely, which would likely drop the time to ~0.05ms.

## Recommendation for Future
While the current implementation (0.55ms/frame) is acceptable (3% of a 16ms frame budget at 60fps), we can optimize further by pushing the filtering logic *into* the `SnapshotService`.

Current Status: **Approved**. The storage savings alone justify the architecture.
