"""Tests for Entity ID Generator (MP-02).

Tests the EntityIDGenerator singleton that provides centralized,
deterministic unique ID generation for all game entities.
"""

import unittest
from scripts.entity_id import EntityIDGenerator, generate_entity_id


class TestEntityIDGenerator(unittest.TestCase):
    def setUp(self):
        # Reset singleton before each test for isolation
        EntityIDGenerator.reset_instance()
        self.gen = EntityIDGenerator.get()

    def tearDown(self):
        # Clean up singleton
        EntityIDGenerator.reset_instance()

    def test_singleton_pattern(self):
        """EntityIDGenerator should return the same instance."""
        gen1 = EntityIDGenerator.get()
        gen2 = EntityIDGenerator.get()
        self.assertIs(gen1, gen2)

    def test_next_id_increments(self):
        """next_id should return incrementing unique IDs."""
        id1 = self.gen.next_id()
        id2 = self.gen.next_id()
        id3 = self.gen.next_id()

        self.assertEqual(id1, 0)
        self.assertEqual(id2, 1)
        self.assertEqual(id3, 2)

    def test_reset_to_zero(self):
        """reset() should reset counter to 0 by default."""
        self.gen.next_id()
        self.gen.next_id()
        self.gen.next_id()

        self.gen.reset()
        self.assertEqual(self.gen.next_id(), 0)

    def test_reset_to_custom_value(self):
        """reset(start_id) should reset counter to specified value."""
        self.gen.reset(100)
        self.assertEqual(self.gen.next_id(), 100)
        self.assertEqual(self.gen.next_id(), 101)

    def test_peek_next_does_not_consume(self):
        """peek_next should return next ID without incrementing."""
        self.assertEqual(self.gen.peek_next(), 0)
        self.assertEqual(self.gen.peek_next(), 0)  # Still 0
        self.assertEqual(self.gen.next_id(), 0)  # Consumes it
        self.assertEqual(self.gen.peek_next(), 1)  # Now 1

    def test_get_state(self):
        """get_state should return current counter value."""
        self.assertEqual(self.gen.get_state(), 0)
        self.gen.next_id()
        self.gen.next_id()
        self.assertEqual(self.gen.get_state(), 2)

    def test_set_state(self):
        """set_state should restore counter to specified value."""
        self.gen.next_id()
        self.gen.next_id()

        state = self.gen.get_state()
        self.assertEqual(state, 2)

        # Generate more IDs
        self.gen.next_id()
        self.gen.next_id()
        self.assertEqual(self.gen.get_state(), 4)

        # Restore state
        self.gen.set_state(state)
        self.assertEqual(self.gen.get_state(), 2)
        self.assertEqual(self.gen.next_id(), 2)

    def test_reset_instance_creates_new_singleton(self):
        """reset_instance should clear singleton, allowing new instance."""
        gen1 = EntityIDGenerator.get()
        gen1.next_id()
        gen1.next_id()
        self.assertEqual(gen1.get_state(), 2)

        EntityIDGenerator.reset_instance()

        gen2 = EntityIDGenerator.get()
        self.assertIsNot(gen1, gen2)
        self.assertEqual(gen2.get_state(), 0)  # Fresh counter

    def test_convenience_function(self):
        """generate_entity_id convenience function should work."""
        id1 = generate_entity_id()
        id2 = generate_entity_id()
        self.assertEqual(id1, 0)
        self.assertEqual(id2, 1)

    def test_determinism_across_resets(self):
        """Same sequence of operations should produce same IDs after reset."""
        # First sequence
        self.gen.reset(0)
        seq1 = [self.gen.next_id() for _ in range(5)]

        # Reset and repeat
        self.gen.reset(0)
        seq2 = [self.gen.next_id() for _ in range(5)]

        self.assertEqual(seq1, seq2)
        self.assertEqual(seq1, [0, 1, 2, 3, 4])


class TestEntityIDIntegration(unittest.TestCase):
    """Integration tests for entity ID usage patterns."""

    def setUp(self):
        EntityIDGenerator.reset_instance()

    def tearDown(self):
        EntityIDGenerator.reset_instance()

    def test_player_and_enemy_ids_unique(self):
        """Players and enemies should get unique IDs from same generator."""
        gen = EntityIDGenerator.get()

        player_id = gen.next_id()  # Player 0
        enemy1_id = gen.next_id()  # Enemy 1
        enemy2_id = gen.next_id()  # Enemy 2
        player2_id = gen.next_id()  # Player 2 (multiplayer)

        # All unique
        ids = [player_id, enemy1_id, enemy2_id, player2_id]
        self.assertEqual(len(ids), len(set(ids)))

    def test_state_serialization_roundtrip(self):
        """State should survive serialization roundtrip."""
        gen = EntityIDGenerator.get()

        # Generate some IDs
        for _ in range(10):
            gen.next_id()

        # Serialize state
        state = gen.get_state()

        # Reset and restore
        gen.reset(0)
        self.assertEqual(gen.next_id(), 0)

        gen.set_state(state)
        self.assertEqual(gen.next_id(), 10)

    def test_level_load_reset_pattern(self):
        """Simulates level load: reset generator for determinism."""
        gen = EntityIDGenerator.get()

        # Level 1: Generate IDs
        gen.reset(0)
        level1_ids = [gen.next_id() for _ in range(5)]

        # Level 2: Reset for fresh IDs
        gen.reset(0)
        level2_ids = [gen.next_id() for _ in range(5)]

        # Same IDs produced (deterministic)
        self.assertEqual(level1_ids, level2_ids)


class TestSnapshotIDPreservation(unittest.TestCase):
    """Tests that entity IDs are preserved across snapshot serialize/deserialize."""

    def setUp(self):
        EntityIDGenerator.reset_instance()

    def tearDown(self):
        EntityIDGenerator.reset_instance()

    def test_entity_snapshot_preserves_id(self):
        """EntitySnapshot should preserve id field through serialization."""
        from scripts.snapshot import EntitySnapshot, SnapshotService, SimulationSnapshot

        # Create snapshot with specific IDs
        player = EntitySnapshot(
            type="player",
            id=42,
            pos=[100.0, 200.0],
            velocity=[0.0, 0.0],
            flip=False,
            action="idle",
            owner_id=42,
            lives=3,
        )

        snap = SimulationSnapshot(
            tick=100,
            rng_state=(),
            players=[player],
        )

        # Serialize and deserialize
        data = SnapshotService.serialize(snap)
        restored = SnapshotService.deserialize(data)

        # Verify ID preserved
        self.assertEqual(restored.players[0].id, 42)
        self.assertEqual(restored.players[0].owner_id, 42)

    def test_projectile_snapshot_preserves_id(self):
        """ProjectileSnapshot should preserve id field through serialization."""
        from scripts.snapshot import ProjectileSnapshot, SnapshotService, SimulationSnapshot

        proj = ProjectileSnapshot(
            id=99,
            pos=[50.0, 60.0],
            velocity=3.5,
            timer=10.0,
            owner="player",
            owner_id=1,
        )

        snap = SimulationSnapshot(
            tick=100,
            rng_state=(),
            projectiles=[proj],
        )

        # Serialize and deserialize
        data = SnapshotService.serialize(snap)
        restored = SnapshotService.deserialize(data)

        # Verify ID preserved
        self.assertEqual(restored.projectiles[0].id, 99)
        self.assertEqual(restored.projectiles[0].owner_id, 1)

    def test_delta_preserves_ids_on_apply(self):
        """Delta application should preserve entity IDs."""
        from scripts.snapshot import EntitySnapshot, SimulationSnapshot
        from scripts.network.delta import compute_delta, apply_delta

        # Base snapshot
        base = SimulationSnapshot(
            tick=100,
            rng_state=(),
            players=[EntitySnapshot("player", 5, [0.0, 0.0], [0.0, 0.0], False, "idle", owner_id=5)],
        )

        # Changed snapshot (same ID, different position)
        curr = SimulationSnapshot(
            tick=101,
            rng_state=(),
            players=[EntitySnapshot("player", 5, [10.0, 0.0], [1.0, 0.0], False, "run", owner_id=5)],
        )

        delta = compute_delta(base, curr)
        restored = apply_delta(base, delta)

        # ID should be preserved
        self.assertEqual(restored.players[0].id, 5)
        self.assertEqual(restored.players[0].owner_id, 5)
        self.assertEqual(restored.players[0].pos, [10.0, 0.0])


if __name__ == "__main__":
    unittest.main()
