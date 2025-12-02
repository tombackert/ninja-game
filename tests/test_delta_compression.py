import unittest
from scripts.snapshot import SimulationSnapshot, EntitySnapshot, ProjectileSnapshot
from scripts.network.delta import compute_delta, apply_delta

class TestSnapshotDelta(unittest.TestCase):
    def setUp(self):
        self.base = SimulationSnapshot(
            tick=100,
            rng_state=(3, (1, 2, 3), None),
            players=[
                EntitySnapshot("player", 0, [10.0, 10.0], [0.0, 0.0], False, "idle", lives=3)
            ],
            enemies=[
                EntitySnapshot("enemy", 1, [50.0, 50.0], [1.0, 0.0], True, "run")
            ],
            projectiles=[],
            score=100,
            dead_count=0,
            transition=0
        )

    def test_no_change(self):
        # Delta vs self should be empty
        delta = compute_delta(self.base, self.base)
        self.assertEqual(delta, {})
        
        # Apply empty delta should result in identical object
        new_snap = apply_delta(self.base, delta)
        self.assertEqual(new_snap, self.base)

    def test_simple_change(self):
        # Move player
        curr = SimulationSnapshot(
            tick=101,
            rng_state=self.base.rng_state,
            players=[
                EntitySnapshot("player", 0, [12.0, 10.0], [2.0, 0.0], False, "run", lives=3)
            ],
            enemies=self.base.enemies,
            projectiles=[],
            score=100, dead_count=0, transition=0
        )
        
        delta = compute_delta(self.base, curr)
        
        # Expect tick and player diff
        self.assertEqual(delta["tick"], 101)
        self.assertIn("players_diff", delta)
        self.assertEqual(delta["players_diff"][0]["pos"], [12.0, 10.0])
        self.assertEqual(delta["players_diff"][0]["action"], "run")
        self.assertNotIn("lives", delta["players_diff"][0]) # Unchanged
        
        # Apply
        restored = apply_delta(self.base, delta)
        self.assertEqual(restored, curr)

    def test_structural_change(self):
        # Add projectile
        curr = SimulationSnapshot(
            tick=101,
            rng_state=self.base.rng_state,
            players=self.base.players,
            enemies=self.base.enemies,
            projectiles=[
                ProjectileSnapshot([20.0, 20.0], 5.0, 0.0, "player")
            ],
            score=100, dead_count=0, transition=0
        )
        
        delta = compute_delta(self.base, curr)
        
        # Since lengths differ, full list is sent (fallback strategy)
        self.assertIn("projectiles", delta)
        self.assertEqual(len(delta["projectiles"]), 1)
        
        restored = apply_delta(self.base, delta)
        self.assertEqual(restored, curr)

if __name__ == '__main__':
    unittest.main()
