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

    def test_shooter_policy(self):
        policy = ShooterPolicy()
        entity = MagicMock()
        entity.game = self.mock_game
        entity.pos = [100, 100]

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
        entity = MagicMock()
        entity.game = self.mock_game
        entity.pos = [100, 100]
        entity.rect.return_value.centerx = 100
        entity.rect.return_value.centery = 100
        entity.collisions = {"left": False, "right": False, "down": True}

        # Mock RNG
        with unittest.mock.patch("scripts.ai.behaviors.RNGService.get") as mock_rng:
            mock_rng.return_value.random.return_value = 0.5

            # Case 1: Player far away -> No movement
            self.mock_game.player.pos = [500, 100]
            decision = policy.decide(entity, self.mock_game)
            self.assertEqual(decision["movement"], (0, 0))

            # Case 2: Player close (right) -> Move right
            self.mock_game.player.pos = [200, 100]

            # Assume ground is solid but wall is clear
            def solid_check_side_effect(pos):
                x, y = pos
                if y > 110:  # Ground check (123)
                    return True
                return False  # Wall check (100)

            self.mock_game.tilemap.solid_check.side_effect = solid_check_side_effect
            decision = policy.decide(entity, self.mock_game)
            self.assertGreater(decision["movement"][0], 0)
            self.assertFalse(entity.flip)

            # Case 3: Player above -> Jump
            self.mock_game.player.pos = [100, 50]
            mock_rng.return_value.random.return_value = 0.01  # Trigger jump
            decision = policy.decide(entity, self.mock_game)
            self.assertTrue(decision["jump"])

    def test_jumper_policy(self):
        from scripts.ai.behaviors import JumperPolicy

        policy = JumperPolicy()
        entity = MagicMock()
        entity.game = self.mock_game
        entity.pos = [100, 100]
        entity.rect.return_value.centerx = 100
        entity.collisions = {"left": False, "right": False, "down": True}

        # Mock RNG
        with unittest.mock.patch("scripts.ai.behaviors.RNGService.get") as mock_rng:
            # Case 1: Blocked -> Jump (50% chance)
            self.mock_game.tilemap.solid_check.return_value = False  # Cliff
            mock_rng.return_value.random.return_value = 0.1  # < 0.5 triggers jump
            decision = policy.decide(entity, self.mock_game)
            self.assertTrue(decision["jump"])


if __name__ == "__main__":
    unittest.main()
