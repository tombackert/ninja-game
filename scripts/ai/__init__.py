from scripts.ai.core import Policy, PolicyService
from scripts.ai.behaviors import (
    ChaserPolicy,
    GunnerPolicy,
    JumperPolicy,
    PatrolPolicy,
    ScriptedEnemyPolicy,
    ShooterPolicy,
    ThrowerPolicy,
    TurretPolicy,
)

# One behavior per enemy kind (scripts/enemy_kinds.py)
PolicyService.register("gunner", GunnerPolicy())
PolicyService.register("patrol", PatrolPolicy())
PolicyService.register("turret", TurretPolicy())
PolicyService.register("chaser", ChaserPolicy())
PolicyService.register("jumper", JumperPolicy())
PolicyService.register("thrower", ThrowerPolicy())
# Old names
PolicyService.register("scripted_enemy", PolicyService.get("gunner"))
PolicyService.register("shooter", PolicyService.get("turret"))

__all__ = [
    "Policy",
    "PolicyService",
    "GunnerPolicy",
    "ScriptedEnemyPolicy",
    "PatrolPolicy",
    "TurretPolicy",
    "ShooterPolicy",
    "ChaserPolicy",
    "JumperPolicy",
    "ThrowerPolicy",
]
