"""Network statistics core, shared by client and server.

Collects the metrics described in docs/online-benchmark-brainstorm.md:

- LinkStats: packet-level health of one peer link (loss, duplicates,
  reordering, RFC 3550 jitter, bytes, packet sizes). Fed by UDPTransport.
- Metric: one measured quantity (RTT, view age, ...) with percentiles over
  the current one-second report window and a ten-second history.
- NetStats: metrics, counters and events of one side, turned into one flat
  sample per second.
- SessionLog: the JSONL file every client and server writes per session
  (a session line, one sample per second, events, a summary at the end).

Times are wall-clock seconds (time.time()) wherever they are compared with
packet arrival times, because kernel receive timestamps use that clock.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

# UDP payloads above this risk IP fragmentation on internet paths
# (Ethernet 1500, PPPoE 1492, Tailscale 1280, minus IP/UDP headers)
SAFE_PACKET_BYTES = 1200

# Sequence window for loss/reorder detection (same span as the ack bitfield).
# A sequence counts as lost once it falls this many packets behind the newest.
LINK_WINDOW = 32
_LINK_MASK = (1 << LINK_WINDOW) - 1
# A forward jump this large means the peer restarted its sequence; start over
MAX_SEQ_JUMP = 10_000

# How long Metric keeps values for recent() queries (HUD graphs)
HISTORY_S = 10.0

# Where session logs go by default, and how many per role are kept
NETLOG_DIR = os.path.join("data", "netlogs")
NETLOG_KEEP = 20


def percentile(sorted_values: List[float], p: float) -> float:
    """Nearest-rank percentile of an already sorted, non-empty list."""
    return sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * p / 100.0))]


class LinkStats:
    """Packet-level health of one peer link, both directions.

    Inbound loss is counted by the receiver from sequence gaps. A sequence
    only counts as lost once it falls LINK_WINDOW packets behind the newest
    without having arrived, so reordered packets are not miscounted. This
    needs per-peer sequence numbers on the sender side.

    Counters accumulate per report window (take() returns and resets them)
    and in ``totals`` for the whole session.
    """

    _COUNTERS = (
        "rx_packets",
        "rx_bytes",
        "lost",
        "duplicates",
        "reordered",
        "late",
        "tx_packets",
        "tx_bytes",
        "tx_oversize",
    )

    def __init__(self) -> None:
        self._highest: Optional[int] = None
        self._seen = 0  # bit i set: sequence (highest - i) arrived
        self._span = 0  # number of valid positions in _seen
        self.jitter = 0.0  # RFC 3550 interarrival jitter estimate, seconds
        self._last_transit: Optional[float] = None
        self.last_arrival: Optional[float] = None
        self._window: Dict[str, int] = dict.fromkeys(self._COUNTERS, 0)
        self._tx_max = 0
        self.totals: Dict[str, int] = dict.fromkeys(self._COUNTERS, 0)

    # --- Inbound ---

    def on_receive(self, sequence: int, size: int, arrival: float, sent: float = 0.0) -> None:
        """Record one received packet.

        Args:
            sequence: The sender's per-peer packet sequence number
            size: Datagram size in bytes
            arrival: Arrival time (wall clock, kernel timestamp if available)
            sent: The sender's wall-clock send time from the header (0 = unknown)
        """
        w = self._window
        w["rx_packets"] += 1
        w["rx_bytes"] += size
        self.last_arrival = arrival

        if self._highest is None or sequence - self._highest > MAX_SEQ_JUMP:
            # Streams start at 0, so earlier sequences missing at the start
            # are real losses; a stream joined late (or restarted) is not.
            self._highest = sequence
            self._seen = 1
            self._span = sequence + 1 if 0 <= sequence < LINK_WINDOW else 1
        elif sequence > self._highest:
            shift = sequence - self._highest
            seen = (self._seen << shift) | 1
            total = self._span + shift
            kept = min(LINK_WINDOW, total)
            w["lost"] += (total - kept) - bin(seen >> LINK_WINDOW).count("1")
            self._seen = seen & _LINK_MASK
            self._span = kept
            self._highest = sequence
        else:
            pos = self._highest - sequence
            if pos >= LINK_WINDOW:
                w["late"] += 1  # already counted as lost
                return
            if (self._seen >> pos) & 1:
                w["duplicates"] += 1
                return
            self._seen |= 1 << pos
            self._span = max(self._span, pos + 1)
            w["reordered"] += 1

        if sent > 0:
            # RFC 3550: J += (|D| - J) / 16, D = difference of transit times.
            # The clock offset between the machines cancels out in D.
            transit = arrival - sent
            if self._last_transit is not None:
                self.jitter += (abs(transit - self._last_transit) - self.jitter) / 16.0
            self._last_transit = transit

    # --- Outbound ---

    def on_send(self, size: int) -> None:
        """Record one sent datagram of ``size`` bytes."""
        w = self._window
        w["tx_packets"] += 1
        w["tx_bytes"] += size
        if size > SAFE_PACKET_BYTES:
            w["tx_oversize"] += 1
        self._tx_max = max(self._tx_max, size)

    # --- Reporting ---

    def take(self) -> Dict[str, Any]:
        """Return this window's counters (plus loss %, jitter) and reset them."""
        w = self._window
        expected = w["rx_packets"] - w["duplicates"] - w["late"] + w["lost"]
        out: Dict[str, Any] = dict(w)
        out["loss_pct"] = round(100.0 * w["lost"] / expected, 2) if expected > 0 else 0.0
        out["jitter_ms"] = round(self.jitter * 1000.0, 2)
        out["tx_max_bytes"] = self._tx_max
        for key, value in w.items():
            self.totals[key] += value
        self._window = dict.fromkeys(self._COUNTERS, 0)
        self._tx_max = 0
        return out


class Metric:
    """One measured quantity: the current report window plus a short history."""

    def __init__(self, history_s: float = HISTORY_S) -> None:
        self._window: List[float] = []
        self._history: Deque[Tuple[float, float]] = deque()
        self._history_s = history_s
        self.last: Optional[float] = None

    def add(self, value: float, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        self._window.append(value)
        self._history.append((now, value))
        self.last = value
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self._history_s
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def take(self) -> Optional[Dict[str, float]]:
        """Percentiles of the current window, then start a new one (None if empty)."""
        if not self._window:
            return None
        values = sorted(self._window)
        self._window = []
        return {
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
            "max": values[-1],
            "n": len(values),
        }

    def recent(self, p: float, seconds: Optional[float] = None, now: Optional[float] = None) -> Optional[float]:
        """Percentile over the last ``seconds`` of history (None if no values)."""
        now = time.monotonic() if now is None else now
        self._prune(now)
        cutoff = now - (self._history_s if seconds is None else seconds)
        values = sorted(v for t, v in self._history if t >= cutoff)
        return percentile(values, p) if values else None

    def history(self) -> List[Tuple[float, float]]:
        """(monotonic time, value) pairs of the last HISTORY_S seconds."""
        return list(self._history)


class NetStats:
    """Metrics, counters and events of one side (client or server).

    ``take_sample()`` flattens everything measured since the previous call
    into one dict: ``<metric>_p50/_p95/_p99/_max`` for metrics with values
    in the window and one key per counter (0 when nothing happened).
    """

    def __init__(self) -> None:
        self.metrics: Dict[str, Metric] = {}
        self.counters: Dict[str, int] = {}
        self.totals: Dict[str, int] = {}
        self._events: List[Dict[str, Any]] = []

    def metric(self, name: str) -> Metric:
        m = self.metrics.get(name)
        if m is None:
            m = self.metrics[name] = Metric()
        return m

    def add(self, name: str, value: float, now: Optional[float] = None) -> None:
        self.metric(name).add(value, now)

    def count(self, name: str, n: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + n
        self.totals[name] = self.totals.get(name, 0) + n

    def event(self, kind: str, **fields: Any) -> None:
        """Record a discrete event (stall, hitch, join, ...) with a wall-clock time."""
        self._events.append({"type": "event", "event": kind, "t": round(time.time(), 3), **fields})

    def drain_events(self) -> List[Dict[str, Any]]:
        events = self._events
        self._events = []
        return events

    def take_sample(self) -> Dict[str, Any]:
        sample: Dict[str, Any] = {}
        for name, m in self.metrics.items():
            stats = m.take()
            if stats is not None:
                for key in ("p50", "p95", "p99", "max"):
                    sample[f"{name}_{key}"] = round(stats[key], 2)
        sample.update(self.counters)
        self.counters = dict.fromkeys(self.counters, 0)
        return sample


class SessionLog:
    """One JSONL file per session: a session line, samples, events, a summary."""

    def __init__(self, path: str) -> None:
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._fh: Any = open(path, "a")

    @classmethod
    def create(
        cls,
        role: str,
        label: str = "",
        directory: Optional[str] = None,
        keep: int = NETLOG_KEEP,
    ) -> Optional[SessionLog]:
        """Open a new log ``<date>-<time>-<role>[-<label>]-<pid>.jsonl`` in the log directory.

        Prunes the directory to the newest ``keep`` logs of that role.
        Returns None if the directory cannot be written.
        """
        directory = NETLOG_DIR if directory is None else directory
        parts = [time.strftime("%Y%m%d-%H%M%S"), role]
        if label:
            parts.append(re.sub(r"[^A-Za-z0-9]+", "_", label)[:32])
        parts.append(str(os.getpid()))
        base = os.path.join(directory, "-".join(parts))
        path, n = base + ".jsonl", 1
        while os.path.exists(path):  # a second session within the same second
            n += 1
            path = f"{base}-{n}.jsonl"
        try:
            log = cls(path)
        except OSError:
            return None
        _prune_logs(directory, role, keep)
        return log

    def write(self, record: Dict[str, Any]) -> None:
        if self._fh is None:
            return
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def write_all(self, records: List[Dict[str, Any]]) -> None:
        for record in records:
            self.write(record)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _prune_logs(directory: str, role: str, keep: int) -> None:
    """Delete all but the newest ``keep`` session logs of ``role``."""
    try:
        names = sorted(n for n in os.listdir(directory) if n.endswith(".jsonl") and n.split("-")[2:3] == [role])
    except OSError:
        return
    for name in names[:-keep] if keep > 0 else names:
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            pass


__all__ = [
    "LinkStats",
    "Metric",
    "NetStats",
    "SessionLog",
    "SAFE_PACKET_BYTES",
    "LINK_WINDOW",
    "NETLOG_DIR",
    "percentile",
]
