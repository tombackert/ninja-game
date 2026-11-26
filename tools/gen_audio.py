"""Synthesize the game's extra sound effects and the world music.

    python tools/gen_audio.py            # everything
    python tools/gen_audio.py sfx        # only data/sfx/<name>.wav
    python tools/gen_audio.py music      # only data/music/music_<world>.wav

Needs numpy (the game itself does not). Every sound is built from simple
oscillators, noise and envelopes in the chiptune style of the original
jump / dash / hit sounds, and the noise is seeded, so a run writes the same
files every time. The sky worlds keep music_0.wav; the desert, Mars and the
sea get their own loop (AudioService.music_for picks it by the level's sky).
"""

from __future__ import annotations

import os
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.path.join(ROOT, "data", "sfx")
MUSIC_DIR = os.path.join(ROOT, "data", "music")

SFX_RATE = 44100
MUSIC_RATE = 22050  # mono 16 bit: a 40 s loop is under 2 MB


# --- Building blocks -----------------------------------------------------


def write_wav(path: str, x: np.ndarray, rate: int) -> None:
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def samples(dur: float, rate: int) -> int:
    return max(1, int(round(dur * rate)))


def osc(kind: str, freq, dur: float, rate: int, duty: float = 0.5) -> np.ndarray:
    """One oscillator; `freq` is a number or an array (a sweep) of the same length."""
    n = samples(dur, rate)
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    phase = np.cumsum(f) / rate
    frac = phase % 1.0
    if kind == "sine":
        return np.sin(2 * np.pi * phase)
    if kind == "square":
        return np.where(frac < duty, 1.0, -1.0)
    if kind == "triangle":
        return 2 * np.abs(2 * frac - 1) - 1
    if kind == "saw":
        return 2 * frac - 1
    raise ValueError(kind)


def sweep(f0: float, f1: float, dur: float, rate: int, curve: float = 1.0) -> np.ndarray:
    """Frequencies from f0 to f1 (curve > 1 moves late, < 1 early)."""
    t = np.linspace(0, 1, samples(dur, rate)) ** curve
    return f0 + (f1 - f0) * t


def decay(dur: float, rate: int, tau: float, attack: float = 0.002) -> np.ndarray:
    n = samples(dur, rate)
    t = np.arange(n) / rate
    env = np.exp(-t / tau)
    a = samples(attack, rate)
    env[:a] *= np.linspace(0, 1, a)
    return env


def gate(dur: float, rate: int, attack: float, release: float) -> np.ndarray:
    """Flat envelope with a linear attack and release."""
    n = samples(dur, rate)
    env = np.ones(n)
    a = min(n, samples(attack, rate))
    r = min(n, samples(release, rate))
    env[:a] *= np.linspace(0, 1, a)
    env[n - r :] *= np.linspace(1, 0, r)
    return env


def lowpass(x: np.ndarray, width: int) -> np.ndarray:
    """A soft low-pass: convolution with a Hann window `width` samples wide."""
    if width <= 1:
        return x
    k = np.hanning(width + 2)[1:-1]
    return np.convolve(x, k / k.sum(), mode="same")


def highpass(x: np.ndarray, width: int) -> np.ndarray:
    return x - lowpass(x, width)


def pad_to(x: np.ndarray, n: int) -> np.ndarray:
    return np.pad(x, (0, max(0, n - len(x))))[:n] if len(x) != n else x


def mix(*parts: np.ndarray) -> np.ndarray:
    n = max(len(p) for p in parts)
    return sum(pad_to(p, n) for p in parts)


def seq(*parts: np.ndarray) -> np.ndarray:
    return np.concatenate(parts)


def silence(dur: float, rate: int) -> np.ndarray:
    return np.zeros(samples(dur, rate))


def normalize(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = np.max(np.abs(x))
    return x if m == 0 else x * (peak / m)


def fade_edges(x: np.ndarray, rate: int, ms: float = 3.0) -> np.ndarray:
    """No click at either end."""
    n = min(len(x) // 2, samples(ms / 1000, rate))
    x = x.copy()
    x[:n] *= np.linspace(0, 1, n)
    x[len(x) - n :] *= np.linspace(1, 0, n)
    return x


def midi_hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


# --- Sound effects -------------------------------------------------------


def make_sfx(rng: np.random.Generator) -> dict[str, np.ndarray]:
    R = SFX_RATE

    def noise(dur):
        return rng.uniform(-1, 1, samples(dur, R))

    out: dict[str, np.ndarray] = {}

    # Feet on the ground: a low thump and a puff of grit
    thump = osc("sine", sweep(170, 55, 0.11, R, 0.6), 0.11, R) * decay(0.11, R, 0.04)
    grit = lowpass(noise(0.07), 9) * decay(0.07, R, 0.018)
    out["land"] = mix(thump, grit * 0.5)

    # Kick off a wall: a low, soft push and a scuff of the sole (kept
    # below the dash, which should stand out more)
    push = osc("triangle", sweep(150, 290, 0.08, R, 0.6), 0.08, R) * decay(0.08, R, 0.032)
    scuff = lowpass(noise(0.05), 16) * decay(0.05, R, 0.015)
    out["wall_jump"] = mix(push * 0.8, scuff * 0.35)

    # Second jump in the air: a rising flutter
    f = sweep(520, 1040, 0.15, R, 0.8) * (1 + 0.04 * np.sin(2 * np.pi * 38 * np.arange(samples(0.15, R)) / R))
    flutter = osc("square", f, 0.15, R, 0.5) * decay(0.15, R, 0.07)
    air = lowpass(noise(0.15), 14) * gate(0.15, R, 0.02, 0.1)
    out["double_jump"] = mix(lowpass(flutter, 6) * 0.5, air * 0.25)

    # Water (own generators, so tuning them leaves the other sounds alone)
    out["swim"] = swim_stroke(np.random.default_rng(21))
    out["splash"] = splash(np.random.default_rng(22))

    # Landing on an enemy: a pop and a springy bounce
    pop = osc("square", sweep(240, 90, 0.07, R, 0.5), 0.07, R) * decay(0.07, R, 0.03)
    boing = osc("triangle", sweep(300, 620, 0.12, R, 0.6), 0.12, R) * decay(0.12, R, 0.06)
    out["stomp"] = mix(lowpass(pop, 4) * 0.8, seq(silence(0.03, R), boing * 0.6))

    # A coin: a two-note ping, picked up all the time, so mellow and short:
    # mid notes (E5, A5) on a triangle with a touch of glassy overtone
    def ping(note, dur, tau):
        f = midi_hz(note)
        tone = osc("triangle", f, dur, R) + 0.2 * osc("sine", f * 2, dur, R) * decay(dur, R, tau / 2)
        return tone * decay(dur, R, tau)

    n1 = ping(76, 0.05, 0.04) * gate(0.05, R, 0.002, 0.008)
    n2 = ping(81, 0.22, 0.07)
    out["coin"] = seq(n1, n2)

    # A heart: a quick major arpeggio up
    notes = [72, 76, 79, 84]
    arp = [osc("triangle", midi_hz(m), 0.07, R) * gate(0.07, R, 0.003, 0.01) for m in notes[:-1]]
    last = osc("triangle", midi_hz(notes[-1]), 0.3, R) * decay(0.3, R, 0.12)
    out["heart"] = seq(*arp, last)

    # Checkpoint: a two-note bell
    def bell(note, dur):
        f = midi_hz(note)
        tone = osc("sine", f, dur, R) + 0.45 * osc("sine", f * 2.76, dur, R) * decay(dur, R, 0.08)
        return tone * decay(dur, R, dur / 3.5)

    out["checkpoint"] = mix(bell(79, 0.9), seq(silence(0.13, R), bell(86, 0.9)))

    # Death: a falling, wobbling slide and a crunch
    d = 0.65
    wob = 1 + 0.06 * np.sin(2 * np.pi * 9 * np.arange(samples(d, R)) / R)
    slide = osc("square", sweep(620, 70, d, R, 0.7) * wob, d, R, 0.5) * gate(d, R, 0.005, 0.2)
    crunch = lowpass(noise(0.18), 4) * decay(0.18, R, 0.05)
    out["death"] = mix(lowpass(slide, 7) * 0.55, crunch * 0.5)

    # Level clear: an arpeggio up into a held chord
    up = [72, 76, 79, 84, 88]
    steps = [
        (osc("square", midi_hz(m), 0.085, R, 0.25) * 0.5 + osc("triangle", midi_hz(m), 0.085, R) * 0.5)
        * gate(0.085, R, 0.003, 0.012)
        for m in up
    ]
    chord = sum(
        osc("square", midi_hz(m), 0.9, R, 0.25) * 0.25 + osc("triangle", midi_hz(m), 0.9, R) * 0.35
        for m in (84, 88, 91)
    ) * decay(0.9, R, 0.35)
    out["level_clear"] = lowpass(seq(*steps, chord), 4)

    # Menus: a tick to move, a blip to choose, a lower blip to go back
    out["menu_move"] = osc("square", 1250, 0.03, R, 0.5) * decay(0.03, R, 0.01)
    out["menu_select"] = lowpass(
        seq(
            osc("square", midi_hz(76), 0.05, R, 0.5) * gate(0.05, R, 0.002, 0.005),
            osc("square", midi_hz(83), 0.11, R, 0.5) * decay(0.11, R, 0.04),
        ),
        3,
    )
    out["menu_back"] = lowpass(
        seq(
            osc("square", midi_hz(76), 0.05, R, 0.5) * gate(0.05, R, 0.002, 0.005),
            osc("square", midi_hz(69), 0.1, R, 0.5) * decay(0.1, R, 0.035),
        ),
        3,
    )

    # Running out of air: two short warning beeps
    beep = osc("square", 880, 0.07, R, 0.5) * gate(0.07, R, 0.003, 0.02)
    out["breath_low"] = lowpass(seq(beep, silence(0.06, R), beep), 3)

    out["crumble"] = crumble(np.random.default_rng(23))

    return {name: fade_edges(normalize(x), R) for name, x in out.items()}


# --- Physically inspired effects: water and stone ------------------------
#
# Real water sounds are mostly bubbles: each rings like a damped sine whose
# pitch rises as it closes (smaller bubble, higher pitch). Gravel and rubble
# are clouds of tiny noise grains. Both are built from many small events at
# random times rather than one oscillator, which is what makes them sound
# like the real thing instead of a synth.


def bandpass(x: np.ndarray, narrow: int, wide: int) -> np.ndarray:
    """Keep the band between the two Hann low-passes (narrow < wide samples)."""
    return lowpass(x, narrow) - lowpass(x, wide)


def bubble(f0: float, tau: float, rise: float, rate: int = SFX_RATE) -> np.ndarray:
    """One bubble: a sine at f0 Hz that rises by `rise` (0.5 = +50 %) per
    decay time `tau` seconds while it dies away."""
    n = samples(tau * 6, rate)
    t = np.arange(n) / rate
    f = f0 * (1 + rise * t / tau)
    x = np.sin(2 * np.pi * np.cumsum(f) / rate) * np.exp(-t / tau)
    a = samples(0.0006, rate)
    x[:a] *= np.linspace(0, 1, a)
    return x


def place(buf: np.ndarray, at: float, x: np.ndarray, gain: float = 1.0, rate: int = SFX_RATE) -> None:
    start = samples(at, rate) if at > 0 else 0
    end = min(len(buf), start + len(x))
    buf[start:end] += x[: end - start] * gain


def bubble_cloud(rng, buf, start, dur, count, fmin, fmax, gain=1.0, cluster=2.0):
    """`count` bubbles from `start` on, most early (cluster > 1), sizes log-uniform."""
    for _ in range(count):
        at = start + dur * rng.random() ** cluster
        f0 = fmin * (fmax / fmin) ** rng.random()
        tau = rng.uniform(0.006, 0.02) * (900 / f0) ** 0.5
        amp = (fmin / f0) ** 0.4 * rng.uniform(0.4, 1.0)
        place(buf, at, bubble(f0, tau, rng.uniform(0.15, 0.5)), gain * amp)


def splash(rng) -> np.ndarray:
    """Plunging into water: the slap on the surface, the deep "bloop" of
    the air pocket closing behind the body, a burst of bubbles and the
    water washing back."""
    R = SFX_RATE
    buf = np.zeros(samples(0.7, R))
    n = samples(0.12, R)
    slap = bandpass(rng.uniform(-1, 1, n), 3, 18) * decay(0.12, R, 0.022, attack=0.0008)
    body = bandpass(rng.uniform(-1, 1, n), 18, 110) * decay(0.12, R, 0.04, attack=0.002)
    place(buf, 0, slap, 0.45)
    place(buf, 0, body, 0.6)
    place(buf, 0.018, bubble(170, 0.05, 1.3), 0.9)  # the plunge
    place(buf, 0.05, bubble(260, 0.035, 1.0), 0.45)
    bubble_cloud(rng, buf, 0.03, 0.45, 34, 450, 2600, gain=0.35, cluster=2.2)
    m = samples(0.5, R)
    wash = lowpass(rng.uniform(-1, 1, m), 40) * gate(0.5, R, 0.06, 0.4) * decay(0.5, R, 0.18)
    place(buf, 0.04, wash, 0.5)
    return buf


def swim_stroke(rng) -> np.ndarray:
    """An arm pulling through water: a soft swish and a few small bubbles."""
    R = SFX_RATE
    buf = np.zeros(samples(0.36, R))
    n = samples(0.24, R)
    swish = bandpass(rng.uniform(-1, 1, n), 12, 90) * gate(0.24, R, 0.07, 0.15)
    place(buf, 0, swish, 0.5)
    place(buf, 0.05, bubble(320, 0.028, 0.9), 0.35)
    bubble_cloud(rng, buf, 0.06, 0.22, 7, 700, 2200, gain=0.25, cluster=1.5)
    return buf


def crumble(rng) -> np.ndarray:
    """Stone giving way: a sharp snap, a dull thump, then gravel and a few
    bigger chunks pattering down, dense at first and thinning out."""
    R = SFX_RATE
    buf = np.zeros(samples(0.65, R))
    snap = bandpass(rng.uniform(-1, 1, samples(0.03, R)), 2, 10) * decay(0.03, R, 0.005, attack=0.0002)
    ping = osc("sine", 2300, 0.03, R) * decay(0.03, R, 0.007)
    place(buf, 0, snap, 0.8)
    place(buf, 0, ping, 0.15)
    thump = osc("sine", sweep(95, 50, 0.15, R, 0.5), 0.15, R) * decay(0.15, R, 0.045)
    place(buf, 0.004, thump, 0.75)
    for _ in range(140):  # gravel
        at = 0.01 + 0.5 * rng.random() ** 1.7
        dur = rng.uniform(0.002, 0.007)
        grain = rng.uniform(-1, 1, samples(dur, R)) * np.hanning(samples(dur, R))
        grain = bandpass(grain, 2, 14) if rng.random() < 0.6 else lowpass(grain, 6)
        place(buf, at, grain, np.exp(-at / 0.16) * rng.uniform(0.25, 0.8))
    for _ in range(6):  # chunks hitting the ground below
        at = rng.uniform(0.06, 0.4)
        f0 = rng.uniform(140, 320)
        chunk = osc("sine", f0, 0.05, R) * decay(0.05, R, 0.012)
        chunk += bandpass(rng.uniform(-1, 1, samples(0.05, R)), 6, 30) * decay(0.05, R, 0.008)
        place(buf, at, chunk, 0.35 * np.exp(-at / 0.3))
    return buf


# --- Music ---------------------------------------------------------------


class Song:
    """A loop of `bars` bars at `bpm`; parts are placed by 16th-note step."""

    def __init__(self, bpm: float, bars: int, rate: int = MUSIC_RATE):
        self.rate = rate
        self.step = 60.0 / bpm / 4
        self.bars = bars
        self.length = samples(self.step * 16 * bars, rate)
        tail = samples(3.0, rate)
        self.buses: dict[str, np.ndarray] = {}
        self._size = self.length + tail

    def bus(self, name: str) -> np.ndarray:
        if name not in self.buses:
            self.buses[name] = np.zeros(self._size)
        return self.buses[name]

    def put(self, bus: str, bar: int, step: float, sound: np.ndarray, gain: float = 1.0) -> None:
        start = samples((bar * 16 + step) * self.step, self.rate)
        buf = self.bus(bus)
        end = min(len(buf), start + len(sound))
        buf[start:end] += sound[: end - start] * gain

    def loop(self, buf: np.ndarray) -> np.ndarray:
        """Fold the tail past the loop end back onto its start (seamless loop)."""
        out = buf[: self.length].copy()
        tail = buf[self.length :]
        out[: len(tail)] += tail[: self.length]
        return out

    def dur(self, steps: float) -> float:
        return steps * self.step


def echo(x: np.ndarray, rate: int, delay: float, feedback: float, taps: int = 4) -> np.ndarray:
    """Circular echo: the repeats wrap around, so the loop stays seamless."""
    d = samples(delay, rate)
    out = x.copy()
    for i in range(1, taps + 1):
        out += np.roll(lowpass(x, 2 + 2 * i), i * d) * feedback**i
    return out


class Instruments:
    def __init__(self, rate: int, rng: np.random.Generator):
        self.R = rate
        self.rng = rng

    def noise(self, dur):
        return self.rng.uniform(-1, 1, samples(dur, self.R))

    # Melodic
    def pluck(self, note, dur):
        """Bright, quickly fading pluck (oud-like on the desert)."""
        d = max(dur, 0.35)
        f = midi_hz(note)
        x = 0.6 * osc("saw", f, d, self.R) + 0.4 * osc("square", f * 1.003, d, self.R, 0.3)
        return lowpass(x, 3) * decay(d, self.R, 0.16, attack=0.003)

    def lead(self, note, dur, duty=0.25, vibrato=True):
        f = midi_hz(note)
        n = samples(dur, self.R)
        t = np.arange(n) / self.R
        vib = 1 + (0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.18) / 0.2, 0, 1) if vibrato else 0)
        x = osc("square", f * vib, dur, self.R, duty) * 0.5 + osc("triangle", f * vib, dur, self.R) * 0.5
        return lowpass(x, 4) * gate(dur, self.R, 0.01, min(0.08, dur / 3))

    def soft(self, note, dur):
        """Rounded triangle voice (the sea)."""
        f = midi_hz(note)
        x = osc("triangle", f, dur, self.R) + 0.15 * osc("sine", f * 2, dur, self.R)
        return x * gate(dur, self.R, 0.02, min(0.15, dur / 2))

    def bell(self, note, dur):
        d = max(dur, 0.8)
        f = midi_hz(note)
        x = osc("sine", f, d, self.R) + 0.3 * osc("sine", f * 3.0, d, self.R) * decay(d, self.R, 0.1)
        return x * decay(d, self.R, 0.35)

    def pulse(self, note, dur):
        d = max(dur, 0.12)
        return lowpass(osc("square", midi_hz(note), d, self.R, 0.125), 4) * decay(d, self.R, 0.07)

    def pad(self, notes, dur):
        x = 0
        for note in notes:
            f = midi_hz(note)
            for detune in (0.996, 1.0, 1.004):
                x = x + osc("saw", f * detune, dur + 0.6, self.R)
        x = lowpass(x / (3 * len(notes)), 16)
        return x * gate(dur + 0.6, self.R, 0.35, 0.6)

    def bass(self, note, dur):
        f = midi_hz(note)
        x = osc("triangle", f, dur, self.R) * 0.8 + osc("square", f, dur, self.R, 0.5) * 0.2
        return lowpass(x, 3) * gate(dur, self.R, 0.005, 0.03) * decay(dur, self.R, 0.6)

    # Drums
    def kick(self):
        d = 0.18
        return osc("sine", sweep(140, 42, d, self.R, 0.4), d, self.R) * decay(d, self.R, 0.07)

    def snare(self):
        d = 0.16
        tone = osc("triangle", 190, d, self.R) * decay(d, self.R, 0.04)
        return highpass(self.noise(d), 3) * decay(d, self.R, 0.05) * 0.7 + tone * 0.4

    def hat(self, tau=0.018):
        d = 0.06
        return highpass(self.noise(d), 2) * decay(d, self.R, tau)

    def tom(self, f0=160):
        d = 0.25
        return osc("sine", sweep(f0, f0 * 0.6, d, self.R, 0.5), d, self.R) * decay(d, self.R, 0.09)

    def tek(self):
        d = 0.07
        return (
            highpass(self.noise(d), 2) * decay(d, self.R, 0.015) * 0.6
            + osc("sine", 820, d, self.R) * decay(d, self.R, 0.012) * 0.4
        )


def master(song: Song, mixes: dict[str, float], fx: dict[str, callable] | None = None) -> np.ndarray:
    total = np.zeros(song.length)
    for name, buf in song.buses.items():
        x = song.loop(buf)
        if fx and name in fx:
            x = fx[name](x)
        total += x * mixes.get(name, 1.0)
    total = np.tanh(normalize(total, 1.0) * 1.2) / np.tanh(1.2)
    return normalize(total, 0.8)


def place_melody(song: Song, inst, bar0: int, phrase, root: int, bus: str = "melody", gain: float = 1.0):
    """phrase: per bar a list of (step, semitones from root, length in steps)."""
    for b, notes in enumerate(phrase):
        for step, semi, length in notes:
            song.put(bus, bar0 + b, step, inst(root + semi, song.dur(length)), gain)


def desert(rng) -> np.ndarray:
    """D Hijaz (D Eb F# G A Bb C), 100 bpm: plucked melody, drone, hand drums."""
    s = Song(bpm=100, bars=16)
    inst = Instruments(s.rate, rng)
    root = 62  # D4
    phrases = {
        "A": [
            [(0, 7, 2), (2, 8, 2), (4, 7, 2), (6, 5, 2), (8, 4, 4), (12, 1, 2), (14, 4, 2)],
            [(0, 0, 6), (8, 1, 2), (10, 4, 2), (12, 5, 4)],
        ],
        "B": [
            [(0, 7, 2), (2, 8, 2), (4, 10, 2), (6, 12, 2), (8, 10, 4), (12, 8, 2), (14, 7, 2)],
            [(0, 5, 4), (4, 4, 2), (6, 1, 2), (8, 0, 8)],
        ],
        "C": [
            [(0, 12, 4), (4, 10, 2), (6, 8, 2), (8, 7, 6), (14, 8, 2)],
            [(0, 7, 2), (2, 5, 2), (4, 4, 4), (8, 5, 2), (10, 7, 2), (12, 4, 4)],
        ],
        "D": [
            [(0, 8, 3), (3, 7, 3), (6, 5, 2), (8, 4, 2), (10, 1, 2), (12, 4, 4)],
            [(0, 0, 12)],
        ],
    }
    roots = {"A": [0, 0], "B": [-2, 0], "C": [5, 0], "D": [-2, 0]}
    order = ["A", "B", "A", "D", "C", "B", "C", "D"]
    for i, name in enumerate(order):
        bar = i * 2
        place_melody(s, inst.pluck, bar, phrases[name], root)
        if i >= 4:  # second half: an octave-down echo of the tune
            place_melody(s, inst.pluck, bar, phrases[name], root - 12, bus="double", gain=0.5)
        for b, r in enumerate(roots[name]):
            bass_note = root - 24 + r
            for step, interval in ((0, 0), (6, 0), (8, 7), (12, 0)):
                s.put("bass", bar + b, step, inst.bass(bass_note + interval, s.dur(3)))
            s.put("drone", bar + b, 0, inst.pad([root - 12, root - 5], s.dur(16)))
    for bar in range(s.bars):
        for step in (0, 6, 8):
            s.put("drums", bar, step, inst.tom(150 if step else 120), 0.9)
        for step in (4, 12):
            s.put("drums", bar, step, inst.tek(), 0.7)
        for step in (2, 10, 14):
            s.put("drums", bar, step, inst.tek(), 0.35)
        if bar % 4 == 3:
            s.put("drums", bar, 15, inst.tek(), 0.5)
    return master(
        s,
        {"melody": 0.55, "double": 0.35, "bass": 0.5, "drone": 0.25, "drums": 0.45},
        {"melody": lambda x: echo(x, s.rate, s.dur(3), 0.25, 3)},
    )


def mars(rng) -> np.ndarray:
    """A minor, 84 bpm: slow pad, pulsing arpeggio, a lead that comes in halfway."""
    s = Song(bpm=84, bars=16)
    inst = Instruments(s.rate, rng)
    root = 57  # A3
    chords = [(0, [0, 3, 7]), (-4, [0, 4, 7]), (5, [0, 3, 7]), (7, [0, 4, 7])]  # Am F Dm E
    melody = [
        [[(0, 7, 6), (6, 5, 2), (8, 3, 8)], [(0, 2, 4), (4, 3, 4), (8, 0, 8)]],
        [[(0, 3, 6), (6, 7, 2), (8, 8, 8)], [(0, 7, 8), (8, 3, 8)]],
        [[(0, 5, 6), (6, 3, 2), (8, 2, 4), (12, 3, 4)], [(0, 5, 12), (12, 7, 4)]],
        [[(0, 8, 4), (4, 7, 4), (8, 11, 8)], [(0, 12, 8), (8, 11, 4), (12, 7, 4)]],
    ]
    arp = [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 4, 3, 2, 1, 2, 3]
    for i in range(8):
        bar = i * 2
        r, shape = chords[i % 4]
        tones = [root + r + t for t in shape]
        s.put("pad", bar, 0, inst.pad([t + 12 for t in tones], s.dur(32)))
        ladder = [t + 12 for t in tones] + [tones[0] + 24, tones[1] + 24]
        for b in range(2):
            for step, k in enumerate(arp):
                s.put("arp", bar + b, step, inst.pulse(ladder[k], s.dur(1)))
            for step in (0, 8, 14):
                s.put("bass", bar + b, step, inst.bass(root - 12 + r, s.dur(2 if step == 14 else 5)))
        if i >= 4:
            place_melody(s, inst.lead, bar, melody[i % 4], root + 12)
    for bar in range(s.bars):
        s.put("drums", bar, 0, inst.kick())
        s.put("drums", bar, 8, inst.kick(), 0.8 if bar % 2 else 1.0)
        if bar % 2:
            s.put("drums", bar, 10, inst.kick(), 0.6)
        if bar >= 4:
            for step in (4, 12):
                s.put("drums", bar, step, inst.snare(), 0.5)
        for step in range(2, 16, 4):
            s.put("drums", bar, step, inst.hat(), 0.3)
    return master(
        s,
        {"pad": 0.4, "arp": 0.22, "bass": 0.55, "melody": 0.45, "drums": 0.45},
        {
            "arp": lambda x: echo(x, s.rate, s.dur(3), 0.35, 3),
            "melody": lambda x: echo(x, s.rate, s.dur(6), 0.3, 3),
        },
    )


def sea(rng) -> np.ndarray:
    """F lydian, 92 bpm: bell arpeggios with echo, a soft tune and shakers."""
    s = Song(bpm=92, bars=16)
    inst = Instruments(s.rate, rng)
    root = 65  # F4
    chords = [(0, [0, 4, 7, 11]), (2, [2, 6, 9, 14]), (4, [4, 7, 11, 14]), (5, [5, 9, 12, 16])]  # F G Am Bb
    melody = [
        [[(0, 12, 4), (4, 14, 2), (6, 16, 6), (12, 19, 4)], [(0, 16, 8), (8, 14, 8)]],
        [[(0, 18, 4), (4, 16, 2), (6, 14, 6), (12, 11, 4)], [(0, 14, 12), (12, 9, 4)]],
        [[(0, 16, 4), (4, 19, 4), (8, 23, 4), (12, 21, 4)], [(0, 19, 8), (8, 16, 8)]],
        [[(0, 17, 6), (6, 16, 2), (8, 14, 4), (12, 12, 4)], [(0, 9, 8), (8, 12, 8)]],
    ]
    arp = [0, 1, 2, 3, 2, 1, 2, 3]
    for i in range(8):
        bar = i * 2
        r, shape = chords[i % 4]
        tones = [root + t for t in shape]
        for b in range(2):
            for k, idx in enumerate(arp):
                s.put("bells", bar + b, k * 2, inst.bell(tones[idx], s.dur(2)))
            for step, length in ((0, 6), (6, 4), (10, 6)):
                s.put("bass", bar + b, step, inst.bass(root - 24 + r + (12 if step == 10 else 0), s.dur(length)))
        voice = inst.soft if i >= 4 else inst.bell
        place_melody(s, voice, bar, melody[i % 4], root - 12 + 12, gain=1.0 if i >= 4 else 0.6)
    for bar in range(s.bars):
        for step in range(16):
            s.put("shaker", bar, step, inst.hat(0.03), 0.5 if step % 4 == 2 else 0.22)
        s.put("drums", bar, 0, inst.kick(), 0.8)
        s.put("drums", bar, 10, inst.kick(), 0.5)
        if bar >= 4:
            s.put("drums", bar, 8, inst.tom(220), 0.35)
    return master(
        s,
        {"bells": 0.3, "bass": 0.5, "melody": 0.5, "shaker": 0.12, "drums": 0.4},
        {
            "bells": lambda x: echo(x, s.rate, s.dur(3), 0.4, 4),
            "melody": lambda x: echo(x, s.rate, s.dur(6), 0.3, 3),
        },
    )


MUSIC = {"desert": desert, "mars": mars, "sea": sea}


# --- Loudness balance ----------------------------------------------------
#
# How loud each effect should sound, in dB against a plain jump. The
# special moves and big moments sit above it, the frequent small ones
# (coins, stomps, swim strokes, menus) below. `python tools/gen_audio.py
# balance` measures every file and prints the AudioService.BASE_VOLUME that
# gets there; paste it into scripts/audio_service.py.
TARGET_DB = {
    "jump": 0.0,
    "wall_jump": 0.0,
    "double_jump": 0.0,
    "land": -5.0,  # at full strength; softer landings play quieter still
    "dash": -6.0,  # the signature move, but frequent: its brightness carries it
    "hit": 4.0,  # a dash or sword kill, a bullet, the ninja getting hurt
    "stomp": -1.0,  # a kill too, but frequent and plain
    "shoot": -1.0,
    "coin": -8.0,
    "collect": -6.0,
    "heart": -2.0,
    "checkpoint": -1.0,
    "death": 3.0,
    "level_clear": 1.0,
    "splash": -2.0,
    "swim": -7.0,
    "crumble": -2.0,
    "breath_low": -3.0,
    "menu_move": -11.0,
    "menu_select": -7.0,
    "menu_back": -8.0,
}
REFERENCE = "jump"
REFERENCE_VOLUME = 0.7  # the jump's base volume so far; all others follow it


def a_weighting(freqs: np.ndarray) -> np.ndarray:
    """IEC 61672 A-weighting as a linear gain (how loud the ear finds each frequency)."""
    f2 = np.maximum(freqs, 1e-3) ** 2
    ra = (12194.0**2 * f2**2) / ((f2 + 20.6**2) * np.sqrt((f2 + 107.7**2) * (f2 + 737.9**2)) * (f2 + 12194.0**2))
    return ra * 10 ** (2.0 / 20)


def loudness_db(x: np.ndarray, rate: int) -> float:
    """Peak short-term loudness: the loudest 50 ms of the A-weighted sound, in dB."""
    spec = np.fft.rfft(x)
    weighted = np.fft.irfft(spec * a_weighting(np.fft.rfftfreq(len(x), 1 / rate)), len(x))
    win, hop = samples(0.05, rate), samples(0.0125, rate)
    if len(weighted) <= win:
        rms = np.sqrt(np.mean(weighted**2))
    else:
        rms = max(np.sqrt(np.mean(weighted[i : i + win] ** 2)) for i in range(0, len(weighted) - win, hop))
    return 20 * np.log10(max(rms, 1e-9))


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(axis=1)
        return x, w.getframerate()


def balance() -> dict[str, float]:
    """Base volumes that put every effect at its TARGET_DB (none above 1.0)."""
    level = {name: loudness_db(*read_wav(os.path.join(SFX_DIR, f"{name}.wav"))) for name in TARGET_DB}
    ref = level[REFERENCE]
    gains = {name: 10 ** ((TARGET_DB[name] - (level[name] - ref)) / 20) for name in TARGET_DB}
    scale = min(REFERENCE_VOLUME, 1.0 / max(gains.values()))
    return {name: round(g * scale, 3) for name, g in gains.items()}


def main(argv: list[str]) -> None:
    if argv == ["balance"]:
        for name, v in balance().items():
            print(f'    "{name}": {v},')
        return
    what = set(argv) or {"sfx", "music"}
    if "sfx" in what:
        for name, x in make_sfx(np.random.default_rng(7)).items():
            path = os.path.join(SFX_DIR, f"{name}.wav")
            write_wav(path, x, SFX_RATE)
            print(f"{os.path.relpath(path, ROOT)}  {len(x) / SFX_RATE:.2f} s")
    if "music" in what:
        for name, build in MUSIC.items():
            x = build(np.random.default_rng(11))
            path = os.path.join(MUSIC_DIR, f"music_{name}.wav")
            write_wav(path, x, MUSIC_RATE)
            print(f"{os.path.relpath(path, ROOT)}  {len(x) / MUSIC_RATE:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
