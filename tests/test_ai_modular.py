import unittest
from unittest.mock import MagicMock
from scripts.ai.core import Policy, PolicyService
from scripts.ai.behaviors import PatrolPolicy, ShooterPolicy
from scripts.entities import Enemy


class TestModularAI(unittest.TestCase):
    def setUp(self):
        self.mock_game = MagicMock()
        self.mock_game.tilemap = MagicMock()
        self.mock_game.player = MagicMock()
        self.mock_game.player.pos = [0, 0]
        self.mock_services = MagicMock()

    def test_policy_registration(self):
        class MockPolicy(Policy):
            def decide(self, entity, context):
                return {"mock": True}

        PolicyService.register("test_mock", MockPolicy())
        p = PolicyService.get("test_mock")
        self.assertIsInstance(p, MockPolicy)

    def test_enemy_init_with_policy(self):
        # Ensure "scripted_enemy" is registered (it should be by import side-effects in __init__)
        # We might need to ensure scripts.ai is imported

        e = Enemy(self.mock_game, (0, 0), services=self.mock_services, policy="scripted_enemy")
        self.assertIsNotNone(e.policy)

        # Test with non-existent policy
        with self.assertRaises(ValueError):
            Enemy(self.mock_game, (0, 0), services=self.mock_services, policy="non_existent_policy")

    def test_patrol_policy(self):
        policy = PatrolPolicy()
        entity = MagicMock()
        entity.game = self.mock_game
        entity.pos = [100, 100]
        entity.flip = False
        entity.rect.return_value.centerx = 100
        entity.collisions = {"left": False, "right": False}

        # Case 1: Solid ground ahead -> Move
        self.mock_game.tilemap.solid_check.return_value = True
        decision = policy.decide(entity, self.mock_game)
        self.assertNotEqual(decision["movement"][0], 0)

        # Case 2: Cliff -> Turn
        self.mock_game.tilemap.solid_check.return_value = False
        # The policy flips the entity directly (side effect)
        policy.decide(entity, self.mock_game)
        self.assertTrue(entity.flip)

    def _enemy(self, kind, x=100, ground=True):
        """A stand-in enemy at (x, 100) on a MagicMock game."""
        from types import SimpleNamespace

        import pygame

        from scripts.enemy_kinds import KINDS

        e = SimpleNamespace(
            game=self.mock_game,
            kind=KINDS[kind],
            pos=[x, 100],
            velocity=[0, 0],
            flip=False,
            cooldown=0,
            awake=False,
            collisions={"left": False, "right": False, "down": ground},
        )
        e.rect = lambda: pygame.Rect(e.pos[0], e.pos[1], 8, 15)
        self.mock_game.enemies = [e]
        return e

    def test_shooter_policy(self):
        policy = ShooterPolicy()  # the turret's behavior
        entity = self._enemy("turret")

        # Case 1: Player to the right
        self.mock_game.player.pos = [200, 100]
        policy.decide(entity, self.mock_game)
        self.assertFalse(entity.flip)  # Face right (False)

        # Case 2: Player to the left
        self.mock_game.player.pos = [50, 100]
        policy.decide(entity, self.mock_game)
        self.assertTrue(entity.flip)  # Face left (True)

    def test_chaser_policy(self):
        from scripts.ai.behaviors import ChaserPolicy

        policy = ChaserPolicy()
        entity = self._enemy("chaser")
        self.mock_game.tilemap.solid_check.side_effect = lambda pos: pos[1] > 110  # flat floor

        # Case 1: Player far away -> asleep, no movement
        self.mock_game.player.pos = [500, 100]
        decision = policy.decide(entity, self.mock_game)
        self.assertEqual(decision["movement"], (0, 0))
        self.assertFalse(entity.awake)

        # Case 2: Player close (right) -> wakes and runs right
        self.mock_game.player.pos = [200, 100]
        decision = policy.decide(entity, self.mock_game)
        self.assertGreater(decision["movement"][0], 0)
        self.assertFalse(entity.flip)

        # Case 3: Edge ahead -> stops instead of falling
        self.mock_game.tilemap.solid_check.side_effect = lambda pos: False
        decision = policy.decide(entity, self.mock_game)
        self.assertEqual(decision["movement"], (0, 0))

    def test_jumper_policy(self):
        from scripts.ai.behaviors import JumperPolicy

        policy = JumperPolicy()
        entity = self._enemy("jumper")
        self.mock_game.tilemap.solid_check.side_effect = lambda pos: pos[1] > 110  # flat floor

        # On the ground, rested -> hops forward
        decision = policy.decide(entity, self.mock_game)
        self.assertTrue(decision["jump"])
        self.assertGreater(decision["movement"][0], 0)
        self.assertEqual(entity.cooldown, entity.kind.hop_period)

        # Resting -> stays put
        decision = policy.decide(entity, self.mock_game)
        self.assertFalse(decision["jump"])
        self.assertEqual(decision["movement"], (0, 0))


if __name__ == "__main__":
    unittest.main()
