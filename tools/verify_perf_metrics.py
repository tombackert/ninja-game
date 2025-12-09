import unittest
import pygame
import time
from scripts.ui import UI
from scripts.perf_hud import PerformanceHUD


class TestPerformanceMetrics(unittest.TestCase):
    def setUp(self):
        # Initialize pygame font module (required for UI.get_font)
        pygame.font.init()
        # Reset UI caches before each test
        UI.clear_image_cache()
        # Ensure we have a clean HUD state
        self.hud = PerformanceHUD(enabled=True)

    def tearDown(self):
        pygame.font.quit()

    def test_cache_hit_miss_logic(self):
        """Verify that cache hits, misses, and evictions are tracked correctly."""
        # 1. First load: Should be a MISS
        # We'll use a dummy path since we are testing the caching logic wrapper
        # mocking pygame.image.load is harder here without heavy patching,
        # so let's test the Text Cache which doesn't require disk IO.

        font = pygame.font.Font(None, 20)

        # Initial state
        stats = UI.get_text_cache_stats()
        self.assertEqual(stats['hits'], 0)
        self.assertEqual(stats['misses'], 0)

        # 2. First render: MISS
        UI.draw_text_with_outline(pygame.Surface((1, 1)), font, "Test", 0, 0)
        stats = UI.get_text_cache_stats()
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['hits'], 0)

        # 3. Second render (same params): HIT
        UI.draw_text_with_outline(pygame.Surface((1, 1)), font, "Test", 0, 0)
        stats = UI.get_text_cache_stats()
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['hits'], 1)

        # 4. Verify Hit Ratio calculation
        total = stats['hits'] + stats['misses']
        ratio = (stats['hits'] / total) * 100
        self.assertEqual(ratio, 50.0)

    def test_cache_eviction(self):
        """Verify that the cache evicts items when capacity is reached."""
        # Force a small capacity for testing
        UI._text_cache_capacity = 2
        font = pygame.font.Font(None, 20)

        # Fill cache
        UI.draw_text_with_outline(pygame.Surface((1, 1)), font, "A", 0, 0)  # Miss 1
        UI.draw_text_with_outline(pygame.Surface((1, 1)), font, "B", 0, 0)  # Miss 2

        stats = UI.get_text_cache_stats()
        self.assertEqual(stats['size'], 2)
        self.assertEqual(stats['evictions'], 0)

        # Push over capacity
        UI.draw_text_with_outline(pygame.Surface((1, 1)), font, "C", 0, 0)  # Miss 3, Evict 1

        stats = UI.get_text_cache_stats()
        self.assertEqual(stats['size'], 2)  # Should stay at max capacity
        self.assertEqual(stats['evictions'], 1)

    def test_timing_metrics(self):
        """Verify work_ms and full_ms calculations."""

        self.hud.begin_frame()

        # self.hud._t_work_start is captured internally

        # Simulate work

        time.sleep(0.01)  # 10ms

        self.hud.end_work_segment()
        # last_sample is now _staging_sample
        sample = self.hud.last_sample

        # Verify work_ms captured ~10ms
        self.assertTrue(sample.work_ms >= 10.0)
        # full_ms should be None yet
        self.assertIsNone(sample.full_ms)

        # Simulate wait/vsync
        time.sleep(0.01)  # another 10ms

        self.hud.end_frame()

        # Verify full_ms captured ~20ms
        self.assertTrue(self.hud.last_full_frame_ms >= 20.0)

        # Verify the sample was updated
        self.assertTrue(self.hud.last_sample.full_ms >= 20.0)

    def test_system_stats_integration(self):
        """Verify system stats are collected (if available)."""
        # Initialize AssetManager to test asset count
        from scripts.asset_manager import AssetManager

        AssetManager.get()

        self.hud.begin_frame()
        self.hud.end_work_segment()
        # This calls the method we added to collect memory/assets
        self.hud.end_frame()
        sample = self.hud.last_sample

        # Check fields exist
        self.assertTrue(hasattr(sample, 'memory_rss'))
        self.assertTrue(hasattr(sample, 'asset_count'))

        # On Darwin (macOS) where this test is running, memory_rss should be populated
        import sys

        if sys.platform == "darwin":
            self.assertIsNotNone(sample.memory_rss)
            self.assertGreater(sample.memory_rss, 0)

        # Asset count should be integer (0 or more)
        self.assertIsNotNone(sample.asset_count)
        self.assertGreaterEqual(sample.asset_count, 0)


if __name__ == '__main__':
    unittest.main()
