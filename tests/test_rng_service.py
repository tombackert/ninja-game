import random
from scripts.rng_service import RNGService


def test_rng_singleton():
    rng1 = RNGService.get()
    rng2 = RNGService.get()
    assert rng1 is rng2


def test_rng_determinism():
    rng = RNGService.get()

    # Sequence A
    rng.seed(12345)
    val_a1 = rng.random()
    val_a2 = rng.randint(0, 100)
    val_a3 = rng.choice(['a', 'b', 'c'])

    # Sequence B (same seed)
    rng.seed(12345)
    val_b1 = rng.random()
    val_b2 = rng.randint(0, 100)
    val_b3 = rng.choice(['a', 'b', 'c'])

    assert val_a1 == val_b1
    assert val_a2 == val_b2
    assert val_a3 == val_b3


def test_rng_independent_of_global():
    """Ensure service does not share state with global random module."""
    rng = RNGService.get()
    rng.seed(999)
    random.seed(999)

    # They start same if seeded same
    s_val = rng.random()
    g_val = random.random()
    assert s_val == g_val

    # Diverge if one is reseeded
    rng.seed(111)
    assert rng.random() != random.random()


def test_state_snapshot():
    rng = RNGService.get()
    rng.seed(42)

    # Advance state
    rng.random()
    rng.random()

    # Capture
    state = rng.get_state()

    # Generate expected future
    future_1 = rng.random()
    future_2 = rng.randint(10, 20)

    # Restore
    rng.set_state(state)

    # Verify replay
    assert rng.random() == future_1
    assert rng.randint(10, 20) == future_2
