"""Tests for the network statistics core (scripts/network/netstats.py).

Covers the packet-level link statistics (loss, reordering, duplicates,
jitter), metrics and samples, the session log, and the way the metrics
travel through the transport, server and client.
"""

import json
import os
import time
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List

from scripts.network import netstats
from scripts.network.game_client import GameClient
from scripts.network.game_server import GameServer
from scripts.network.messages import Message
from scripts.network.netstats import LINK_WINDOW, LinkStats, Metric, NetStats, SessionLog
from scripts.network.udp_transport import UDPTransport


def _receive(link: LinkStats, sequences, transit: float = 0.01) -> None:
    for i, seq in enumerate(sequences):
        link.on_receive(seq, 100, arrival=1000.0 + i * 0.016 + transit, sent=1000.0 + i * 0.016)


class TestLinkStatsLoss(unittest.TestCase):
    def test_in_order_stream_has_no_loss(self):
        link = LinkStats()
        _receive(link, range(100))
        w = link.take()
        self.assertEqual(w["rx_packets"], 100)
        self.assertEqual(w["lost"], 0)
        self.assertEqual(w["loss_pct"], 0.0)

    def test_gap_counts_as_lost_once_out_of_window(self):
        link = LinkStats()
        _receive(link, [s for s in range(12 + LINK_WINDOW) if s not in (10, 11)])
        self.assertEqual(link.take()["lost"], 2)

    def test_gap_not_counted_while_it_can_still_arrive(self):
        link = LinkStats()
        _receive(link, [s for s in range(20) if s != 10])
        self.assertEqual(link.take()["lost"], 0)

    def test_reordered_packet_is_not_lost(self):
        link = LinkStats()
        _receive(link, [0, 1, 3, 2] + list(range(4, 100)))
        w = link.take()
        self.assertEqual(w["reordered"], 1)
        self.assertEqual(w["lost"], 0)

    def test_duplicate_is_counted_once(self):
        link = LinkStats()
        _receive(link, [0, 1, 1] + list(range(2, 50)))
        w = link.take()
        self.assertEqual(w["duplicates"], 1)
        self.assertEqual(w["lost"], 0)

    def test_packet_older_than_window_is_late_and_stays_lost(self):
        link = LinkStats()
        _receive(link, [s for s in range(LINK_WINDOW + 10) if s != 5] + [5])
        w = link.take()
        self.assertEqual(w["late"], 1)
        self.assertEqual(w["lost"], 1)

    def test_missing_start_of_stream_is_lost(self):
        link = LinkStats()
        _receive(link, range(3, 3 + LINK_WINDOW + 5))
        self.assertEqual(link.take()["lost"], 3)

    def test_stream_joined_late_is_not_lost(self):
        link = LinkStats()
        _receive(link, range(5000, 5100))
        self.assertEqual(link.take()["lost"], 0)

    def test_big_forward_jump_counts_skipped_packets(self):
        link = LinkStats()
        _receive(link, list(range(10)) + list(range(110, 110 + LINK_WINDOW)))
        self.assertEqual(link.take()["lost"], 100)

    def test_loss_pct(self):
        link = LinkStats()
        _receive(link, [s for s in range(100 + LINK_WINDOW) if s % 10 != 0])
        w = link.take()
        # 0, 10, ..., 90 are out of the window: 10 lost of 100 expected
        self.assertEqual(w["lost"], 10)
        self.assertAlmostEqual(w["loss_pct"], 100.0 * 10 / (w["rx_packets"] + 10), places=1)


class TestLinkStatsJitterAndSend(unittest.TestCase):
    def test_constant_transit_has_no_jitter(self):
        link = LinkStats()
        _receive(link, range(50), transit=0.03)
        self.assertAlmostEqual(link.take()["jitter_ms"], 0.0, places=3)

    def test_varying_transit_shows_jitter(self):
        link = LinkStats()
        for i in range(200):
            transit = 0.010 if i % 2 else 0.020  # 10 ms difference every packet
            link.on_receive(i, 100, arrival=1000.0 + i * 0.016 + transit, sent=1000.0 + i * 0.016)
        self.assertAlmostEqual(link.take()["jitter_ms"], 10.0, delta=0.5)

    def test_clock_offset_does_not_matter(self):
        link = LinkStats()
        for i in range(50):
            link.on_receive(i, 100, arrival=5000.0 + i * 0.016, sent=1000.0 + i * 0.016)
        self.assertAlmostEqual(link.take()["jitter_ms"], 0.0, places=3)

    def test_send_sizes(self):
        link = LinkStats()
        for size in (200, 900, 1500, 5000):
            link.on_send(size)
        w = link.take()
        self.assertEqual(w["tx_packets"], 4)
        self.assertEqual(w["tx_bytes"], 7600)
        self.assertEqual(w["tx_oversize"], 2)
        self.assertEqual(w["tx_max_bytes"], 5000)

    def test_take_resets_window_and_keeps_totals(self):
        link = LinkStats()
        _receive(link, range(10))
        link.take()
        _receive(link, range(10, 15))
        self.assertEqual(link.take()["rx_packets"], 5)
        self.assertEqual(link.totals["rx_packets"], 15)


class TestMetricAndNetStats(unittest.TestCase):
    def test_metric_percentiles(self):
        m = Metric()
        for v in range(1, 101):
            m.add(float(v), now=0.0)
        stats = m.take()
        self.assertEqual(stats["p50"], 51.0)
        self.assertEqual(stats["p95"], 96.0)
        self.assertEqual(stats["max"], 100.0)
        self.assertEqual(stats["n"], 100)
        self.assertIsNone(m.take())

    def test_metric_recent_uses_history_window(self):
        m = Metric(history_s=10.0)
        m.add(100.0, now=0.0)
        m.add(10.0, now=8.0)
        self.assertEqual(m.recent(100, now=9.0), 100.0)
        self.assertEqual(m.recent(100, seconds=2.0, now=9.0), 10.0)
        self.assertEqual(m.recent(100, now=10.5), 10.0)  # the 100 aged out
        self.assertIsNone(m.recent(50, now=30.0))

    def test_sample_flattens_metrics_and_resets_counters(self):
        stats = NetStats()
        stats.add("rtt_ms", 20.0)
        stats.add("rtt_ms", 40.0)
        stats.count("stalls")
        sample = stats.take_sample()
        self.assertEqual(sample["rtt_ms_p50"], 40.0)
        self.assertEqual(sample["rtt_ms_max"], 40.0)
        self.assertEqual(sample["stalls"], 1)
        # Next window: counter present with 0, metric absent without values
        sample = stats.take_sample()
        self.assertEqual(sample["stalls"], 0)
        self.assertNotIn("rtt_ms_p50", sample)
        self.assertEqual(stats.totals["stalls"], 1)

    def test_events_are_drained(self):
        stats = NetStats()
        stats.event("net_stall", tick=5, ms=120.0)
        events = stats.drain_events()
        self.assertEqual(events[0]["event"], "net_stall")
        self.assertEqual(events[0]["type"], "event")
        self.assertEqual(events[0]["ms"], 120.0)
        self.assertEqual(stats.drain_events(), [])


class TestSessionLog(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(netstats.NETLOG_DIR, f"t{time.time_ns()}")

    def test_create_writes_jsonl(self):
        log = SessionLog.create("client", "Tom Backert", directory=self.dir)
        log.write({"type": "session"})
        log.write_all([{"type": "sample", "n": 1}, {"type": "event", "event": "x"}])
        log.close()
        name = os.path.basename(log.path)
        self.assertIn("-client-Tom_Backert-", name)
        with open(log.path) as f:
            records = [json.loads(line) for line in f]
        self.assertEqual([r["type"] for r in records], ["session", "sample", "event"])

    def test_two_sessions_in_one_second_get_two_files(self):
        a = SessionLog.create("server", directory=self.dir)
        b = SessionLog.create("server", directory=self.dir)
        self.assertNotEqual(a.path, b.path)
        a.close()
        b.close()

    def test_prune_keeps_newest_per_role(self):
        os.makedirs(self.dir)
        for name in (
            "20260101-000000-client-1.jsonl",
            "20260102-000000-client-1.jsonl",
            "20260101-000000-server-1.jsonl",
        ):
            open(os.path.join(self.dir, name), "w").close()
        SessionLog.create("client", directory=self.dir, keep=2).close()
        names = sorted(os.listdir(self.dir))
        self.assertNotIn("20260101-000000-client-1.jsonl", names)
        self.assertIn("20260102-000000-client-1.jsonl", names)
        self.assertIn("20260101-000000-server-1.jsonl", names)
        self.assertEqual(len(names), 3)


class TestTransportStats(unittest.TestCase):
    def test_sequences_are_per_peer(self):
        sender = UDPTransport(port=0)
        a = UDPTransport(port=0)
        b = UDPTransport(port=0)
        try:
            msg = Message(type="test", payload={})
            for _ in range(3):
                sender.send(msg, ("127.0.0.1", a.port))
                sender.send(msg, ("127.0.0.1", b.port))
            time.sleep(0.02)
            for receiver in (a, b):
                seqs = []
                while (result := receiver.receive()) is not None:
                    seqs.append(result[2].sequence)
                self.assertEqual(seqs, [0, 1, 2])
        finally:
            for t in (sender, a, b):
                t.close()

    def test_arrival_time_and_link_stats(self):
        sender = UDPTransport(port=0)
        receiver = UDPTransport(port=0)
        try:
            before = time.time()
            for _ in range(5):
                sender.send(Message(type="test", payload={"x": 1}), ("127.0.0.1", receiver.port))
            time.sleep(0.05)
            results = []
            while (result := receiver.receive()) is not None:
                results.append(result)
                # Kernel timestamp: the packet arrived before we read it
                self.assertLessEqual(receiver.last_arrival, time.time())
                self.assertGreaterEqual(receiver.last_arrival, before - 0.01)
                self.assertGreater(result[2].time, 0)
            self.assertEqual(len(results), 5)
            rx = receiver.link(results[0][1]).take()
            tx = sender.link(("127.0.0.1", receiver.port)).take()
            self.assertEqual(rx["rx_packets"], 5)
            self.assertEqual(rx["lost"], 0)
            self.assertEqual(tx["tx_packets"], 5)
            self.assertEqual(tx["tx_bytes"], rx["rx_bytes"])
        finally:
            sender.close()
            receiver.close()

    def test_forget_restarts_sequence(self):
        sender = UDPTransport(port=0)
        receiver = UDPTransport(port=0)
        try:
            addr = ("127.0.0.1", receiver.port)
            sender.send(Message(type="test", payload={}), addr)
            sender.forget(addr)
            self.assertNotIn(addr, sender.links)
            sender.send(Message(type="test", payload={}), addr)
            time.sleep(0.02)
            seqs = [receiver.receive()[2].sequence, receiver.receive()[2].sequence]
            self.assertEqual(seqs, [0, 0])
        finally:
            sender.close()
            receiver.close()


@dataclass
class _Player:
    id: int
    pos: List[float] = field(default_factory=lambda: [0.0, 0.0])
    velocity: List[float] = field(default_factory=lambda: [0.0, 0.0])
    flip: bool = False
    action: str = "idle"
    lives: int = 3
    air_time: int = 0
    jumps: int = 1
    wall_slide: bool = False
    dashing: int = 0
    shoot_cooldown: int = 0


@dataclass
class _Collectables:
    coins: int = 0
    ammo: int = 0


@dataclass
class _Game:
    tick: int = 0
    dead: int = 0
    transition: int = 0
    players: List[Any] = field(default_factory=list)
    enemies: List[Any] = field(default_factory=list)
    cm: _Collectables = field(default_factory=_Collectables)
    _pending_inputs: Dict[int, Any] = field(default_factory=dict)


def _connect(client: GameClient, server: GameServer) -> None:
    client.connect()
    for _ in range(5):
        time.sleep(0.02)
        server.update()
        time.sleep(0.02)
        client.update()
        if client.is_connected:
            return


class TestEndToEndMetrics(unittest.TestCase):
    """Metrics travelling through a real server and client over loopback."""

    def setUp(self):
        self.game = _Game(players=[_Player(id=1)])
        self.server = GameServer(port=0, game=self.game)
        self.client = GameClient(server_port=self.server.port, player_name="M", transport=UDPTransport(port=0))
        _connect(self.client, self.server)
        self.assertTrue(self.client.is_connected)

    def tearDown(self):
        self.server.shutdown()
        self.client.close()

    def _play(self, frames: int) -> None:
        for _ in range(frames):
            self.client.update()
            self.client.send_input_state((False, True), [])
            time.sleep(0.004)
            self.server.process_inputs()
            self.game.tick += 1
            self.server.post_tick()
            time.sleep(0.004)

    def test_snapshots_carry_input_hold_times(self):
        sent: List[Dict[str, Any]] = []
        real_send = self.server.transport.send

        def spy(message, address):
            if message.type == "snapshot":
                sent.append(message.payload)
            return real_send(message, address)

        self.server.transport.send = spy
        self._play(10)
        with_holds = [p for p in sent if p.get("holds")]
        self.assertTrue(with_holds)
        hold = with_holds[-1]["holds"][str(self.client.player_id)]
        self.assertGreaterEqual(hold, 0.0)
        self.assertLess(hold, 100.0)

    def test_client_measures_rtt_per_snapshot(self):
        self._play(30)
        rtt = self.client.netstats.metric("rtt_ms")
        stats = rtt.take()
        self.assertIsNotNone(stats)
        self.assertGreaterEqual(stats["n"], 5)
        # Loopback with queueing removed: far below one 16.7 ms tick
        self.assertLess(stats["p50"], 10.0)
        self.assertGreater(self.client.rtt, 0.0)

    def test_server_counts_inputs_per_tick(self):
        self._play(30)
        report = self.server.client_reports()[str(self.client.player_id)]
        ticks = report["ticks"]
        self.assertGreater(ticks["ticks"], 20)
        # One input per tick in this lockstep loop
        self.assertEqual(ticks["starved"], 0)
        self.assertEqual(ticks["burst"], 0)
        self.assertEqual(report["link"]["lost"], 0)

    def test_heartbeat_carries_reports_both_ways(self):
        self._play(5)
        self.server.client_reports()  # fills the compact server view
        self.client.set_report({"rtt_p95": 12.5})
        self.client._last_heartbeat_time = 0.0  # force a heartbeat
        self._play(3)
        server_client = self.server.clients.get_client_by_id(self.client.player_id)
        self.assertEqual(server_client.report, {"rtt_p95": 12.5})
        self.assertIn("starved_pct", self.client.server_view)
        self.assertIsNotNone(self.client.netstats.metric("rtt_hb_ms").take())

    def test_join_and_leave_events(self):
        self._play(5)
        client_events = [e["event"] for e in self.client.netstats.drain_events()]
        self.assertIn("connected", client_events)
        self.assertIn("joined", client_events)
        self.client.disconnect()
        time.sleep(0.02)
        self.server.update()
        server_events = [e["event"] for e in self.server.netstats.drain_events()]
        self.assertEqual(server_events, ["client_joined", "client_left"])


if __name__ == "__main__":
    unittest.main()
