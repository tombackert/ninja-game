"""Game feel: hit-stop, squash & stretch, dust and the sound hooks.

All of it is looks and sound only: a run simulates the same with or without
it (the shared RNG, positions, enemies), so replays, route plans, training
and the netcode are untouched.
"""

import pygame
import pytest

from scripts import dust
from scripts.audio_service import BASE_VOLUME, DEFAULT_MUSIC, SFX_NAMES, _resampled, music_for
from scripts.constants import HITSTOP_KILL_FRAMES, MAX_FALL_SPEED, SQUASH_FRAMES
from scripts.replay import GhostPlayer
from scripts.rng_service import RNGService
from scripts.state_manager import GameState

LEVEL = 0  # enemies and trees (leaves draw from the RNG every tick)
TICKS = 360


def _state():
    state = GameState()
    g = state.game
    g.level = LEVEL
    g.load_level(LEVEL)
    g.replay.ghost = None  # independent of locally saved replays
    return state, g


def _run(feedback: bool):
    """Run right and jump now and then, straight through Game.step()."""
    state, g = _state()
    RNGService.get().seed(99)
    g.player.FEEDBACK = feedback
    dusts = 0
    for t in range(TICKS):
        g.movement = [False, True]
        if t % 45 == 10:
            g.player.jump()
        g.step()
        dusts += sum(isinstance(p, dust.Dust) for p in g.particles)
    enemies = [(e.id, list(e.pos), e.action) for e in g.enemies]
    return (RNGService.get().get_state(), enemies, list(g.player.pos), g.player.lives), dusts


def test_feedback_does_not_change_the_simulation():
    with_fx, dusts = _run(feedback=True)
    without_fx, none = _run(feedback=False)
    assert with_fx == without_fx
    assert dusts > 0 and none == 0


def test_landing_squashes_and_springs_back():
    _, g = _state()
    p = g.player
    for _ in range(120):  # come down at the spawn and stand
        p.update(g.tilemap, (0, 0))
    p._land(MAX_FALL_SPEED)
    sx, sy = p.squash_scale()
    assert sx > 1.0 > sy
    for _ in range(SQUASH_FRAMES):
        p.update(g.tilemap, (0, 0))
    assert p.squash_scale() == (1.0, 1.0)


def test_jump_stretches_and_names_its_sound():
    _, g = _state()
    p = g.player
    p.collisions["down"] = True
    p.air_time = 0
    p.jumps = 1
    assert p.jump() is True
    assert p.jump_kind == "jump"
    sx, sy = p.squash_scale()
    assert sx < 1.0 < sy


def test_squashed_sprite_keeps_its_feet():
    _, g = _state()
    p = g.player
    img = p.animation.img()
    plain = pygame.Surface((64, 64), pygame.SRCALPHA)
    p.blit_sprite(plain, img, (p.pos[0] - 20, p.pos[1] - 20))
    p._land(MAX_FALL_SPEED)
    squashed = pygame.Surface((64, 64), pygame.SRCALPHA)
    p.blit_sprite(squashed, img, (p.pos[0] - 20, p.pos[1] - 20))
    a, b = plain.get_bounding_rect(), squashed.get_bounding_rect()
    assert b.bottom == a.bottom
    assert b.height < a.height

    def feet(surf, rect):  # opaque pixels in the lowest row
        mask = pygame.mask.from_surface(surf)
        return sum(mask.get_at((x, rect.bottom - 1)) for x in range(64))

    assert feet(squashed, b) > feet(plain, a)


def test_ghost_makes_no_sound_or_dust():
    _, g = _state()
    ghost = GhostPlayer(g, list(g.player.pos), (8, 15), 999)
    assert ghost.feedback() is False
    before = len(g.particles)
    ghost._land(MAX_FALL_SPEED)
    assert len(g.particles) == before


def test_a_kill_holds_the_picture_without_a_tick():
    state, g = _state()
    g.enemies[0].die(g.player)
    assert g.hitstop == HITSTOP_KILL_FRAMES
    tick = g.tick
    for _ in range(HITSTOP_KILL_FRAMES):
        state.update(1 / 60)
    assert g.tick == tick and g.hitstop == 0
    state.update(1 / 60)
    assert g.tick == tick + 1


def test_broken_block_leaves_rubble():
    _, g = _state()
    rect = pygame.Rect(0, 0, 16, 16)
    dust.rubble(g, rect, g.assets["crumble"][0])
    debris = [p for p in g.particles if isinstance(p, dust.Debris)]
    assert len(debris) >= 10
    start = debris[0].pos[1]
    for _ in range(20):
        debris[0].update()
    assert debris[0].pos[1] > start  # it falls


def test_every_effect_has_a_volume():
    assert set(SFX_NAMES) <= set(BASE_VOLUME)
    assert all(0 < v <= 1 for v in BASE_VOLUME.values())


def test_input_during_hitstop_waits_for_the_next_step():
    state, g = _state()
    g.hitstop = 2
    frames = g.replay.recording.data.duration_frames
    state.handle_actions(["jump"])
    assert state._held_actions == ["jump"]
    assert g.replay.recording.data.duration_frames == frames  # nothing recorded
    g.hitstop = 0
    state.handle_actions([])
    assert state._held_actions == []
    assert g.replay.recording.data.duration_frames == frames + 1
    assert "jump" in g.replay.recording.data.inputs[-1]["inputs"]


def test_hitstop_is_left_out_of_the_run_time(monkeypatch):
    state, g = _state()
    clock = {"now": 10_000}
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: clock["now"])
    g.hitstop = 3
    start = g.timer.start_time
    for _ in range(4):  # three held frames and the one that steps again
        state.update(1 / 60)
        clock["now"] += 17
    assert g.timer.start_time - start == 3 * 17


def test_world_music():
    assert music_for({"music": DEFAULT_MUSIC}) == DEFAULT_MUSIC
    assert music_for({"music": DEFAULT_MUSIC, "background": "background-mars.png"}).endswith("music_mars.wav")
    assert music_for({"background": "background-deep.png"}).endswith("music_sea.wav")
    assert music_for({"music": "data/music/mine.wav", "background": "background-mars.png"}) == "data/music/mine.wav"


def test_pitch_variant_is_shorter_when_faster():
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init()
        except pygame.error:
            pytest.skip("no audio device")
    freq, size, channels = pygame.mixer.get_init()
    if size != -16:
        pytest.skip("mixer format")
    snd = pygame.mixer.Sound(buffer=bytes(2 * channels * 4410))
    faster = _resampled(snd, 1.25)
    assert faster is not None
    assert faster.get_length() == pytest.approx(snd.get_length() / 1.25, rel=0.01)
