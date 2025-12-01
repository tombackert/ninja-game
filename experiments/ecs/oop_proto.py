import time
import random
from dataclasses import dataclass
from typing import List

# --- OOP Core ---

class Particle:
    __slots__ = ['x', 'y', 'vx', 'vy', 'life']
    def __init__(self, x, y, vx, vy, life):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life

    def update(self) -> bool:
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        return self.life <= 0

# --- Benchmark ---

def run_benchmark(entity_count=5000, steps=100):
    particles: List[Particle] = []
    
    print(f"Initializing {entity_count} entities (OOP)...")
    for _ in range(entity_count):
        p = Particle(
            random.random()*100, random.random()*100,
            random.random()-0.5, random.random()-0.5,
            random.randint(50, 200)
        )
        particles.append(p)

    print(f"Running {steps} simulation steps...")
    start_time = time.time()
    
    for _ in range(steps):
        # Standard update loop: update and filter dead
        # This is often O(N) allocation if creating new list, or O(N) swap-remove
        
        # Method 1: List comprehension (Idiomatic Python)
        # particles = [p for p in particles if not p.update()]
        
        # Method 2: In-place removal (usually slower in Python due to shifts, unless swap-remove)
        # Let's use the list comp method as it's common in the current codebase.
        
        new_particles = []
        for p in particles:
            kill = p.update()
            if not kill:
                new_particles.append(p)
        particles = new_particles
        
    end_time = time.time()
    duration = end_time - start_time
    print(f"Total time: {duration:.4f}s")
    print(f"Avg step: {(duration/steps)*1000:.2f}ms")
    print(f"Entities remaining: {len(particles)}")

if __name__ == "__main__":
    run_benchmark()
