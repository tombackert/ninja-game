# Multiplayer

Server-authoritative multiplayer over UDP. One player hosts (the game spawns a
dedicated server process locally), other players join over the LAN.

## Playing

### Host (Player A)

1. Start the game: `python app.py`
2. Menu → **Multiplayer** → **Host Game**
3. You enter the currently selected level immediately. The HUD (bottom left)
   shows the address other players use to join, e.g. `Hosting on 192.168.178.92:7777`.

### Join (Player B)

1. Start the game: `python app.py`
2. Menu → **Multiplayer** → **Join Game**
3. Type the host's address (`192.168.178.92` or `192.168.178.92:7777`) and press Enter.

Two windows on one machine work the same way: host in the first window, join
`127.0.0.1` in the second.

### CLI shortcuts

```bash
python server.py --port 7777 --level 0        # dedicated server only
python app.py --multiplayer --host <ip> --port 7777 --name Tom
```

### Controls

Same as single player (arrows/WASD move, jump, `x` dash, `c` shoot). ESC pauses
locally — the connection stays alive while paused.

## Rules (multiplayer specific)

- Every player spawns with a gun and 15 ammo; ammo pickups give +5.
- Player projectiles hit **other players** (never the shooter): 1 life per hit.
- Dash kills and projectile kills on enemies credit a coin to that player.
- Falling off the map costs a life and respawns you; at 0 lives you respawn
  with full lives (arena style). Coins (score) persist across deaths.
- Multiplayer coins/ammo are session-only — they never touch your saved wallet.

## Two machines / firewall

The server binds UDP `0.0.0.0:7777`. On macOS the Application Firewall must
allow Python to accept incoming connections — accept the prompt on first host,
or check *System Settings → Network → Firewall → Options* if joining from the
second machine times out. (Loopback play is never affected.)

## Architecture

| Piece | File | Role |
| --- | --- | --- |
| Dedicated server | `server.py` | 60 Hz fixed-timestep loop, session log (see [Session logs](#session-logs)) |
| World simulation | `scripts/network/headless_game.py` | Full sim without rendering: players, enemies (AI targets nearest player), projectiles, collectables, respawns |
| Networking (server) | `scripts/network/game_server.py` | Connections, input ingestion, snapshot broadcast (30 Hz, delta-compressed, periodic full) |
| Networking (client) | `scripts/network/game_client.py` | Connection lifecycle, input sending, snapshot reconstruction, RTT, tick resync |
| Client gameplay | `scripts/multiplayer_state.py` | Prediction (rewind+replay), interpolation, world application, HUD |
| Lobby UI | `scripts/multiplayer_menu.py` | Host/Join menu states, server subprocess spawn |
| Netcode metrics | `scripts/network/netstats.py` | Link statistics, metrics, events, session logs |

Protocol decisions:

- **Inputs = state + events.** Held movement is sent as state every frame
  (loss/drift tolerant); one-shot actions (jump/dash/shoot) carry sequence
  numbers, are re-sent until acknowledged and deduplicated server-side.
- **Acks for prediction.** Snapshots carry per-player `acks` (newest applied
  input tick). The client rewinds to server state and replays unacknowledged
  inputs — no threshold rubber-banding.
- **Snapshots exclude RNG state** (was ~5 KB JSON per snapshot, now ~2.2 KB
  total for a full snapshot).
- **Remote entities render on a 60 Hz interpolation clock** trailing the
  newest snapshot by `INTERP_DELAY` (4 ticks ≈ 67 ms), so 30 Hz snapshots
  still produce fluid motion.
- **Collectables sync by stable ID** — extraction order from the level JSON
  (coins, then ammo) is identical on client and server.
- **Packet sequence numbers are per peer**, so a receiver counts loss from
  sequence gaps. Every header carries the sender's send time (for jitter).
- **RTT from every snapshot.** Snapshots carry `holds`: how long each acked
  input has waited on the server. The client measures
  `snapshot arrival - input send - hold`, with kernel receive timestamps
  (`SO_TIMESTAMP`) as arrival times, so the time packets sit in socket
  buffers until the next tick/frame reads them is not counted as ping.
- **The hosted server follows its game.** It gets `--parent-pid` and shuts
  down when the host's game exits; closing the window also leaves the
  session cleanly.

## E2E testing

```bash
python tools/mp_e2e.py --duration 10   # real processes: server + 2 bots
```

Asserts cross-client state identity per tick (delta-chain integrity), input
application, enemy/projectile sync, 60 ticks/s server, ~60 fps clients,
snapshot rate, RTT and ack lag, no packet loss in either direction, and
that client reports reach the server log. `--keep-logs` retains the logs.

Windowed instances can run scripted too:

```bash
NINJA_MP_AUTOPILOT=runner NINJA_MP_METRICS=/tmp/a.jsonl python app.py --multiplayer
```

Patterns: `runner` (moves/jumps/dashes), `shooter` (jumps/shoots).
`NINJA_MP_METRICS` writes the client's session log to that file.

To test against an emulated bad network, put `tools/mp_netem.py` between a
client and the server (delay, jitter, loss, Wi-Fi doze bursts).

## Session logs

Every multiplayer session writes a JSONL log to `data/netlogs/` (newest 20
per role are kept): the game client as `<date>-<time>-client-<name>-<pid>.jsonl`,
the server as `...-server-<pid>.jsonl`. `NINJA_MP_METRICS=<path>` (client) and
`--metrics-file <path>` (server) log to that file instead; `NINJA_NETLOG=0`
(client) and `--no-netlog` (server) turn logging off.

Each line has a `type`:

| Type | When | Content |
| --- | --- | --- |
| `session` | first line | role, name/host/port (client), level/port/tick rate (server) |
| `sample` | every second | flat metrics of that second (below) |
| `event` | when it happens | `event` name, wall-clock `t`, server `tick`, details |
| `summary` | at exit | duration and session totals of counters and link statistics |

Metrics are reported as `<name>_p50`, `_p95`, `_p99` and `_max` over the
second; counters are the count in that second.

**Client sample** (the game client, `scripts/multiplayer_state.py`):

| Field | Meaning |
| --- | --- |
| `rtt_ms_*` | Network RTT, measured from every snapshot (queueing removed); `rtt_hb_ms_*` the same from heartbeats |
| `snap_gap_ms_*`, `stalls` | Real time between arriving snapshots (expected 33 ms); stalls are gaps of 100 ms or more |
| `link_*` | Packet level from the client's side: `link_lost`, `link_loss_pct`, `link_jitter_ms` for server-to-client, `link_rx_bytes`, `link_tx_bytes`, `link_tx_oversize` (packets > 1200 B) |
| `view_age_ms_*` | How old the rendered other players and enemies are: half the RTT + interpolation delay + age of the newest snapshot |
| `interp_delay_ms` | Current adaptive interpolation delay |
| `reconcile_px_*`, `mispredictions`, `corrections` | How far reconciliation moved the own ninja; mispredictions > 0.5 px, corrections > 2 px (a visible snap) |
| `reconcile_ms_*` | CPU time of rewind and replay |
| `freeze_ms_*`, `freezes` | How long a remote player stood still while it should move; freezes of 50 ms or more |
| `frame_ms_*`, `frame_hitches` | Real frame intervals; hitches > 25 ms |
| `server_view` | How the server receives this client: `c2s_loss_pct`, `c2s_jitter_ms`, `starved_pct`, `burst_pct` |

The older cumulative fields (`interp_underruns`, `remote_frozen_frames`,
`remote_jump_frames`, `net_*`, ...) are still there.

**Server sample** (`server.py`):

| Field | Meaning |
| --- | --- |
| `tick_ms_*`, `tick_interval_ms_*`, `hitches` | Simulation time per tick, time between tick starts; hitches are ticks > 16.7 ms or starting > 33 ms after the previous one |
| `full_bytes_*`, `delta_bytes_*` | Sizes of sent snapshot packets |
| `input_stalls` | Gaps of 100 ms or more between a client's inputs |
| `peers.<id>` | Per client: `c2s_loss_pct`, `c2s_jitter_ms`, `starved_pct` (server ticks without a new input: the old movement is reused), `burst_pct` (ticks with 2+ new inputs: all but the newest are skipped), `link` (rx = client to server, tx = server to client), `client` (the client's own summary from its heartbeats) |

Since every client sends its summary with its heartbeat, the host's server
log alone shows how the session went for every player.

**Events:** client `connected`, `joined` (with ms since connecting),
`net_stall`, `correction` (> 8 px), `remote_freeze`, `client_hitch`
(> 50 ms), `disconnected`; server `client_joined`, `client_left`,
`input_stall`, `server_hitch`.
