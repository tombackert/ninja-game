from scripts.ai.core import Policy, PolicyService
from scripts.ai.behaviors import ScriptedEnemyPolicy, PatrolPolicy, ShooterPolicy, ChaserPolicy, JumperPolicy

# Register standard behaviors
PolicyService.register("scripted_enemy", ScriptedEnemyPolicy())
PolicyService.register("patrol", PatrolPolicy())
PolicyService.register("shooter", ShooterPolicy())
PolicyService.register("chaser", ChaserPolicy())
PolicyService.register("jumper", JumperPolicy())

__all__ = [
    "Policy",
    "PolicyService",
    "ScriptedEnemyPolicy",
    "PatrolPolicy",
    "ShooterPolicy",
    "ChaserPolicy",
    "JumperPolicy",
]
