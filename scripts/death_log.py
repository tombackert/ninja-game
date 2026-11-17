"""Death log: one JSON line per lost life, for calibrating the difficulty rating.

Every death ends in one place: the death and respawn block of
`GameState.update` (scripts/state_manager.py), where the level reloads at the
respawn point, or the game over screen opens once no life is left. That block writes the
line, once per death (`record_death`). The places where a death starts only
name its cause (`set_cause`; the first cause of a death wins):

- `Player.update` (scripts/entities.py): "air_time", "fell_out" (below the
  kill line), "breath";
- the R key (scripts/keyboardManager.py): "restart";
- the death block itself: "out_of_lives" (bullets took the last life).

A bullet costs a life without a death (scripts/projectile_system.py), so it
is logged as a "hit" event of its own. The log also notes the manual
checkpoint ("save", the P key), the level's clear ("clear") and leaving the
level unfinished ("quit"), so attempts per element can be counted: every
attempt ends in a death, a clear or a quit.

The log records a human's single-player play only:
- `app.main()` switches it on (`enable`), unless NINJA_DEATH_LOG=0;
- `GameState` hands it to its `Game` (`DeathLog.bind`). Every site asks the
  game for its log, so a `Game` without one logs nothing.
Multiplayer (its own state), the route bot (tools/worlds/play.py sets
NINJA_DEATH_LOG=0), the benchmark, the trailer and the training runs (they
drive `GameState` or `Game` without `app.main()`) never see it.

Lines go to data/deaths/<level>.jsonl, a few hundred bytes each:

    {"event": "death", "cause": "fell_out", "level": 26, "attempt": 3,
     "session": "2026-11-06T14:03:11", "session_s": 312.4,
     "at": "2026-11-06T14:08:23", "tick": 1834, "attempt_ticks": 812,
     "pos": [1203.5, 340.0], "respawn": [1104, 352], "checkpoint": 0,
     "checkpoints": [0], "lives": 2, "restart": false,
     "map": "3f2a9c0d1e4b", "gear": "None"}

- `attempt`: the level's attempts in this session (app start), from 1;
- `tick`: the game's simulation tick since the level was entered, at the
  frame the death began; `attempt_ticks`: ticks since the last (re)load;
- `pos`: the player's position (px, top left) where the death began;
  `respawn`: where the player comes back; `checkpoint` (every line): the
  furthest banner reached (index west to east, or null), `checkpoints`: all;
- `restart`: the level starts over (no life left) instead of a respawn;
- `map`: the first 12 hex digits of the map file's SHA-1, so lines of an
  older map version can be told apart.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from typing import Any, Callable

from scripts.logger import get_logger

DEATHS_DIR = os.path.join("data", "deaths")
ENV_SWITCH = "NINJA_DEATH_LOG"  # "0" switches the log off

CAUSES = ("air_time", "fell_out", "breath", "restart", "out_of_lives")

_log = get_logger("death_log")
_session: "DeathLog | None" = None


def enable(directory: str = DEATHS_DIR) -> "DeathLog | None":
    """Switch the log on for this process (app.main). Returns it, or None
    when NINJA_DEATH_LOG=0."""
    global _session
    if os.environ.get(ENV_SWITCH, "1") == "0":
        _session = None
        return None
    if _session is None or _session.directory != directory:
        _session = DeathLog(directory)
    return _session


def disable() -> None:
    global _session
    _session = None


def current() -> "DeathLog | None":
    return _session


def _of(game) -> "DeathLog | None":
    log = getattr(game, "death_log", None)
    return log if isinstance(log, DeathLog) and log.game is game else None


def set_cause(game, cause: str, entity=None) -> None:
    """Name the cause of the death that starts now. Only the game's own player
    counts (not a ghost or another player), and the first cause wins."""
    log = _of(game)
    if log is not None and (entity is None or entity is getattr(game, "player", None)):
        log.set_cause(cause)


def record_death(game, restart: bool) -> None:
    log = _of(game)
    if log is not None:
        log.record_death(restart)


def record_hit(game, player, absorbed: bool = False) -> None:
    log = _of(game)
    if log is not None and player is getattr(game, "player", None):
        log.record_event("hit", absorbed=bool(absorbed), lives=_lives(player))


def record_save(game) -> None:
    log = _of(game)
    if log is not None:
        log.record_event("save", saves=getattr(game, "saves", None))


def record_clear(game) -> None:
    log = _of(game)
    if log is not None:
        log.record_end("clear")


def record_quit(game) -> None:
    log = _of(game)
    if log is not None:
        log.record_end("quit", dead=bool(getattr(game, "dead", 0)))


def _lives(player) -> int:
    return int(getattr(player, "lives", getattr(player, "lifes", 0)))


def _xy(pos) -> list:
    return [round(float(pos[0]), 1), round(float(pos[1]), 1)]


class DeathLog:
    """The log of one session (one app start)."""

    def __init__(self, directory: str = DEATHS_DIR, clock: Callable[[], float] = time.monotonic):
        self.directory = directory
        self._clock = clock
        self._t0 = clock()
        self.session = datetime.now().isoformat(timespec="seconds")
        self._attempts: dict = {}  # level -> attempt number in this session
        self._map_sha: dict = {}  # (path, mtime) -> sha
        self.game = None
        self._attempt_start = 0  # tick of the last (re)load
        self._pending: tuple | None = None  # (cause, tick, pos) of the death in progress
        self._ended = False  # the bound game's level was cleared or left

    # --- wiring ------------------------------------------------------------
    def bind(self, game) -> None:
        """Log `game` from now on (GameState builds one Game per level start)."""
        self.game = game
        game.death_log = self
        self._attempt_start = int(getattr(game, "tick", 0))
        self._pending = None
        self._ended = False

    # --- events ------------------------------------------------------------
    def set_cause(self, cause: str) -> None:
        if self._pending is None:
            g = self.game
            self._pending = (cause, int(getattr(g, "tick", 0)), _xy(g.player.pos))

    def record_death(self, restart: bool) -> None:
        g = self.game
        p = g.player
        cause, tick, pos = self._pending or ("unknown", int(getattr(g, "tick", 0)), _xy(p.pos))
        line = self._line("death", tick=tick, pos=pos)
        line.update(cause=cause, respawn=_xy(p.respawn_pos), lives=_lives(p), restart=bool(restart))
        self._write(line)
        self._next_attempt()

    def record_event(self, kind: str, **fields: Any) -> None:
        line = self._line(kind)
        line.update(fields)
        self._write(line)

    def record_end(self, kind: str, **fields: Any) -> None:
        """The attempt ends without a death: the level is cleared or left."""
        if self._ended:
            return
        g = self.game
        timer = getattr(g, "timer", None)
        line = self._line(kind)
        line.update(fields)
        line["run_ms"] = int(getattr(timer, "elapsed_time", 0) or 0)
        self._write(line)
        self._ended = True
        self._next_attempt()

    # --- helpers -----------------------------------------------------------
    def attempt(self, level) -> int:
        return self._attempts.get(str(level), 1)

    def _next_attempt(self) -> None:
        g = self.game
        key = str(g.level)
        self._attempts[key] = self.attempt(key) + 1
        self._attempt_start = int(getattr(g, "tick", 0))
        self._pending = None

    def _line(self, kind: str, tick: int | None = None, pos=None) -> dict:
        g = self.game
        if tick is None:
            tick = int(getattr(g, "tick", 0))
        line = {
            "event": kind,
            "level": g.level,
            "attempt": self.attempt(g.level),
            "session": self.session,
            "session_s": round(self._clock() - self._t0, 2),
            "at": datetime.now().isoformat(timespec="seconds"),
            "tick": tick,
            "attempt_ticks": tick - self._attempt_start,
            "pos": pos if pos is not None else _xy(g.player.pos),
            "map": self._map_hash(g),
            "gear": _gear(),
        }
        reached = sorted(getattr(g.player, "checkpoints_reached", ()) or ())
        line["checkpoint"] = reached[-1] if reached else None
        line["checkpoints"] = reached
        return line

    def _map_hash(self, game) -> str | None:
        path = getattr(getattr(game, "tilemap", None), "loaded_path", None)
        if not path:
            return None
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            return None
        if key not in self._map_sha:
            try:
                with open(path, "rb") as f:
                    self._map_sha[key] = hashlib.sha1(f.read()).hexdigest()[:12]
            except OSError:
                return None
        return self._map_sha[key]

    def path(self, level) -> str:
        return os.path.join(self.directory, f"{level}.jsonl")

    def _write(self, line: dict) -> None:
        """Append one line; a failing disk never stops the game."""
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(self.path(line["level"]), "a", encoding="utf-8") as f:
                f.write(json.dumps(line, separators=(",", ":")) + "\n")
        except OSError as exc:  # pragma: no cover - disk trouble
            _log.warn("death log not written:", exc)


def _gear() -> str:
    try:
        from scripts.collectableManager import CollectableManager
        from scripts.settings import settings

        return CollectableManager.GEAR[settings.selected_gear]
    except Exception:
        return "None"


def read(level, directory: str = DEATHS_DIR) -> list:
    """All lines of a level's log (for the tools: read only)."""
    path = os.path.join(directory, f"{level}.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    return out


__all__ = [
    "CAUSES",
    "DEATHS_DIR",
    "DeathLog",
    "ENV_SWITCH",
    "current",
    "disable",
    "enable",
    "read",
    "record_clear",
    "record_death",
    "record_hit",
    "record_quit",
    "record_save",
    "set_cause",
]
