from scripts.feature_extractor import FeatureExtractor
from scripts.snapshot import SimulationSnapshot, EntitySnapshot, ProjectileSnapshot


def test_feature_extractor_basic():
    # Setup dummy snapshot
    me = EntitySnapshot(type="player", id=0, pos=[100, 100], velocity=[0, 0], flip=False, action="idle", lives=3)
    enemy = EntitySnapshot(type="enemy", id=1, pos=[150, 100], velocity=[-1, 0], flip=True, action="run", walking=1)
    proj = ProjectileSnapshot(pos=[90, 100], velocity=3.0, timer=0, owner="enemy")

    snap = SimulationSnapshot(tick=1, rng_state=(), players=[me], enemies=[enemy], projectiles=[proj])

    extractor = FeatureExtractor(max_enemies=1, max_projectiles=1)
    obs = extractor.extract(snap, entity_id=0)

    # Self
    assert obs["self"][0] == 100  # x
    assert obs["self"][5] == 3  # lives

    # Enemy (relative)
    # dx = 150 - 100 = 50
    assert obs["enemies"][0] == 50
    assert obs["enemies"][4] == 1.0  # present

    # Projectile (relative)
    # dx = 90 - 100 = -10
    assert obs["projectiles"][0] == -10
    assert obs["projectiles"][3] == -1.0  # owner enemy


def test_feature_extractor_missing_self():
    snap = SimulationSnapshot(tick=1, rng_state=(), players=[])
    extractor = FeatureExtractor()
    obs = extractor.extract(snap, entity_id=99)

    # Should return zeroed
    assert all(v == 0.0 for v in obs["self"])
    assert all(v == 0.0 for v in obs["enemies"])


def test_feature_extractor_padding():
    # No enemies, but requested max 2
    me = EntitySnapshot(type="player", id=0, pos=[0, 0], velocity=[0, 0], flip=False, action="idle")
    snap = SimulationSnapshot(tick=1, rng_state=(), players=[me], enemies=[])

    extractor = FeatureExtractor(max_enemies=2)
    obs = extractor.extract(snap, entity_id=0)

    # Length should be 2 * 5 = 10
    assert len(obs["enemies"]) == 10
    assert all(v == 0.0 for v in obs["enemies"])
