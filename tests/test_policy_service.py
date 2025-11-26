from scripts.policy_service import PolicyService, ScriptedEnemyPolicy
from scripts.entities import Enemy
from game import Game

def test_policy_registry():
    # Default should be present
    policy = PolicyService.get("scripted_enemy")
    assert isinstance(policy, ScriptedEnemyPolicy)

def test_enemy_uses_policy():
    g = Game()
    e = Enemy(g, [0,0], (8,15), 0)
    assert isinstance(e.policy, ScriptedEnemyPolicy)
    
    # Mock decide
    class MockPolicy:
        def decide(self, entity, context):
            return {"movement": (5, 0), "shoot": True}
    
    e.policy = MockPolicy()
    e.update(g.tilemap, (0,0))
    
    # Verify movement applied
    assert e.pos[0] > 0
    # Verify run animation set due to movement
    assert e.action == "run"
