import os
import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["NINJA_GAME_TESTING"] = "1"

from scripts.entities import PhysicsEntity  # noqa: E402
from scripts.constants import MAX_FALL_SPEED, GRAVITY_ACCEL  # noqa: E402


class DummyTilemap:
    """Minimal tilemap supplying physics_rects_around for collision tests."""

    def __init__(self, rects):
        self._rects = rects

    def physics_rects_around(self, pos):  # signature match
        return self._rects


class DummyGame:
    def __init__(self):
        # Provide trivial assets mapping for animation copies; we only need an object
        class DummyAnim:
            def copy(self):
                return self

            def update(self):
                pass

            def img(self):  # pragma: no cover - not used
                return pygame.Surface((1, 1))

        # Provide both enemy and player idle assets to satisfy set_action invocations
        self.assets = {"enemy/idle": DummyAnim(), "player/0/idle": DummyAnim()}


def make_entity(x=0, y=0, w=8, h=8):
    g = DummyGame()
    e = PhysicsEntity(g, "enemy", [x, y], (w, h), id=0)
    return e


def test_horizontal_collision_stops_movement():
    # Place a blocking rect to the right
    block = pygame.Rect(10, 0, 10, 10)
    tilemap = DummyTilemap([block])
    e = make_entity(x=0, y=0, w=8, h=8)
    e.velocity[0] = 0
    # Attempt to move right by +12 -> should collide and set right flag.
    e.update(tilemap, movement=(12, 0))
    assert e.collisions["right"] is True
    # Entity should not penetrate block: its right edge <= block.left
    assert e.rect().right <= block.left


def test_gravity_capped_at_max_fall_speed():
    tilemap = DummyTilemap([])
    e = make_entity()
    # Simulate many updates with no collisions; velocity should cap at MAX_FALL_SPEED
    for _ in range(int(MAX_FALL_SPEED / GRAVITY_ACCEL) * 3):  # plenty iterations
        e.update(tilemap, movement=(0, 0))
    assert e.velocity[1] == MAX_FALL_SPEED
