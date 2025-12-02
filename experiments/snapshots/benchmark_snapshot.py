import time
import random
import json
from dataclasses import asdict
from scripts.snapshot import SnapshotService, SimulationSnapshot
from scripts.replay import ReplayManager, ReplayRecording
from scripts.entities import Player, Enemy
from unittest.mock import MagicMock

# --- Setup ---

class MockGame:
    def __init__(self, entity_count=50):
        self.players = []
        self.enemies = []
        self.projectiles = []
        self.dead = 0
        self.transition = 0
        
        # Create entities to make the snapshot heavy
        p = MagicMock(spec=Player)
        p.id = 0
        p.pos = [100.0, 100.0]
        p.velocity = [0.0, 0.0]
        p.action = "idle"
        p.flip = False
        p.lives = 3
        p.air_time = 0
        p.jumps = 0
        p.wall_slide = False
        p.dashing = 0
        p.shoot_cooldown = 0
        self.players.append(p)
        
        for i in range(entity_count):
            e = MagicMock(spec=Enemy)
            e.id = i + 1
            e.pos = [i * 10.0, 100.0]
            e.velocity = [1.0, 0.0]
            e.flip = False
            e.action = "run"
            e.walking = 0
            self.enemies.append(e)
            
        # Add some projectiles
        for i in range(20):
            self.projectiles.append({
                "pos": [i*5.0, 50.0],
                "vel": [5.0, 0.0],
                "age": 0.1,
                "owner": "player"
            })

def run_benchmark(game, iterations=1000, mode="FULL"):
    """
    mode: 
      - FULL: standard capture (all entities)
      - LITE: optimized capture (player only)
      - NONE: baseline (no capture)
    """
    replay = ReplayRecording("1", "default", 0)
    
    start = time.perf_counter()
    
    for i in range(iterations):
        if mode == "NONE":
            pass # Simulate game loop overhead?
        else:
            snap = SnapshotService.capture(game)
            optimized = (mode == "LITE")
            replay.capture_frame(i, game.players[0], [], snap, optimized=optimized)
            
    end = time.perf_counter()
    
    total_time = end - start
    avg_ms = (total_time / iterations) * 1000
    
    # Measure data size of one frame
    size_bytes = 0
    if mode != "NONE":
        last_frame = replay.data.snapshots[str(iterations-1)]
        dump = json.dumps(last_frame)
        size_bytes = len(dump)
        
    return avg_ms, size_bytes

if __name__ == "__main__":
    game = MockGame(entity_count=100) # Heavy load
    
    print(f"--- Snapshot Benchmark (100 Enemies, 20 Projectiles) ---")
    
    # Warmup
    run_benchmark(game, 100, "FULL")
    
    ms_none, _ = run_benchmark(game, 1000, "NONE")
    print(f"Baseline (No Capture): {ms_none:.4f} ms/frame")
    
    ms_full, size_full = run_benchmark(game, 1000, "FULL")
    print(f"FULL Snapshot:       {ms_full:.4f} ms/frame | Size: {size_full/1024:.2f} KB")
    
    ms_lite, size_lite = run_benchmark(game, 1000, "LITE")
    print(f"LITE Snapshot:       {ms_lite:.4f} ms/frame | Size: {size_lite/1024:.2f} KB")
    
    print(f"\n--- Comparison ---")
    print(f"Speedup (Lite vs Full): {ms_full/ms_lite:.2f}x")
    print(f"Size Reduction:         {100 * (1 - size_lite/size_full):.2f}%")
