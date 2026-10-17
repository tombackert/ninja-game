"""Rendering must never change the simulation.

Headless paths (training, replay re-simulation, prediction) never render,
so anything the render path does to the shared RNG or world state makes
them diverge from live play.
"""

import pygame

from scripts.replay import ReplayData, ReplayGhost
from scripts.rng_service import RNGService
from scripts.state_manager import GameState

LEVEL = 0  # has leaf-spawning trees and enemies
TICKS = 300


def _run(render: bool):
    state = GameState()
    g = state.game
    RNGService.get().seed(1234)
    g.level = LEVEL
    g.load_level(LEVEL)
    g.replay.ghost = None  # independent of locally saved replays
    g.movement = [False, True]
    surface = pygame.Surface((g.BASE_W, g.BASE_H))
    for _ in range(TICKS):
        state.update(1 / 60)
        if render:
            state.render(surface)
    enemies = [(e.id, list(e.pos), e.action) for e in g.enemies]
    return RNGService.get().get_state(), enemies, list(g.player.pos), g.player.lives


def test_rendering_does_not_change_simulation():
    assert _run(render=False) == _run(render=True)


def test_ghost_resimulation_does_not_touch_world():
    g = GameState().game
    data = ReplayData(level=str(LEVEL), skin="default", seed=0, duration_frames=30)
    data.inputs = [{"tick": 0, "inputs": ["dash"]}]
    ghost = ReplayGhost(g, data)

    rng_state = RNGService.get().get_state()
    for _ in range(30):
        ghost.step_and_render(g.display, (0, 0))

    assert ghost.tick == 30
    assert RNGService.get().get_state() == rng_state
    assert g.dead == 0
