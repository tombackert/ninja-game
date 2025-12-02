# Interpolation Performance Analysis

**Date:** 2025-12-01
**Experiment:** `experiments/benchmark_interpolation.py`

## Goal
Assess the performance of `SnapshotBuffer.get_surrounding_snapshots` and `interpolate_entity` to ensure they are efficient enough for smoothing multiple remote entities in a multiplayer context.

## Methodology
*   **Buffer:** 20 snapshots deep.
*   **Workload:** 100,000 random queries (simulating worst-case random access, though linear access is typical).
*   **Operation:** Retrieve surrounding snapshots + Lerp position/velocity.

## Results
*   **Avg per Op:** 1.87 us (microseconds)
*   **Throughput:** ~534,000 operations per second (per core).

## Analysis
*   **Budget:** In a typical 60fps frame (16ms), we allocate maybe 1-2ms for networking.
*   **Capacity:** With 1.87us per entity, we can interpolate **500+ entities** within a conservative 1ms budget.
*   **Conclusion:** The pure Python implementation using `deque` iteration is extremely fast for the expected scale (max 50-100 entities). No `numpy` or C optimization is required at this stage.

## Status
**Approved** for production use.
