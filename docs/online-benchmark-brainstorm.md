# Online Benchmark Brainstorm

**Date:** 2026-10-23
**Status:** Step 1 (`NetStats` core and session logs) implemented, see section 12; steps 2-5 open

The online mode works on loopback and over the LAN (see [multiplayer.md](multiplayer.md)). The goal now is to make it reliably playable over the internet with friends. This document collects the first step: what to measure, how to see it live, and how to benchmark it reproducibly, so every netcode change is backed by numbers the way the single-player suite ([BENCHMARKS.md](../BENCHMARKS.md)) backs frame-time changes.

---

## 1. The Question

> ich möchte jetzt den online modus vom spiel jetzt spielbar bzw produktion ready machen - dazu wäre in meiner überlegung als erstes ein umfassendes performance benchmarking system (vielleicht auch eine hud als live interface wieder), mit dem man prüfen/überwachen/entwickeln kann wie gut/performant der online mode funktioniert. [...] welche metriken nimmt man da normalerweise? was ist SOTA bei online modes/gaming?

I want to make the online mode playable, production ready. The first step would be a comprehensive performance benchmarking system (maybe with a live HUD again) to check, monitor and develop how well the online mode performs. Which metrics are normally used? What is state of the art in online gaming?

## 2. Requirements

- **Internet:** the host plays at home, the friend at their own home.
- **Two players** for now.
- **HUD:** eventually for every player, but first for development.

### Consequences

**Getting through home routers.** The server binds UDP `0.0.0.0:7777`; today only LAN clients can reach it.

| Option | Effort | Notes |
| --- | --- | --- |
| Port forwarding on the host's router | Low | Needs a public IPv4. DS-Lite/CGNAT (common on German cable and fiber lines) makes it impossible |
| Tailscale / ZeroTier | Low | No router setup, works behind CGNAT. Tunnel MTU 1280 (see 6a) |
| Small VPS running `server.py` | Medium | Both players get the same RTT (no host advantage), costs a few euros a month |

Decided since: direct peer-to-peer through a serverless rendezvous and hole punching, so neither router setup nor Tailscale is needed; Tailscale stays as the fallback. See [online-connectivity-brainstorm.md](online-connectivity-brainstorm.md). A VPS remains an option if the host advantage turns out to matter.

**Host advantage.** The host's client talks to the local server over loopback (RTT ~0), the friend gets the full internet RTT. In a 1v1 this is the largest fairness asymmetry, so every measurement has to cover both sides, not just the host's view.

**Packet size suddenly matters.** Loopback and LAN carry 20 KB UDP packets without complaint; the internet does not (see 6a).

## 3. What Players Feel: Three Latencies

"Ping" alone is not what a player feels. There are three different delays with different causes:

| What you see | How old it is | Measured today? |
| --- | --- | --- |
| Own movement, jump, dash | ~0 ms (predicted), but every misprediction is a visible snap | error in px yes, the visible snap no |
| Own unpredicted actions (projectile appears, hit, coin) | at least one RTT | no |
| The other player and the enemies | ½ RTT + interpolation delay (67-400 ms, adaptive) + up to 33 ms snapshot interval | not as a number |

## 4. Metrics

Four layers, from the wire up to what the player feels. "Today" refers to the existing counters in `GameClient.net_stats`, `MultiplayerGameState._stats` and the server's `_report()`.

### 4.1 Network (what the line does)

| Metric | Why | Today |
| --- | --- | --- |
| RTT p50/p95/p99 (not the mean) | baseline and spikes | partial: one heartbeat per second, smoothed |
| Jitter (spread of arrival intervals, RFC 3550 style) | sizes the jitter buffer | missing |
| Packet loss per direction | loss hurts deltas and inputs differently | missing |
| Reordering, duplicates | stresses the delta chain | partial: `deltas_deferred` |
| Bandwidth up/down, packets/s, packet size p95 | host upload, MTU | partial: last snapshot size only |

### 4.2 Netcode (how well the code hides the line)

| Metric | Why | Today |
| --- | --- | --- |
| Server tick rate, tick duration p99 | server hitches | yes: `tick_rate`, `tick_ms_p95`, `tick_ms_max` |
| Snapshot arrival gaps (longest, count > 100 ms) | network stalls | partial: `snap_gap_max`, in ticks |
| Interpolation buffer: delay, headroom, underruns | freezes of remote entities | yes: `interp_delay`, `interp_underruns` |
| **Inputs arriving per server tick (0 / 1 / 2+)** | main suspect for own-player snaps (6d) | missing |
| Mispredictions: rate, px, replayed ticks, CPU cost | prediction quality | partial: `reconcile_error_px`, `reconcile_max_px` |
| Delta chain breaks, full-snapshot requests | loss recovery | yes: `deltas_dropped`, `deltas_pruned` |

### 4.3 Experience (what the player feels)

| Metric | Why | Today |
| --- | --- | --- |
| **View age of the other player in ms** | "how far in the past do I see them" | missing |
| Visible corrections of the own ninja per minute and in px | the snap the player actually notices | missing |
| Remote freezes and teleports (count, longest) | stutter of the other player | yes: `remote_frozen_frames`, `remote_jump_frames` |
| Action-to-feedback latency per action | how sluggish shooting feels | missing |
| Disconnects, timeouts, join time | reliability | missing |
| Connection success, setup time, chosen path (LAN / IPv6 / IPv4) | does joining just work ([connectivity](online-connectivity-brainstorm.md)) | missing |

### 4.4 Fairness (relevant because players shoot each other)

| Metric | Why | Today |
| --- | --- | --- |
| Victim position on the shooter's screen vs. on the server at hit time | "I hit him / I was never touched" | missing |
| Deaths and kills the client could not have predicted | unexplained events | missing |

### 4.5 Lags as Events, Not Averages

Averages hide exactly what annoys. Every lag is logged as an event with start, duration and cause:

- **Network stall:** no snapshot for more than X ms.
- **Server hitch:** a tick takes longer than 16.7 ms.
- **Client hitch:** a frame takes longer than 33 ms.

If client and server logs carry the same timestamp (the server tick), a stutter can be attributed afterwards: "the lag at 21:14 was the friend's WLAN, not the server".

## 5. State of the Art

- **Live network graph:** Source/CS `net_graph` (the telemetry HUD in CS2 today) and Overwatch's network graph (Ctrl+Shift+N) show RTT, interpolation delay and loss per direction. Here: an overlay next to the F1 perf HUD.
- **Built-in network simulator:** Unreal (`PktLag`, `PktLoss`), Unity Netcode's Network Simulator. `tools/mp_netem.py` already covers this, seeded.
- **Server input buffer with time dilation:** Overwatch (GDC 2017) and Rocket League (GDC 2018). The server keeps 1-3 ticks of inputs buffered; the client runs its simulation minimally faster or slower so the buffer never runs dry, and sends inputs redundantly.
- **Packet design:** Glenn Fiedler (Gaffer on Games): acks as a 32-bit bitfield (exactly what `PacketHeader` already carries) and packets below ~1200 bytes.
- **Lag compensation:** the server rewinds other entities to what the shooter saw (Valve Source; Riot's analysis of peeker's advantage in Valorant).

## 6. Findings in the Current Code

What a network benchmark would show right away.

### 6a. Packets Are Too Large for the Internet

Measured headless with 2 players: `HeadlessGame` per level, both players holding a direction, 240 ticks, a snapshot every second tick, size of `Packet.to_bytes()`. Enemies dominate the size; the player count barely changes it.

| Level | Enemies | Full snapshot | Fragments (MTU 1500 / 1280) | Full lost at 1 % loss | Delta p50 | Deltas > 1200 B | Downstream |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 5 | 2.4 KB | 2 / 2 | 2 % | 0.7 KB | 0 % | 0.19 Mbit/s |
| 3 | 14 | 4.7 KB | 4 / 4 | 4 % | 0.9 KB | 3 % | 0.25 Mbit/s |
| 6 | 33 | 10.1 KB | 7 / 8 | 7-8 % | 1.5 KB | 90 % | 0.44 Mbit/s |
| 9 | 74 | 22.4 KB | 16 / 18 | 15-17 % | 5.3 KB | 100 % | 1.41 Mbit/s |
| 12 | 31 | 9.9 KB | 7 / 8 | 7-8 % | 2.5 KB | 100 % | 0.67 Mbit/s |
| 16 | 26 | 8.4 KB | 6 / 7 | 6-7 % | 2.1 KB | 99 % | 0.56 Mbit/s |

Internet paths carry ~1500 bytes per packet (DSL with PPPoE 1492, Tailscale 1280). IP splits larger packets into fragments, and one lost fragment loses the whole packet. Loss compounds: a lost delta breaks the chain, the client requests a full snapshot (`FULL_SNAPSHOT_INTERVAL`, `game_server.py:52`), and the full snapshot is the packet most likely to be lost. Loopback and LAN hide all of this. Upstream is harmless: an input packet is 184 B at 60/s (~90 kbit/s).

### 6b. RTT Is Measured Too Coarsely

One heartbeat per second (`HEARTBEAT_INTERVAL`, `game_client.py:40`), smoothed with factor 0.1 (`game_client.py:488`): a 300 ms spike moves the displayed value by ~27 ms. It uses `time.time()` (wall clock, can jump) instead of a monotonic clock. Better without new packets: every snapshot already carries the input ack, and the client knows when it sent that input tick. That gives 30 RTT samples per second (the server's hold time until the next broadcast has to be sent along or subtracted).

### 6c. Packet Loss Is Measurable but Not Counted

`PacketHeader` (`udp_transport.py:44`) already carries sequence, ack and ack bitfield, and `_update_ack_tracking()` (`udp_transport.py:186`) maintains them. Loss in both directions falls out almost for free.

### 6d. The Server Has No Input Buffer

`_apply_client_inputs()` (`game_server.py:308`) applies the most recently received movement state every tick (`ClientState.receive_input()`, `client_state.py:68`). A late packet makes the old state last one tick longer; two packets in one tick skip one. Jump and dash fire on arrival. The server then simulates differently from what the client predicted, and the client corrects. Under client-to-server jitter this is the likely main cause of own-player snaps. Measure first (inputs per server tick), then decide on an Overwatch-style buffer.

### 6e. Corrections Are Applied Hard

`_reconcile_local_player()` (`multiplayer_state.py:564`) rewinds, replays and leaves the ninja at the new position immediately. The usual approach is to keep the correction as a visual offset that decays over a few frames.

### 6f. The Other Player Can Be Shown ~0.5 s in the Past

Under bad WLAN the interpolation delay grows up to `INTERP_DELAY_MAX` = 24 ticks (400 ms, `multiplayer_state.py:35`), plus half the RTT. Whether a dash kill or a hit counts is still decided by the server on current positions. The host, on loopback, never feels this, so the server has to measure every client separately.

## 7. Proposed System

1. **`NetStats` core**, shared by client and server: rolling windows (1 s and 10 s), percentiles, events stamped with the server tick, one JSONL per session. The server keeps stats per client. Covers the missing metrics from section 4: per-snapshot RTT, loss from the ack bitfield, inputs per server tick, view age, visible corrections, lag events.
2. **Live HUD on F2** (F1 is the perf overlay, F2 is free):
   - Level 1: one line with a traffic-light color, e.g. `Ping 34 ±4 ms · Loss 0.2 % · View 110 ms`.
   - Level 2: graphs for RTT, snapshot arrivals (gaps in red), interpolation headroom and markers for corrections.
   - Later, for players: a connection indicator per player.
3. **Netbench**: `mp_e2e` and `mp_netem` combined into a matrix.
   - Topology: host bot on loopback, friend bot through `mp_netem`, so both sides of the host advantage are measured.
   - Profiles: loopback, WLAN and harsh WLAN (as used in 5ddb08c), internet DE-DE, the friend's real line (calibrated, see section 8), lag spikes.
   - Levels: small (0) and large (9).
   - `mp_netem` needs an `--mtu` option that drops per fragment instead of per packet; today a 22 KB packet has the same loss chance as a 200 B one. Burst loss (Gilbert-Elliott) instead of only independent loss would also be closer to reality.
   - Seeded runs, median of several runs against noise (the lesson from the single-player suite), pass/fail against the targets in section 9, history like BENCHMARKS.md.
4. **Real sessions: logging only.** Client and server always write their `NetStats` JSONL during a real game (the host already spawns the server; it passes a metrics file automatically). No report tool (see section 8).

## 8. Follow-up: Report After a Game Night?

> bei deiner skizze punkt 4: report nach dem spieleabend, ist das wirklich nützlich? oder wäre das overpowered? können wir nicht sobald wir die metriken zuverlässig messen können, die metriken maxxen?

Is a report after a game night really useful, or overpowered? Can't we just max out the metrics once we can measure them reliably?

**A report tool is overpowered for two players.** It is dropped.

**Maxing the metrics is the right workflow, with two conditions:**

1. **The benchmark has to resemble the real line.** `mp_netem` is synthetic: uniform jitter, independent loss, periodic doze windows, no fragmentation. Real lines have loss bursts, evening congestion and WLAN power-save patterns. Optimizing only against netem risks tuning for a network nobody has. Hence the cheap part of the report idea stays: always-on logging in real sessions. One or two real evenings calibrate the "friend's line" profile (RTT distribution, jitter, loss bursts); after that, all optimizing happens in the netbench. After larger changes, one real evening checks that the gains carry over. Analysis by hand or with a small script, no tool.
2. **The metrics pull against each other, so "max" needs a target.** A larger interpolation delay drives freezes to zero but ages the view; redundant inputs soften loss but cost bandwidth; heavier correction smoothing hides snaps but delays the own position. So: a primary goal plus guardrails (section 9).

## 9. Optimization Target and Starting Values

**Primary goal:** minimize the lag players feel: remote freezes (count, longest) and visible corrections of the own ninja.

**Guardrails:** must not get worse while optimizing.

Starting values, rules of thumb to be calibrated with the first real session:

| Metric | Role | Starting target |
| --- | --- | --- |
| Remote freezes | primary | ~0 per minute, longest < 250 ms |
| Visible corrections of the own ninja (> 2 px) | primary | < 1 per minute |
| View age of the other player, p95 | guardrail | < 150 ms |
| RTT p95 per player | context | < 80 ms good, > 150 ms noticeable |
| Jitter | context | < 15 ms |
| Packet loss per direction | context | < 1 % |
| Packet size p95 | guardrail | < 1200 B |
| Bandwidth per client | guardrail | < 0.5 Mbit/s |
| Server tick p99 | guardrail | < 8 ms (budget 16.7 ms) |

"Context" values describe the line, not the code; the netbench sets them through the profile.

## 10. Order of Work

1. **`NetStats` core** in client and server, with always-on session logging. *Done (section 12).*
2. **Dev HUD on F2** (levels 1 and 2).
3. **Connectivity for a first real session** (rendezvous and hole punching, see [online-connectivity-brainstorm.md](online-connectivity-brainstorm.md); Tailscale works as a stopgap). Record one real evening and calibrate the friend's-line profile. Can happen at any point; it only needs step 1 for useful data.
4. **Netbench**: 2 players, levels 0 and 9, profiles from section 7, `mp_netem` with `--mtu` and burst loss.
5. **Fixes driven by the numbers.** Likely order: packet size (MTU), server input buffer, correction smoothing, interpolation delay tuning, lag compensation only if the fairness metric demands it.

## 11. Open Questions

- **Lag compensation for player-vs-player hits:** needed? Decide once the fairness metric (4.4) has numbers.
- **When does the HUD become a player feature** (connection indicator for everyone)?

## 12. Step 1 Implemented: First Measurements

`scripts/network/netstats.py` plus the wiring in transport, server, client and `MultiplayerGameState`; fields and log format in [multiplayer.md](multiplayer.md#session-logs). Sections 6b and 6c are resolved: RTT is measured from every snapshot (30 samples/s) with kernel receive timestamps and the server's hold time subtracted, and loss is counted per direction from per-peer sequence numbers.

Two things surfaced while verifying:

- **Hold time measured too early.** It was taken before the snapshot was serialized (three times per broadcast, one of them only for the `last_snapshot_bytes` stat), which added ~1 ms to every RTT sample on level 0 and more on large levels. Now it is stamped right before each send, and sizes come from the sent packets; loopback RTT p50 went from 1.26 ms to 0.43 ms.
- **Orphaned host server.** Closing the window skipped `MultiplayerGameState.on_exit`, so the hosted server kept running with the port bound, and the next "Host Game" would join the old server. Fixed: the window close ends the session cleanly, and the server shuts down when its parent game exits (`--parent-pid`).

### Loopback (`tools/mp_e2e.py`, 2 bots)

RTT p50 0.43 ms, p95 < 1 ms, no loss either way. Even on loopback up to 1.7 % of server ticks get no new input and 1.7 % get two: the client and server 60 Hz clocks drift against each other.

### Emulated WLAN: host on loopback, friend through `mp_netem`

Profile: 15 ms one-way delay, 0-25 ms uniform jitter, 2 % loss per direction, 80 ms doze every 300 ms. Level 0, the game client (`MultiplayerGameState`, autopilot `runner`) as the friend, a bot as the host.

| Metric | Measured | Check |
| --- | --- | --- |
| RTT p50 / p95 | 57 / 113 ms | expected ~55 ms (2 x 15 ms + mean jitter) |
| Jitter client to server | 8.5 ms | theory for uniform 0-25 ms: 8.3 ms |
| Jitter server to client | 18 ms | higher: doze windows release packets in bursts |
| Loss client to server / server to client | 1.7 % / 1.3 % | 2 % configured |
| Snapshot stalls (gap >= 100 ms) | 25 in 15 s | doze windows |
| View age of the other player, p95 | ~350 ms | interpolation delay grew to 283 ms |
| **Server ticks without a new input / with 2+** | **28 % / 20 %** (host: 0 %) | confirms 6d |
| **Visible corrections of the own ninja** | **~2-3 per second** (mispredictions ~10/s) | target < 1 per minute |

The friend's own corrections and the server's input classification line up: under client-to-server jitter almost half of the server ticks apply the wrong input timing, and the friend sees the own ninja snap several times per second. The host sees none of it. This makes the server input buffer (6d) and correction smoothing (6e) the first candidates once the netbench (step 4) can measure fixes against a baseline.
