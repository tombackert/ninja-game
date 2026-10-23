"""Network HUD (F2): live netcode health while developing the online mode.

F2 cycles off -> one status line -> status line plus graphs -> off.

The status line rates what a player feels, each part colored by the
starting targets of docs/online-benchmark-brainstorm.md (section 9): ping,
packet loss in both directions, how old the shown remote world is, and
own-ninja snaps. The graphs show the last 10 seconds: RTT per snapshot, the
gaps between arriving snapshots, and the interpolation buffer (headroom
against the delay, starved frames in red) with own-ninja snaps marked.

It reads the same numbers the session log records (scripts/network/
netstats.py): the client's metric histories, the per-second sample of
MultiplayerGameState, and what the server reports about our link. The
panel is rebuilt REBUILD_EVERY frames and blitted from a cache in between;
its text is rendered straight onto the panel so the changing values do not
churn the UI text cache.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import pygame

GOOD, OK, BAD = (110, 225, 120), (240, 205, 80), (245, 95, 85)
TEXT, DIM, GRID = (235, 235, 240), (150, 150, 165), (70, 70, 85)
PANEL_BG = (12, 12, 20, 170)
RATING_COLORS = (GOOD, OK, BAD)

LINE_FONT, SMALL_FONT = 10, 8  # the game font is monospaced, 1 px per size per char
PART_GAP = 16  # px between the parts of the status line
WINDOW_S = 10.0  # seconds shown in the graphs
REBUILD_EVERY = 6  # frames between panel rebuilds (10 Hz at 60 FPS)
TICK_MS = 1000.0 / 60.0

# (good below, ok below) per rated value; above "ok" is bad
THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "ping": (80.0, 150.0),  # RTT ms
    "loss": (1.0, 3.0),  # % in the worse direction
    "view": (150.0, 250.0),  # view age p95 ms
    "snaps": (1.0, 3.0),  # own-ninja snaps in the last 10 s
}

MODES = ("off", "line", "graphs")


def rate(kind: str, value: Optional[float]) -> int:
    """0 good, 1 ok, 2 bad (unknown values count as good)."""
    if value is None:
        return 0
    good, ok = THRESHOLDS[kind]
    return 0 if value < good else 1 if value < ok else 2


class NetHUD:
    """Collects the per-frame values only it shows and draws the overlay."""

    def __init__(self) -> None:
        self.mode = 0
        # (monotonic time, headroom ticks, delay ticks), one per frame
        self._buffer: Deque[Tuple[float, float, float]] = deque(maxlen=int(WINDOW_S * 60) + 30)
        self._snaps: Deque[Tuple[float, float]] = deque(maxlen=200)  # (time, px)
        self._sample: Dict[str, Any] = {}
        self._frame = 0
        self._cache: Optional[pygame.Surface] = None

    # --- Feeding ---

    @property
    def enabled(self) -> bool:
        return self.mode > 0

    def toggle(self) -> None:
        self.mode = (self.mode + 1) % len(MODES)
        self._cache = None

    def note_frame(self, headroom: float, delay: float, now: Optional[float] = None) -> None:
        self._buffer.append((time.monotonic() if now is None else now, headroom, delay))

    def note_snap(self, px: float, now: Optional[float] = None) -> None:
        self._snaps.append((time.monotonic() if now is None else now, px))

    def note_sample(self, sample: Dict[str, Any]) -> None:
        """The per-second sample MultiplayerGameState writes to the session log."""
        self._sample = sample

    # --- Status line ---

    def status(self, rtt_ms: Optional[float], now: Optional[float] = None) -> List[Tuple[str, int]]:
        """The parts of the status line, each with its rating."""
        now = time.monotonic() if now is None else now
        s = self._sample
        loss_in = s.get("link_loss_pct")
        loss_out = (s.get("server_view") or {}).get("c2s_loss_pct")
        view = s.get("view_age_ms_p95")
        snaps = sum(1 for t, _ in self._snaps if t >= now - WINDOW_S)
        losses = [v for v in (loss_in, loss_out) if v is not None]
        return [
            ("Ping " + (f"{rtt_ms:.0f} ms" if rtt_ms else "--"), rate("ping", rtt_ms)),
            (
                "Loss " + "/".join(_num(v, 1) for v in (loss_in, loss_out)) + " %",
                rate("loss", max(losses) if losses else None),
            ),
            ("View " + (f"{view:.0f} ms" if view is not None else "--"), rate("view", view)),
            (f"Snaps {snaps}", rate("snaps", snaps)),
        ]

    # --- Drawing ---

    def render(self, surface: pygame.Surface, client: Any) -> None:
        """Draw the overlay at the top right (no-op while off)."""
        if not self.mode:
            return
        self._frame += 1
        if self._cache is None or self._frame % REBUILD_EVERY == 0:
            self._cache = self._build(client)
        x = surface.get_width() - self._cache.get_width() - 10
        y = max(40, surface.get_height() // 10)  # below the timer
        surface.blit(self._cache, (x, y))

    def _build(self, client: Any) -> pygame.Surface:
        from scripts.ui import UI

        font = UI.get_font(LINE_FONT)
        small = UI.get_font(SMALL_FONT)
        now = time.monotonic()
        rtt_ms = client.rtt * 1000.0 if client is not None and client.rtt else None
        parts = self.status(rtt_ms, now)
        line_w = sum(font.size(text)[0] for text, _ in parts) + PART_GAP * (len(parts) - 1)
        rows: List[Tuple[str, Any]] = []
        if self.mode == 2:
            rows = self._graph_rows(client, now)
        text_w = max((small.size(r)[0] for kind, r in rows if kind == "text"), default=0)
        width = max(line_w, text_w, 360 if rows else 0) + 16
        y = 6 + font.get_linesize() + (6 if rows else 0)
        panel = pygame.Surface((width, y + sum(_row_height(kind) for kind, _ in rows) + 5), pygame.SRCALPHA)
        panel.fill(PANEL_BG)
        x = 8
        for text, rating in parts:
            _text(panel, font, text, x, 6, RATING_COLORS[rating])
            x += font.size(text)[0] + PART_GAP
        inner = pygame.Rect(8, 0, width - 16, 0)
        for kind, payload in rows:
            if kind == "label":
                left, right = payload
                _text(panel, small, left, inner.x, y, DIM)
                if right:
                    _text(panel, small, right, inner.right - small.size(right)[0], y, DIM)
            elif kind == "text":
                _text(panel, small, payload, inner.x, y, TEXT)
            else:
                payload(panel, pygame.Rect(inner.x, y, inner.w, _row_height(kind) - 4), now)
            y += _row_height(kind)
        return panel

    def _graph_rows(self, client: Any, now: float) -> List[Tuple[str, Any]]:
        s = self._sample
        rows: List[Tuple[str, Any]] = []
        t0 = now - WINDOW_S

        rtt = [(t, v) for t, v in _history(client, "rtt_ms") if t >= t0]
        rtt_top = _nice_max([v for _, v in rtt], floor=40.0)
        p95 = s.get("rtt_ms_p95")
        jitter = s.get("link_jitter_ms")
        rows.append(
            (
                "label",
                (
                    "RTT (ms)",
                    "  ".join(
                        part
                        for part in (
                            f"jitter {jitter:.0f}" if jitter is not None else "",
                            f"p95 {p95:.0f}" if p95 is not None else "",
                        )
                        if part
                    ),
                ),
            )
        )
        rows.append(("graph", lambda surf, r, n: _plot_line(surf, r, rtt, t0, n, rtt_top, GOOD, f"{rtt_top:.0f}")))

        gaps = [(t, v) for t, v in _history(client, "snap_gap_ms") if t >= t0]
        gap_top = _nice_max([v for _, v in gaps], floor=100.0)
        rows.append(("label", ("Snapshot gaps (ms)", f"max {max((v for _, v in gaps), default=0):.0f}")))
        rows.append(("graph", lambda surf, r, n: _plot_bars(surf, r, gaps, t0, n, gap_top, _gap_color)))

        buf = [(t, h, d) for t, h, d in self._buffer if t >= t0]
        snaps = [(t, px) for t, px in self._snaps if t >= t0]
        delay = buf[-1][2] if buf else None
        buf_top = _nice_max([max(h, d) for _, h, d in buf], floor=8.0)
        rows.append(
            (
                "label",
                (
                    "Buffer headroom / delay (ticks)",
                    f"delay {delay:.0f} = {delay * TICK_MS:.0f} ms" if delay is not None else "",
                ),
            )
        )
        rows.append(("graph", lambda surf, r, n: _plot_buffer(surf, r, buf, snaps, t0, n, buf_top)))

        view = s.get("server_view") or {}
        if view:
            rows.append(
                (
                    "text",
                    "Server gets: loss {} %, jitter {} ms, backlog {}".format(
                        _num(view.get("c2s_loss_pct"), 1),
                        _num(view.get("c2s_jitter_ms"), 0),
                        view.get("backlog", "-"),
                    ),
                )
            )
            rows.append(
                (
                    "text",
                    "Ticks with no step {} %, with 2+ steps {} %".format(
                        _num(view.get("no_step_pct"), 1), _num(view.get("multi_step_pct"), 1)
                    ),
                )
            )
        if "link_rx_bytes" in s:
            rows.append(
                (
                    "text",
                    "Link: in {} / out {} kbit/s, max {} B ({} > 1200)".format(
                        _num(s["link_rx_bytes"] * 8 / 1000.0, 0),
                        _num(s.get("link_tx_bytes", 0) * 8 / 1000.0, 0),
                        view.get("s2c_max_bytes", "-"),
                        view.get("s2c_oversize", "-"),
                    ),
                )
            )
        return rows


# --- Drawing helpers ---


def _row_height(kind: str) -> int:
    return 34 if kind == "graph" else SMALL_FONT + 3


def _num(value: Optional[float], decimals: int) -> str:
    return "-" if value is None else f"{value:.{decimals}f}"


def _history(client: Any, name: str) -> Sequence[Tuple[float, float]]:
    stats = getattr(client, "netstats", None)
    if stats is None or name not in stats.metrics:
        return []
    return stats.metrics[name].history()


_NICE = (10, 20, 25, 40, 50, 80, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000, 5000)


def _nice_max(values: List[float], floor: float) -> float:
    """A round upper bound for a graph's y axis, at least ``floor``."""
    top = max(floor, max(values, default=0.0) * 1.15)
    return float(next((n for n in _NICE if top <= n), top))


def _gap_color(gap_ms: float) -> Tuple[int, int, int]:
    return GOOD if gap_ms <= 50 else OK if gap_ms < 100 else BAD


def _x(rect: pygame.Rect, t: float, t0: float, t1: float) -> int:
    return rect.x + int((t - t0) / (t1 - t0) * (rect.w - 1))


def _y(rect: pygame.Rect, v: float, top: float) -> int:
    return rect.bottom - 1 - int(min(max(v, 0.0), top) / top * (rect.h - 1))


def _frame(surf: pygame.Surface, rect: pygame.Rect, label: str = "") -> None:
    pygame.draw.rect(surf, GRID, rect, 1)
    pygame.draw.line(surf, GRID, (rect.x, rect.centery), (rect.right - 1, rect.centery))
    if label:
        from scripts.ui import UI

        _text(surf, UI.get_font(SMALL_FONT), label, rect.x + 2, rect.y + 2, DIM)


def _plot_line(surf, rect, points, t0, t1, top, color, label="") -> None:
    _frame(surf, rect, label)
    pts = [(_x(rect, t, t0, t1), _y(rect, v, top)) for t, v in points]
    if len(pts) >= 2:
        pygame.draw.lines(surf, color, False, pts)


def _plot_bars(surf, rect, points, t0, t1, top, color_fn) -> None:
    _frame(surf, rect, f"{top:.0f}")
    for t, v in points:
        x = _x(rect, t, t0, t1)
        pygame.draw.line(surf, color_fn(v), (x, rect.bottom - 1), (x, _y(rect, v, top)))


def _plot_buffer(surf, rect, buf, snaps, t0, t1, top) -> None:
    _frame(surf, rect, f"{top:.0f}")
    delay = [(_x(rect, t, t0, t1), _y(rect, d, top)) for t, _, d in buf]
    if len(delay) >= 2:
        pygame.draw.lines(surf, DIM, False, delay)
    prev = None
    for t, h, _ in buf:
        pt = (_x(rect, t, t0, t1), _y(rect, h, top))
        if prev is not None:
            pygame.draw.line(surf, BAD if h < 0.5 else GOOD, prev, pt)
        prev = pt
    for t, _px in snaps:
        x = _x(rect, t, t0, t1)
        pygame.draw.line(surf, BAD, (x, rect.y), (x, rect.y + 6), 2)


def _text(surf: pygame.Surface, font: pygame.font.Font, text: str, x: int, y: int, color) -> None:
    """Text with a 1 px shadow, rendered directly (not through the UI text cache)."""
    surf.blit(font.render(text, False, (0, 0, 0)), (x + 1, y + 1))
    surf.blit(font.render(text, False, color), (x, y))


__all__ = ["NetHUD", "rate", "THRESHOLDS", "MODES"]
