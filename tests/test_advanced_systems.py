import unittest
import pygame
from unittest.mock import MagicMock

from scripts.snapshot import SnapshotService, SimulationSnapshot
from scripts.rng_service import RNGService
from scripts.replay import ReplayData, FrameSample
from scripts.ai.behaviors import ShooterPolicy
from scripts.entities import Enemy, PhysicsEntity

# Stub classes to avoid loading assets
class StubGame:
    def __init__(self):
        self.players = []
        self.enemies = []
        self.projectiles = MagicMock()
        self.projectiles._projectiles = []
        self.cm = MagicMock()
        self.cm.coins = 0
        self.dead = 0
        self.transition = 0
        
        # Mock assets with copy() method
        mock_anim = MagicMock()
        mock_anim.copy.return_value = mock_anim
        self.assets = {
            "enemy/idle": mock_anim,
            "enemy/run": mock_anim,
            "player/idle": mock_anim,
            "player/run": mock_anim,
            # Add others if needed by specific tests
        }
        
        self.tilemap = MagicMock()
        self.tilemap.solid_check.return_value = False
        # Setup mock player
        self.player = MagicMock()
        self.player.pos = [0, 0]
        self.player.id = 0
        self.player.velocity = [0, 0]
        self.player.action = "idle"
        self.player.flip = False
        self.player.lives = 3
        self.player.air_time = 0
        self.player.jumps = 1
        self.player.wall_slide = False
        self.player.dashing = 0
        self.player.shoot_cooldown = 0
        self.players.append(self.player)

class TestAdvancedSystems(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.game = StubGame()
        RNGService.initialize(seed=123)

    def tearDown(self):
        pygame.quit()

    def test_snapshot_determinism(self):
        """
        Verify that restoring a snapshot and applying the same inputs 
        results in the EXACT same state (Determinism).
        """
        # 1. Setup initial state
        self.game.player.pos = [100.0, 100.0]
        self.game.player.velocity = [1.0, 0.0]
        
        # 2. Capture Snapshot A (Start)
        snap_a = SnapshotService.capture(self.game)
        
        # 3. Simulate "Run 1"
        # Modify state as if simulation happened
        self.game.player.pos[0] += 10.0 # Move right
        self.game.player.velocity[0] = 2.0
        RNGService.get().random() # Advance RNG
        
        # 4. Capture Snapshot B (End of Run 1)
        snap_b = SnapshotService.capture(self.game)
        
        # 5. Restore Snapshot A
        SnapshotService.restore(self.game, snap_a)
        
        # Verify restoration worked (sanity check)
        self.assertEqual(self.game.player.pos, [100.0, 100.0])
        self.assertEqual(self.game.player.velocity, [1.0, 0.0])
        
        # 6. Simulate "Run 2" (Identical actions)
        self.game.player.pos[0] += 10.0
        self.game.player.velocity[0] = 2.0
        RNGService.get().random() # Advance RNG (must match)

        # 7. Capture Snapshot C (End of Run 2)
        snap_c = SnapshotService.capture(self.game)
        
        # 8. Compare B and C
        # We compare the serialized dicts for deep equality
        dict_b = SnapshotService.serialize(snap_b)
        dict_c = SnapshotService.serialize(snap_c)
        
        self.assertEqual(dict_b, dict_c, "Snapshots diverging after restore and re-simulation!")

    def test_replay_data_serialization(self):
        """
        Verify ReplayData serialization roundtrip, including sparse snapshots.
        """
        # Create dummy data
        rd = ReplayData(
            level="1",
            skin="ninja",
            seed=999,
            duration_frames=100,
            inputs=[{"tick": 1, "inputs": ["left"]}, {"tick": 2, "inputs": ["jump"]}],
            snapshots={"0": {"tick": 0, "score": 100}}, # Mock serialized snapshot
            visual_frames=[FrameSample(10, 10, False, "run", 0)]
        )
        
        # Serialize
        json_data = rd.to_json()
        
        # Deserialize
        rd_restored = ReplayData.from_json(json_data)
        
        self.assertEqual(rd.level, rd_restored.level)
        self.assertEqual(rd.seed, rd_restored.seed)
        self.assertEqual(len(rd.inputs), len(rd_restored.inputs))
        self.assertEqual(rd.inputs[1]["inputs"], ["jump"])
        self.assertEqual(rd.snapshots["0"]["score"], 100)
        self.assertEqual(rd.visual_frames[0].x, 10.0)

    def test_ai_shooter_orientation(self):
        """
        Verify ShooterPolicy correctly orients the enemy towards the player.
        """
        # Setup Enemy with ShooterPolicy
        # We need a real Enemy instance but stubbed game
        # PolicyService.get("shooter") requires "scripts.ai" import side-effect.
        # We will inject policy directly or rely on PolicyService working if imported.
        from scripts.ai.behaviors import ShooterPolicy
        
        enemy = Enemy(self.game, (200, 200), (10, 10), 0)
        enemy.policy = ShooterPolicy()
        
        # Case 1: Player is to the RIGHT
        self.game.player.pos = [300, 200]
        enemy.update(self.game.tilemap)
        
        # Enemy should NOT be flipped (facing right)
        self.assertFalse(enemy.flip, "Shooter should face right when player is right")
        
        # Case 2: Player is to the LEFT
        self.game.player.pos = [100, 200]
        enemy.update(self.game.tilemap)
        
        # Enemy SHOULD be flipped (facing left)
        self.assertTrue(enemy.flip, "Shooter should face left when player is left")

if __name__ == '__main__':
    unittest.main()
