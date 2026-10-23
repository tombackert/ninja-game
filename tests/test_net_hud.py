"""Tests for the network HUD (scripts/net_hud.py, F2 in multiplayer)."""

import time
import unittest

import pygame

from scripts.net_hud import REBUILD_EVERY, NetHUD, rate
from scripts.network.netstats import NetStats


def setUpModule():
    pygame.init()


class _Client:
    """The parts of GameClient the HUD reads."""

    def __init__(self, rtt=0.034):
        self.rtt = rtt
        self.netstats = NetStats()
        now = time.monotonic()
        for i in range(60):
            t = now - 9.0 + i * 0.15
            self.netstats.add("rtt_ms", 30.0 + (i % 7), now=t)
            self.netstats.add("snap_gap_ms", 33.0 if i % 10 else 120.0, now=t)


def _sample(**overrides):
    sample = {
        "link_jitter_ms": 4.0,
        "link_loss_pct": 0.2,
        "view_age_ms_p95": 110.0,
        "rtt_ms_p95": 41.0,
        "link_rx_bytes": 28000,
        "link_tx_bytes": 11000,
        "server_view": {
            "c2s_loss_pct": 0.1,
            "c2s_jitter_ms": 3.0,
            "no_step_pct": 0.7,
            "multi_step_pct": 0.7,
            "backlog": 1,
            "s2c_max_bytes": 2400,
            "s2c_oversize": 1,
        },
    }
    sample.update(overrides)
    return sample


class TestRating(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(rate("ping", 40), 0)
        self.assertEqual(rate("ping", 100), 1)
        self.assertEqual(rate("ping", 200), 2)
        self.assertEqual(rate("loss", 0.5), 0)
        self.assertEqual(rate("loss", 5), 2)
        self.assertEqual(rate("view", None), 0)

    def test_status_parts_are_rated_one_by_one(self):
        hud = NetHUD()
        hud.note_sample(_sample())
        self.assertEqual(
            hud.status(34.0),
            [("Ping 34 ms", 0), ("Loss 0.2/0.1 %", 0), ("View 110 ms", 0), ("Snaps 0", 0)],
        )
        hud.note_sample(_sample(view_age_ms_p95=300.0, link_loss_pct=1.5))
        self.assertEqual([r for _, r in hud.status(34.0)], [0, 1, 2, 0])

    def test_snaps_count_the_last_ten_seconds(self):
        hud = NetHUD()
        now = time.monotonic()
        hud.note_snap(4.0, now=now - 20.0)
        hud.note_snap(4.0, now=now - 2.0)
        hud.note_snap(9.0, now=now - 1.0)
        self.assertEqual(hud.status(34.0, now=now)[-1], ("Snaps 2", 1))

    def test_status_before_any_sample(self):
        self.assertEqual(
            NetHUD().status(None),
            [("Ping --", 0), ("Loss -/- %", 0), ("View --", 0), ("Snaps 0", 0)],
        )


class TestRender(unittest.TestCase):
    def setUp(self):
        self.screen = pygame.Surface((1280, 720))
        self.client = _Client()
        self.hud = NetHUD()
        self.hud.note_sample(_sample())
        now = time.monotonic()
        for i in range(300):
            self.hud.note_frame(5.0 - (i % 2), 6.0, now=now - 5.0 + i / 60.0)
        self.hud.note_snap(3.0, now=now - 1.0)

    def _black_pixels(self):
        right = self.screen.subsurface(pygame.Rect(640, 0, 640, 720))
        return pygame.mask.from_threshold(right, (0, 0, 0), (1, 1, 1, 255)).count()

    def test_toggle_cycles_off_line_graphs(self):
        modes = []
        for _ in range(4):
            self.hud.toggle()
            modes.append(self.hud.mode)
        self.assertEqual(modes, [1, 2, 0, 1])

    def test_off_draws_nothing(self):
        self.hud.render(self.screen, self.client)
        self.assertEqual(self._black_pixels(), 640 * 720)

    def test_graphs_panel_is_taller_than_the_line(self):
        self.hud.toggle()
        self.hud.render(self.screen, self.client)
        line_h = self.hud._cache.get_height()
        self.hud.toggle()
        self.hud.render(self.screen, self.client)
        self.assertGreater(self.hud._cache.get_height(), line_h * 3)
        self.assertLessEqual(self.hud._cache.get_width(), 640)

    def test_panel_is_rebuilt_only_every_few_frames(self):
        self.hud.toggle()
        self.hud.toggle()
        self.hud.render(self.screen, self.client)
        first = self.hud._cache
        built = [first]
        for _ in range(REBUILD_EVERY):
            self.hud.render(self.screen, self.client)
            if self.hud._cache is not built[-1]:
                built.append(self.hud._cache)
        self.assertEqual(len(built), 2)

    def test_render_without_history(self):
        hud = NetHUD()
        hud.toggle()
        hud.toggle()
        client = _Client(rtt=0.0)
        client.netstats = NetStats()
        hud.render(self.screen, client)
        self.assertIsNotNone(hud._cache)


if __name__ == "__main__":
    unittest.main()
