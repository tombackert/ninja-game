import os
import sys

# Ensure scripts path is importable if running directly
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.constants import JUMP_VELOCITY, DASH_DURATION_FRAMES  # noqa: E402
from game import Game  # noqa: E402


def make_minimal_game():
    g = Game()
    # Trim entities for speed
    g.enemies.clear()
    return g


def test_player_jump_sets_constant_velocity(monkeypatch):
    g = make_minimal_game()
    p = g.player
    # Ensure grounded state
    p.collisions["down"] = True
    p.jumps = 1
    assert p.jump() is True
    assert p.velocity[1] == JUMP_VELOCITY


def test_player_dash_uses_duration_constant(monkeypatch):
    g = make_minimal_game()
    p = g.player
    # prev = p.dashing
    p.flip = False
    p.dash()
    assert p.dashing == DASH_DURATION_FRAMES
    # Simulate one update tick to reduce dash counter
    p.update(g.tilemap, (0, 0))
    assert p.dashing <= DASH_DURATION_FRAMES
