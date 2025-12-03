from scripts.prediction_service import PredictionReconciliationService
from scripts.rollback_buffer import RollbackBuffer
from scripts.snapshot import SnapshotService
from game import Game


def test_reconciliation_logic():
    # Setup Game
    g = Game()
    g.load_level(0)
    # Mock physics rects to avoid collision resolution interfering with pos
    g.tilemap.physics_rects_around = lambda pos: []

    p = g.player
    p.pos = [100, 100]
    p.velocity = [0, 0]

    buffer = RollbackBuffer()
    service = PredictionReconciliationService(g, buffer)

    # Simulate local ticks 0..5
    # Tick 0: Initial
    snap0 = SnapshotService.capture(g)
    snap0.tick = 0
    buffer.push(snap0, [])  # No input led to 0 (start)

    # Tick 1: Move Right
    # Apply input
    p.velocity = [2, 0]  # Simulate result of right
    p.pos = [102, 100]
    snap1 = SnapshotService.capture(g)
    snap1.tick = 1
    buffer.push(snap1, ["right"])

    # Tick 2: Move Right again
    p.pos = [104, 100]
    snap2 = SnapshotService.capture(g)
    snap2.tick = 2
    buffer.push(snap2, ["right"])

    # Now, Server sends Snapshot for Tick 1.
    # SERVER SAYS: At tick 1, pos was [105, 100] (Desync!)
    # Maybe due to teleporter or lag.

    server_snap = SnapshotService.capture(g)  # Copy structure
    server_snap.tick = 1
    server_snap.players[0].pos = [105, 100]

    # Trigger reconciliation
    service.on_authoritative_snapshot(server_snap)

    # After reconciliation:
    # 1. Game state should now be at Tick 2 (re-simulated).
    # 2. Base was Tick 1 [105, 100].
    # 3. Re-simulated Tick 2 should apply "right" (+2) -> [107, 100].
    #    (Assuming _apply_inputs_and_step logic works roughly as mocked)

    # Since _apply_inputs_and_step calls physics update which adds velocity/friction,
    # exact value depends on physics constants.
    # But strictly, it should NOT be [104, 100] anymore.

    assert g.player.pos != [104, 100]

    # The service re-simulates physics.
    # Tick 1 (restored 105) -> Apply "right" -> Tick 2.
    # With velocity [2,0], new pos should be > 105.
    assert g.player.pos[0] > 105

    # Verify buffer was updated
    new_snap2 = buffer.get(2).snapshot
    assert new_snap2.players[0].pos[0] > 105
