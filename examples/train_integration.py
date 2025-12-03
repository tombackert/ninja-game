"""Distributed Training Integration Example

This script demonstrates how to use the `TrainingAdapter` to interface
with a hypothetical external RL training loop (like Ray RLLib or Stable Baselines).

It performs one "training iteration" (collection + mock update).
"""

import time
import random
from scripts.training_adapter import RayRLLibAdapter


def mock_train_step():
    """Simulate a gradient update step."""
    time.sleep(0.01)
    return {"loss": random.random() * 0.1}


def run_training_loop(iterations=10):
    print("Initializing Training Adapter...")
    env = RayRLLibAdapter(config={"seed": 100})

    print(f"Starting {iterations} training iterations...")
    start_time = time.time()

    for i in range(iterations):
        # 1. Data Collection Phase
        obs, _ = env.reset()
        done = False
        truncated = False
        steps = 0

        while not (done or truncated) and steps < 100:  # Limit steps for quick test
            action = random.randint(0, 7)
            obs, reward, done, truncated, info = env.step(action)
            steps += 1

        # 2. Training Phase
        stats = mock_train_step()

        if i % 2 == 0:
            print(f"Iter {i}: Collected {steps} steps. Loss: {stats['loss']:.4f}")

    duration = time.time() - start_time
    print(f"Training complete in {duration:.2f}s")


if __name__ == "__main__":
    run_training_loop()
