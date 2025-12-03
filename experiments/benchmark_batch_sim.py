import time
from scripts.training_env import TrainingEnv
from scripts.batch_sim import BatchSimulation


def run_benchmark():
    print("--- Batch Simulation Benchmark ---")

    # 1. Sequential Baseline
    print("Running Sequential Baseline (1 Env)...")
    env = TrainingEnv(seed=42)
    env.reset()
    start = time.time()
    steps = 2000
    for _ in range(steps):
        env.step(0)  # No-op
    end = time.time()
    seq_sps = steps / (end - start)
    print(f"Sequential: {seq_sps:.2f} steps/sec")

    # 2. Parallel Batch
    num_envs = 4
    steps_per_env = 2500  # Total 10000 steps
    print(f"Running Parallel Batch ({num_envs} Envs)...")
    batch = BatchSimulation(num_envs=num_envs)
    stats = batch.run_batch(steps_per_env=steps_per_env)
    par_sps = stats['sps']
    print(f"Parallel:   {par_sps:.2f} steps/sec")

    # 3. Analysis
    speedup = par_sps / seq_sps
    print(f"Speedup: {speedup:.2f}x")

    if speedup > 1.0:
        print("SUCCESS: Parallel execution improves throughput.")
    else:
        print("NOTE: Overhead might outweigh benefit for small step counts or single-core limits.")


if __name__ == "__main__":
    run_benchmark()
