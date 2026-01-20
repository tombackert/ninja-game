import unittest
from scripts.snapshot import SimulationSnapshot, EntitySnapshot, ProjectileSnapshot
from scripts.network.delta import compute_delta, apply_delta


class TestSnapshotDelta(unittest.TestCase):
    def setUp(self):
        self.base = SimulationSnapshot(
            tick=100,
            rng_state=(3, (1, 2, 3), None),
            players=[EntitySnapshot("player", 0, [10.0, 10.0], [0.0, 0.0], False, "idle", lives=3)],
            enemies=[EntitySnapshot("enemy", 1, [50.0, 50.0], [1.0, 0.0], True, "run")],
            projectiles=[],
            score=100,
            dead_count=0,
            transition=0,
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
            players=[EntitySnapshot("player", 0, [12.0, 10.0], [2.0, 0.0], False, "run", lives=3)],
            enemies=self.base.enemies,
            projectiles=[],
            score=100,
            dead_count=0,
            transition=0,
        )

        delta = compute_delta(self.base, curr)

        # Expect tick and player diff (ID-based matching: keyed by entity ID)
        self.assertEqual(delta["tick"], 101)
        self.assertIn("players_diff", delta)
        # Player ID 0 should have changes
        self.assertEqual(delta["players_diff"][0]["pos"], [12.0, 10.0])
        self.assertEqual(delta["players_diff"][0]["action"], "run")
        self.assertNotIn("lives", delta["players_diff"][0])  # Unchanged

        # Apply
        restored = apply_delta(self.base, delta)
        self.assertEqual(restored, curr)

    def test_structural_change(self):
        # Add projectile (using new signature with id parameter)
        curr = SimulationSnapshot(
            tick=101,
            rng_state=self.base.rng_state,
            players=self.base.players,
            enemies=self.base.enemies,
            projectiles=[ProjectileSnapshot(id=1, pos=[20.0, 20.0], velocity=5.0, timer=0.0, owner="player")],
            score=100,
            dead_count=0,
            transition=0,
        )

        delta = compute_delta(self.base, curr)

        # With ID-based matching, added projectiles use "projectiles_added" key
        self.assertIn("projectiles_added", delta)
        self.assertEqual(len(delta["projectiles_added"]), 1)
        self.assertEqual(delta["projectiles_added"][0]["id"], 1)

        restored = apply_delta(self.base, delta)
        self.assertEqual(restored, curr)

    def test_entity_removal(self):
        # Remove enemy from base snapshot
        curr = SimulationSnapshot(
            tick=101,
            rng_state=self.base.rng_state,
            players=self.base.players,
            enemies=[],  # Enemy removed
            projectiles=[],
            score=100,
            dead_count=0,
            transition=0,
        )

        delta = compute_delta(self.base, curr)

        # Enemy ID 1 should be in removed list
        self.assertIn("enemies_removed", delta)
        self.assertIn(1, delta["enemies_removed"])

        restored = apply_delta(self.base, delta)
        self.assertEqual(restored, curr)

    def test_entity_addition(self):
        # Add a new enemy
        curr = SimulationSnapshot(
            tick=101,
            rng_state=self.base.rng_state,
            players=self.base.players,
            enemies=[
                EntitySnapshot("enemy", 1, [50.0, 50.0], [1.0, 0.0], True, "run"),  # Original
                EntitySnapshot("enemy", 2, [100.0, 50.0], [0.0, 0.0], False, "idle"),  # New
            ],
            projectiles=[],
            score=100,
            dead_count=0,
            transition=0,
        )

        delta = compute_delta(self.base, curr)

        # New enemy ID 2 should be in added list
        self.assertIn("enemies_added", delta)
        self.assertEqual(len(delta["enemies_added"]), 1)
        self.assertEqual(delta["enemies_added"][0]["id"], 2)

        restored = apply_delta(self.base, delta)
        self.assertEqual(restored, curr)

    def test_projectile_changes(self):
        # Base with projectile, then move it
        base_with_proj = SimulationSnapshot(
            tick=100,
            rng_state=(3, (1, 2, 3), None),
            players=self.base.players,
            enemies=self.base.enemies,
            projectiles=[ProjectileSnapshot(id=5, pos=[10.0, 10.0], velocity=3.0, timer=0.0, owner="player")],
            score=100,
            dead_count=0,
            transition=0,
        )

        curr = SimulationSnapshot(
            tick=101,
            rng_state=(3, (1, 2, 3), None),
            players=self.base.players,
            enemies=self.base.enemies,
            projectiles=[ProjectileSnapshot(id=5, pos=[13.0, 10.0], velocity=3.0, timer=1.0, owner="player")],
            score=100,
            dead_count=0,
            transition=0,
        )

        delta = compute_delta(base_with_proj, curr)

        # Projectile ID 5 should have diff for pos and timer
        self.assertIn("projectiles_diff", delta)
        self.assertIn(5, delta["projectiles_diff"])
        self.assertEqual(delta["projectiles_diff"][5]["pos"], [13.0, 10.0])
        self.assertEqual(delta["projectiles_diff"][5]["timer"], 1.0)
        self.assertNotIn("velocity", delta["projectiles_diff"][5])  # Unchanged

        restored = apply_delta(base_with_proj, delta)
        self.assertEqual(restored, curr)


if __name__ == "__main__":
    unittest.main()
