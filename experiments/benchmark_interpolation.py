import time
import random
from scripts.network.interpolation import SnapshotBuffer, interpolate_entity
from dataclasses import dataclass


@dataclass
class MockState:
    pos: list
    velocity: list
    flip: bool
    action: str


def run_benchmark(iterations=100000):
    buf = SnapshotBuffer(max_size=20)

    # Fill buffer
    for i in range(20):
        state = MockState([float(i), float(i)], [1.0, 1.0], False, "idle")
        buf.push(i * 10, state)

    start = time.perf_counter()

    for i in range(iterations):
        # Query random times (mostly inside buffer, some outside)
        tick = random.uniform(-10, 210)
        prev, nxt, t = buf.get_surrounding_snapshots(tick)

        if prev and nxt:
            _ = interpolate_entity(prev[1], nxt[1], t)

    end = time.perf_counter()

    duration = end - start
    avg_us = (duration / iterations) * 1_000_000

    print(f"Interpolation Benchmark ({iterations} ops)")
    print(f"Total Time: {duration:.4f}s")
    print(f"Avg per Op: {avg_us:.4f} us")

    # Ops per frame (budget 1ms for 100 remote entities)
    ops_in_1ms = 1000 / avg_us * 1000
    print(f"Ops per 1ms budget: {ops_in_1ms:.0f}")


if __name__ == "__main__":
    run_benchmark()
