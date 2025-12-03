from scripts.rollback_buffer import RollbackBuffer
from scripts.snapshot import SimulationSnapshot


def make_dummy_snap(tick):
    return SimulationSnapshot(tick=tick, rng_state=())


def test_buffer_push_retrieve():
    rb = RollbackBuffer(capacity=10)

    snap = make_dummy_snap(100)
    rb.push(snap, ["jump"])

    data = rb.get(100)
    assert data is not None
    assert data.snapshot.tick == 100
    assert data.inputs == ["jump"]


def test_buffer_overwrite():
    rb = RollbackBuffer(capacity=3)

    # Fill 0, 1, 2
    for i in range(3):
        rb.push(make_dummy_snap(i), [])

    assert rb.get(0) is not None
    assert rb.get(2) is not None

    # Push 3 -> Should overwrite 0
    rb.push(make_dummy_snap(3), [])

    assert rb.get(0) is None  # Evicted
    assert rb.get(1) is not None
    assert rb.get(3) is not None


def test_buffer_lookup_by_tick_modulo():
    # Tick doesn't always start at 0
    rb = RollbackBuffer(capacity=5)
    rb.push(make_dummy_snap(1005), [])  # index 0

    assert rb.get(1005) is not None
    assert rb.get(5) is None  # Different tick, same index
