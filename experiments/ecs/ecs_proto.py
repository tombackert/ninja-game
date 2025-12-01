import time
import random
from dataclasses import dataclass
from typing import List, Optional, Dict

# --- ECS Core ---

@dataclass(slots=True)
class Position:
    x: float
    y: float

@dataclass(slots=True)
class Velocity:
    vx: float
    vy: float

@dataclass(slots=True)
class Lifetime:
    frames: int

class World:
    def __init__(self):
        self.next_id = 0
        self.entities: List[int] = []
        # Component stores (ID -> Component)
        self.positions: Dict[int, Position] = {}
        self.velocities: Dict[int, Velocity] = {}
        self.lifetimes: Dict[int, Lifetime] = {}

    def create_entity(self) -> int:
        e_id = self.next_id
        self.next_id += 1
        self.entities.append(e_id)
        return e_id

    def destroy_entity(self, e_id: int):
        # In a real ECS, we'd swap-remove or mark for deletion
        # Python dict deletion is O(1) usually
        if e_id in self.positions: del self.positions[e_id]
        if e_id in self.velocities: del self.velocities[e_id]
        if e_id in self.lifetimes: del self.lifetimes[e_id]
        # self.entities.remove(e_id) # O(N) - slow, skip for benchmark pure update speed

# --- Systems ---

def movement_system(world: World):
    # Join Position + Velocity
    # In Python, iterating dict items is fast, but joining is the cost.
    # Naive join:
    for e_id, vel in world.velocities.items():
        if e_id in world.positions:
            pos = world.positions[e_id]
            pos.x += vel.vx
            pos.y += vel.vy

def lifetime_system(world: World):
    to_destroy = []
    for e_id, life in world.lifetimes.items():
        life.frames -= 1
        if life.frames <= 0:
            to_destroy.append(e_id)
    
    for e_id in to_destroy:
        world.destroy_entity(e_id)

# --- Benchmark ---

def run_benchmark(entity_count=5000, steps=100):
    world = World()
    
    print(f"Initializing {entity_count} entities...")
    for _ in range(entity_count):
        e = world.create_entity()
        world.positions[e] = Position(random.random()*100, random.random()*100)
        world.velocities[e] = Velocity(random.random()-0.5, random.random()-0.5)
        world.lifetimes[e] = Lifetime(random.randint(50, 200))

    print(f"Running {steps} simulation steps...")
    start_time = time.time()
    
    for _ in range(steps):
        movement_system(world)
        lifetime_system(world)
        
    end_time = time.time()
    duration = end_time - start_time
    print(f"Total time: {duration:.4f}s")
    print(f"Avg step: {(duration/steps)*1000:.2f}ms")
    print(f"Entities remaining: {len(world.lifetimes)}")

if __name__ == "__main__":
    run_benchmark()
