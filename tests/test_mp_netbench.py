"""Tests for the netbench log reduction (tools/mp_netbench.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import mp_netbench  # noqa: E402


def _client_sample(t, **fields):
    sample = {
        "type": "sample",
        "t": t,
        "fps": 60.0,
        "link_lost": 0,
        "link_rx_packets": 30,
        "link_duplicates": 0,
        "link_late": 0,
    }
    sample.update(fields)
    return sample


def _peer(name, ticks=60, starved=0, burst=0, lost=0, rx=60, tx_bytes=1000, tx_max=900):
    return {
        "name": name,
        "ticks": {"ticks": ticks, "starved": starved, "burst": burst},
        "link": {
            "lost": lost,
            "rx_packets": rx,
            "duplicates": 0,
            "late": 0,
            "tx_bytes": tx_bytes,
            "tx_max_bytes": tx_max,
        },
    }


class TestReduceRun(unittest.TestCase):
    def setUp(self):
        # 10 friend samples at t = 100..109; the first WARMUP_S seconds are not scored
        self.friend = [{"type": "session", "t": 99.5}] + [
            _client_sample(100.0 + i, corrections=2, rtt_ms_p50=40.0 + i, view_age_ms_p95=150.0) for i in range(10)
        ]
        self.host = [_client_sample(100.0 + i, corrections=0) for i in range(12)]
        self.server = [
            {
                "type": "sample",
                "t": 100.0 + i,
                "tick_ms_p95": 0.5,
                "peers": {"1": _peer("Host"), "2": _peer("Friend", starved=6, burst=3, lost=1, tx_max=2500)},
            }
            for i in range(12)
        ]

    def test_scores_only_after_warmup(self):
        result = mp_netbench.reduce_run(self.server, self.host, self.friend)
        scored = 10 - int(mp_netbench.WARMUP_S)
        self.assertEqual(result["friend.seconds"], scored)
        # 2 corrections every second -> 120 per minute
        self.assertAlmostEqual(result["friend.corrections_per_min"], 120.0)
        self.assertEqual(result["host.corrections_per_min"], 0.0)
        self.assertEqual(result["friend.rtt_p50_ms"], 40.0 + 3 + (scored - 1) / 2)

    def test_server_side_is_split_by_player(self):
        result = mp_netbench.reduce_run(self.server, self.host, self.friend)
        self.assertAlmostEqual(result["server.friend_starved_pct"], 10.0)
        self.assertAlmostEqual(result["server.friend_burst_pct"], 5.0)
        self.assertEqual(result["server.host_starved_pct"], 0.0)
        # 1 lost of 61 expected (60 received + 1 lost) per second
        self.assertAlmostEqual(result["server.friend_c2s_loss_pct"], 100.0 / 61.0)
        self.assertEqual(result["server.max_packet_bytes"], 2500)
        self.assertAlmostEqual(result["server.friend_s2c_kbps"], 8.0)

    def test_loss_counts_expected_packets(self):
        for s in self.friend[1:]:
            s["link_lost"] = 3
            s["link_rx_packets"] = 27
        result = mp_netbench.reduce_run(self.server, self.host, self.friend)
        self.assertAlmostEqual(result["friend.s2c_loss_pct"], 10.0)

    def test_missing_friend_log_is_an_error(self):
        self.assertIn("error", mp_netbench.reduce_run(self.server, self.host, []))

    def test_median_of_runs_skips_missing_values(self):
        runs = [{"a": 1.0, "b": 5.0}, {"a": 3.0}, {"a": 2.0, "b": None}, {"error": "x"}]
        self.assertEqual(mp_netbench.median_of_runs(runs), {"a": 2.0, "b": 5.0})


if __name__ == "__main__":
    unittest.main()
