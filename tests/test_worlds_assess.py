"""tools.worlds.assess: sections, the play-time estimate and profiles of unsaved levels."""

import pytest

from tools.worlds.assess import PROFILES, profile_level, section_name, time_to_beat
from tools.worlds.builder import Level


@pytest.mark.parametrize(
    "label, section",
    [
        ("bounce ledge 4", "bounce ledge"),
        ("maze 3,2", "maze"),
        ("temple step 3 (far)", "temple step (far)"),
        ("flag", "flag"),
    ],
)
def test_a_section_is_its_waypoint_labels_without_numbers(label, section):
    assert section_name(label) == section


def test_time_to_beat_without_deaths_is_the_sum_of_the_pieces():
    assert time_to_beat([2.0, 3.0, 5.0], [1.0, 1.0, 1.0]) == pytest.approx(10.0)


def test_a_death_starts_the_stretch_over():
    # Through the first piece for sure, then half the runs die in the second:
    # a run costs 1 + 1, and it takes two runs on average
    assert time_to_beat([1.0, 1.0], [1.0, 0.5]) == pytest.approx(4.0)


def _level(pillars=(), far: int = 0) -> Level:
    """Ground, 1-wide pillars over the void (x, top), ground again `far` tiles on."""
    lv = Level(990, "sand")
    lv.rect(0, 20, 9, 60)
    lv.spawn(2, 19)
    lv.wp(7, 19, 9, 19, ground=True, label="edge")
    x = 9
    for x, top in pillars:
        lv.rect(x, top, x, 60)
        lv.wp(x, top - 1, ground=True, label=f"pillar {x}")
    x += far + 1
    lv.rect(x, 20, x + 20, 60)
    lv.wp(x, 19, x + 2, 19, ground=True, label="far side")
    lv.wp(x + 15, 19, ground=True, label="end")
    return lv


def test_a_profile_of_an_unsaved_level_says_where_it_is_hard():
    flat = profile_level(_level())
    pillars = profile_level(_level([(14, 20), (19, 19), (24, 21), (29, 19), (34, 20)], far=3))
    assert set(flat["playtime"]) == set(PROFILES)
    assert flat["playtime"]["average"]["deaths"] == 0
    assert pillars["playtime"]["average"]["deaths"] > 0
    assert pillars["playtime"]["average"]["minutes"] > flat["playtime"]["average"]["minutes"]
    assert pillars["playtime"]["average"]["death_hotspots"][0][0] == "pillar"
    assert dict(pillars["sections"])["pillar"] > 0


def test_a_level_whose_route_cannot_be_played_has_no_profile(monkeypatch):
    from tools.worlds import route

    monkeypatch.setattr(route, "plan_route", lambda *a, **k: route.RouteResult(False, failed_at=1))
    assert profile_level(_level()) is None


def _long_run_up(checkpoint: bool) -> Level:
    """A long walk, then pillars over the void: a death there costs the walk, unless a banner stands before them."""
    lv = Level(993, "sand")
    lv.rect(0, 20, 49, 60)
    lv.spawn(2, 19)
    if checkpoint:
        lv.checkpoint(46, 19)
    lv.wp(47, 19, 49, 19, ground=True, label="edge")
    for x, top in [(54, 20), (59, 19), (64, 21), (69, 19)]:
        lv.rect(x, top, x, 60)
        lv.wp(x, top - 1, ground=True, label="pillar")
    lv.rect(73, 20, 90, 60)
    lv.wp(73, 19, 75, 19, ground=True, label="far side")
    return lv


def test_a_banner_before_the_hard_part_shortens_the_time_to_clear():
    without, with_banner = profile_level(_long_run_up(False)), profile_level(_long_run_up(True))
    a, b = without["playtime"]["average"], with_banner["playtime"]["average"]
    assert (a["checkpoints"], b["checkpoints"]) == (0, 1)
    assert a["deaths_without_p"] > 0
    assert b["minutes_without_p"] < a["minutes_without_p"]
