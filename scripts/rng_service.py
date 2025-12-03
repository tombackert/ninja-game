import random
from typing import Any, Sequence

from scripts.logger import get_logger

log = get_logger("rng")


class RNGService:
    _instance: "RNGService | None" = None

    def __init__(self, seed: int | float | str | bytes | bytearray | None = None):
        self._generator = random.Random(seed)
        self._seed_val = seed
        log.info(f"RNG initialized with seed: {seed!r}")

    @classmethod
    def get(cls) -> "RNGService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def initialize(cls, seed: int | float | str | bytes | bytearray | None = None) -> None:
        cls._instance = cls(seed)

    def seed(self, a: int | float | str | bytes | bytearray | None = None) -> None:
        self._seed_val = a
        self._generator.seed(a)
        log.debug(f"RNG re-seeded: {a!r}")

    def random(self) -> float:
        """Return the next random floating point number in the range [0.0, 1.0)."""
        return self._generator.random()

    def randint(self, a: int, b: int) -> int:
        """Return a random integer N such that a <= N <= b."""
        return self._generator.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        """Return a random floating point number N such that a <= N <= b for a <= b."""
        return self._generator.uniform(a, b)

    def choice(self, seq: Sequence[Any]) -> Any:
        """Return a random element from the non-empty sequence seq."""
        return self._generator.choice(seq)

    def shuffle(self, x: list) -> None:
        """Shuffle list x in place, and return None."""
        self._generator.shuffle(x)

    def get_state(self) -> tuple[Any, ...]:
        """Return an object capturing the current internal state of the generator."""
        return self._generator.getstate()

    def set_state(self, state: tuple[Any, ...]) -> None:
        """Restore the internal state of the generator from a previous get_state() call."""
        self._generator.setstate(state)
