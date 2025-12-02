import multiprocessing
import time
from typing import Any, Dict, List, Tuple
from scripts.training_env import TrainingEnv

def _worker_run(env_kwargs: Dict[str, Any], steps: int, queue: multiprocessing.Queue):
    """
    Worker function to run a single environment instance.
    """
    env = TrainingEnv(**env_kwargs)
    env.reset()
    
    total_reward = 0.0
    obs_count = 0
    
    # Simple random policy for benchmark
    import random
    
    for _ in range(steps):
        action = random.randint(0, 7)
        obs, reward, done, info = env.step(action)
        total_reward += reward
        obs_count += 1
        if done:
            env.reset()
            
    queue.put({"reward": total_reward, "steps": obs_count})

class BatchSimulation:
    """
    Manages parallel execution of TrainingEnv instances.
    """
    def __init__(self, num_envs: int = 4):
        self.num_envs = num_envs

    def run_batch(self, steps_per_env: int = 1000) -> Dict[str, Any]:
        queue = multiprocessing.Queue()
        processes = []
        
        start_time = time.time()
        
        for i in range(self.num_envs):
            p = multiprocessing.Process(
                target=_worker_run,
                args=({"seed": 42 + i, "level_id": 0}, steps_per_env, queue)
            )
            processes.append(p)
            p.start()
            
        results = []
        for _ in range(self.num_envs):
            results.append(queue.get())
            
        for p in processes:
            p.join()
            
        end_time = time.time()
        total_time = end_time - start_time
        
        total_steps = sum(r["steps"] for r in results)
        
        return {
            "total_steps": total_steps,
            "wall_time": total_time,
            "sps": total_steps / total_time if total_time > 0 else 0,
            "results": results
        }

if __name__ == "__main__":
    # Simple CLI test
    batch = BatchSimulation(num_envs=4)
    stats = batch.run_batch(steps_per_env=500)
    print(f"Batch Run: {stats['total_steps']} steps in {stats['wall_time']:.2f}s")
    print(f"Throughput: {stats['sps']:.2f} steps/sec")
