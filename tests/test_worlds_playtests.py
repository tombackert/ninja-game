"""Playtests from the death log against the model (tools/worlds/playtests.py)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

from tools.worlds import playtests as PT  # noqa: E402
from tools.worlds import windows as W  # noqa: E402
from tools.worlds.compose import Composed, Press  # noqa: E402


def _ln(event, tick, **kw):
    return {"event": event, "tick": tick, "map": "m", **kw}


def test_the_first_clear_adds_up_the_entries_before_it():
    lines = [
        _ln("quit", 300),  # entered, left after 5 s
        _ln("hit", 100),  # entered again: ticks start over
        _ln("death", 1200),
        _ln("save", 1500),
        _ln("death", 2400),
        _ln("clear", 6000),
        _ln("death", 50),  # after the clear: not part of it
    ]
    o = PT.observed(31, lines, map_hash="m")
    assert o.cleared and o.entries == 2
    assert o.seconds == (300 + 6000) / 60
    assert (o.deaths, o.hits, o.saves, o.stale) == (2, 1, 1, 0)


def test_a_level_never_cleared_is_reported_as_such():
    o = PT.observed(36, [_ln("hit", 800), _ln("quit", 3600)], map_hash="other")
    assert not o.cleared and o.seconds == 60 and o.stale == 2
    assert PT.observed(99, []) is None


def test_the_lapse_is_fitted_to_the_deaths_seen():
    els = [Composed(f"e{i}", 2.0, [Press(13), Press(25)], [1.0, 0.0]) for i in range(30)]
    profile = {"sigma": 0.6, "pace": 1.2, "lapse": 0.08}
    true = {**profile, "lapse": 0.03}
    seen = round(4 * PT.predicted(els, [15], true, False)[1])  # four playtests of a player with lapse 0.03
    each = [seen - 3 * (seen // 4)] + [seen // 4] * 3
    fit = PT.fit_lapse([(els, [15], False, d) for d in each], profile)
    assert abs(fit["lapse"] - 0.03) <= 0.005
    assert fit["lapse_range"][0] <= 0.03 <= fit["lapse_range"][1]
    assert fit["expected_now"] > seen  # the profile's own lapse expects more deaths


def test_the_prediction_follows_the_manual_checkpoint():
    els = [Composed(f"e{i}", 2.0, [Press(4)], [1.0]) for i in range(10)]
    with_p = PT.predicted(els, [], W.PROFILES["expert"], True)
    without = PT.predicted(els, [], W.PROFILES["expert"], False)
    assert with_p[0] < without[0] and with_p[1] < without[1]
