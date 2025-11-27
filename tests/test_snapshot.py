import pytest
from game import Game
from scripts.snapshot import SnapshotService
from scripts.rng_service import RNGService


def test_snapshot_roundtrip():
    g = Game()
    g.load_level(0)

    # Setup initial state
    p = g.player
    p.pos = [100, 100]
    p.velocity = [1.5, -2.0]
    p.lives = 2
    g.cm.coins = 5

    # Spawn a projectile
    g.projectiles.spawn(120, 100, 3.0, "player")

    # Advance RNG
    rng = RNGService.get()
    rng.seed(42)
    rng.random()

    # CAPTURE
    snap = SnapshotService.capture(g)

    # MUTATE
    p.pos = [200, 200]
    p.velocity = [0, 0]
    p.lives = 1
    g.cm.coins = 10
    g.projectiles.clear()
    rng.random()  # mutate RNG

    # RESTORE
    SnapshotService.restore(g, snap)

    # VERIFY
    assert g.player.pos == [100, 100]
    assert g.player.velocity == [1.5, -2.0]
    assert g.player.lives == 2
    assert g.cm.coins == 5
    assert len(g.projectiles) == 1

    # Verify projectile details
    proj = next(iter(g.projectiles))
    assert proj["pos"] == [120, 100]
    assert proj["vel"][0] == 3.0

    # Verify RNG
    val = rng.random()
    rng.set_state(snap.rng_state)  # manually reset to check next val
    assert rng.random() == val
