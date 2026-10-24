# Multiplayer

Server-authoritative multiplayer over UDP. One player hosts (the game spawns a
dedicated server process locally), other players join by friend code over the
internet, or by address on the LAN.

## Playing

### Friend codes (once)

Every installation has a friend code, shown in **Multiplayer** (e.g.
`K7QM-2XRA`). Send yours to your friend once; they add it under
**Join Friend** → **+ Add friend**. The code is the invitation: whoever
knows it can join your game while you host.

### Host (Player A)

1. Start the game: `python app.py`
2. Menu → **Multiplayer** → **Host Game**
3. You enter the currently selected level immediately. The HUD (bottom left)
   shows your code and LAN address, e.g. `Tom | Code K7QM-2XRA | LAN 192.168.178.92:7777`
   (`(not online)` if the rendezvous cannot be reached; LAN play still works).

### Join (Player B)

1. Start the game: `python app.py`
2. Menu → **Multiplayer** → **Join Friend**: friends who are hosting show
   `hosting level N`; select one and press Enter. The game finds the host
   through the rendezvous and opens a direct path (IPv6, LAN or IPv4); the
   HUD shows which one (`via IPv6`).
3. Without the rendezvous: **Join by IP**, type the host's address
   (`192.168.178.92` or `192.168.178.92:7777`) and press Enter. The last
   address is remembered.

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

**F2** cycles the network HUD (top right): off → status line → status line
plus graphs. The status line rates ping, packet loss (to you / to the
server, mean of the last 10 s), view age (how old the other player you see is, p95) and own-ninja
snaps in the last 10 s, each green / yellow / red by the starting targets
in `docs/online-benchmark-brainstorm.md` (section 9). The graphs show the
last 10 s: RTT per snapshot, gaps between arriving snapshots (red ≥ 100 ms),
the interpolation buffer (headroom against the delay, red when starved,
own-ninja snaps as red marks), and what the server reports about your link.

## Rules (multiplayer specific)

- Every player spawns with a gun and 15 ammo; ammo pickups give +5.
- Player projectiles hit **other players** (never the shooter): 1 life per hit.
- Dash kills and projectile kills on enemies credit a coin to that player.
- Falling off the map costs a life and respawns you; at 0 lives you respawn
  with full lives (arena style). Coins (score) persist across deaths.
- Multiplayer coins/ammo are session-only — they never touch your saved wallet.

## Two machines / firewall

The server binds UDP `[::]:7777` (IPv6 and IPv4). On macOS the Application
Firewall must allow Python to accept incoming connections — accept the prompt
on first host (and on first join by code), or check *System Settings → Network
→ Firewall → Options* if joining times out. (Loopback play is never affected.)

## Online play by friend code

See `docs/online-connectivity-brainstorm.md` for the design. No game server
runs anywhere: the host's machine is the server, as on the LAN.

1. The host's server learns its addresses with STUN (`stun.cloudflare.com`)
   on its own UDP socket: the IPv6 address it sends from and the public IPv4
   address and port the router maps it to; plus its LAN address. These are
   its *candidates*.
2. Every 2 s it registers its code, name, level, protocol version and
   candidates at the **rendezvous**, a Cloudflare Worker (`rendezvous/`); the
   call also returns join requests waiting for it.
3. The friend's game learns its own candidates the same way and sends them
   with a join request; the rendezvous answers with the host's candidates.
4. Both sides send `punch` packets to all of the other's candidates (every
   100 ms, up to 10 s); each router takes the other side's packets for
   replies. The first candidate that answers is the path; the game connects
   over it with the normal protocol.

The rendezvous only sees codes, names and addresses (presence expires after
15 s); game traffic never passes through it. Each code's secret token is
stored as a hash on first use, so nobody else can host under your code.
Identity and friends live in `data/online.json`.

```bash
cd rendezvous && npm install && npx wrangler dev     # local rendezvous on :8787
python tools/mp_online_e2e.py --rendezvous http://127.0.0.1:8787
python tools/mp_online_e2e.py                       # against the deployed one
cd rendezvous && npx wrangler deploy                 # after npx wrangler login
```

`NINJA_RENDEZVOUS_URL` points the game and server at another rendezvous,
`NINJA_ONLINE_FILE` gives a second game on the same machine its own identity.
If no path answers (both sides behind strict NAT without IPv6), **Join by IP**
over Tailscale is the fallback.

## Architecture

| Piece | File | Role |
| --- | --- | --- |
| Dedicated server | `server.py` | 60 Hz fixed-timestep loop, session log (see [Session logs](#session-logs)) |
| World simulation | `scripts/network/headless_game.py` | Full sim without rendering: players, enemies (AI targets nearest player), projectiles, collectables, respawns |
| Networking (server) | `scripts/network/game_server.py` | Connections, input ingestion, snapshot broadcast (30 Hz, deltas against each client's acked snapshot) |
| Networking (client) | `scripts/network/game_client.py` | Connection lifecycle, input sending, snapshot reconstruction, RTT |
| Client gameplay | `scripts/multiplayer_state.py` | Prediction (rewind+replay), interpolation, world application, HUD |
| Lobby UI | `scripts/multiplayer_menu.py` | Host/Join menu states, server subprocess spawn |
| Netcode metrics | `scripts/network/netstats.py` | Link statistics, metrics, events, session logs |
| Online play | `scripts/network/online.py`, `stun.py` | Friend codes, rendezvous calls, STUN, candidates, hole punching |
| Rendezvous | `rendezvous/src/index.js` | Cloudflare Worker + Durable Object: presence, join requests |

Protocol decisions:

- **One physics step per input.** Every client frame is one input: held
  movement plus the actions pressed in it. The server runs each player one
  physics step per input, in input order, with that input's actions (as the
  Source engine runs player commands), so its trajectory matches the
  client's prediction step for step, however the packets arrive: a tick
  without a new input makes no step for that player, a burst catches up at
  most 2 steps per tick. Before, the server applied the newest movement
  once per tick, and arrival jitter alone made the friend's ninja snap up
  to 200 times a minute (see `docs/online-benchmark-brainstorm.md`).
- **Inputs survive loss.** Each packet carries the movement of the 3
  previous ticks (`history`); a hole that stays anyway is filled with the
  last movement after 3 ticks. Actions (jump/dash/shoot) carry a sequence
  number and their tick, are re-sent until the server has run that tick,
  and are deduplicated server-side. Client ticks advance by exactly one
  per input, so they are never resynced to the server's tick.
- **Acks for prediction.** Snapshots carry per-player `acks`: the newest
  input that has run. The client rewinds to server state and replays the
  inputs after it — no threshold rubber-banding.
- **Deltas against the acked snapshot.** Every input carries `snap`, the
  newest snapshot the client has reconstructed; the server keeps its last
  32 broadcasts and sends each client a delta against its acked one (as
  Quake 3 does), or a full snapshot without a usable ack. A lost packet
  only makes the next delta a little larger. Before, deltas went against
  the previous broadcast, and one lost delta made every following one
  unusable until a requested full snapshot arrived.
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
- **Dual stack.** Sockets bind `::` with IPv4 mapped in; peers are plain
  `(host, port)` tuples either way (IPv4 never as `::ffff:a.b.c.d`), host
  names are resolved once. STUN answers arrive on the game socket and go to
  the STUN probe instead of the game.
- **Protocol version.** `connect_request` carries `version`
  (`PROTOCOL_VERSION` in `messages.py`); the server rejects another version
  with a clear reason instead of letting it run with a broken state.
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

## Netbench

```bash
python tools/mp_netbench.py           # 4 network profiles x 3 runs (~6 min)
python tools/mp_netbench.py --quick   # 1 short run per profile
python tools/mp_netbench.py --save    # record a new reference point
```

Each run plays a real two-player session: the server, the host's game
client on loopback and the friend's game client behind `tools/mp_netem.py`,
both the real game with the `runner` autopilot and closing their window at
the end. The session logs are reduced to the core metrics (own-ninja snaps
per minute, freezes, view age, inputs per server tick, RTT, loss,
bandwidth), and the median of the runs is shown next to the reference
point `docs/benchmarks/netbench-baseline.json`. The netbench fails if any
player data file changes during the runs.

| Profile | Emulates | `mp_netem` settings |
| --- | --- | --- |
| `loopback` | both on one machine | none |
| `internet` | wired lines within Germany | 12 ms delay, 0-4 ms jitter, 0.5 % loss |
| `wlan` | friend on Wi-Fi at home | 15 ms, 0-10 ms, 1 %, 40 ms doze every 500 ms |
| `bad_wlan` | weak Wi-Fi with power-save bursts | 15 ms, 0-25 ms, 2 %, 80 ms doze every 300 ms |

The profiles are starting values until a real session calibrates them.
`mp_netem` adds jitter independently per packet, so it reorders more than a
real line with the same jitter.

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
| `reconcile_px_*`, `mispredictions`, `corrections`, `respawns` | How far reconciliation moved the own ninja; mispredictions > 0.5 px, corrections > 2 px (a visible snap); a move while the lives change is a respawn, not counted as a snap |
| `reconcile_ms_*` | CPU time of rewind and replay |
| `freeze_ms_*`, `freezes` | How long a remote player stood still while it should move; freezes of 50 ms or more |
| `frame_ms_*`, `frame_hitches` | Real frame intervals; hitches > 25 ms |
| `server_view` | How the server receives this client: `c2s_loss_pct`, `c2s_jitter_ms`, `starved_pct`, `burst_pct`, `no_step_pct`, `multi_step_pct`, `backlog`, `s2c_max_bytes` / `s2c_oversize` (largest packet to this client, packets > 1200 B) |

The older cumulative fields (`interp_underruns`, `remote_frozen_frames`,
`remote_jump_frames`, `net_*`, ...) are still there.

**Server sample** (`server.py`):

| Field | Meaning |
| --- | --- |
| `tick_ms_*`, `tick_interval_ms_*`, `hitches` | Simulation time per tick, time between tick starts; hitches are ticks > 16.7 ms or starting > 33 ms after the previous one |
| `full_bytes_*`, `delta_bytes_*` | Sizes of sent snapshot packets |
| `input_stalls` | Gaps of 100 ms or more between a client's inputs |
| `peers.<id>` | Per client: `c2s_loss_pct`, `c2s_jitter_ms`, `starved_pct` / `burst_pct` (server ticks in which no / 2+ new inputs arrived), `no_step_pct` / `multi_step_pct` (ticks in which the player made no / 2+ physics steps), `backlog` (inputs waiting), `ticks` (counts, also `filled`, `dropped`, `late_actions`), `link` (rx = client to server, tx = server to client), `client` (the client's own summary from its heartbeats) |

Since every client sends its summary with its heartbeat, the host's server
log alone shows how the session went for every player.

**Events:** client `connected`, `joined` (with ms since connecting),
`net_stall`, `correction` (> 8 px), `respawn`, `remote_freeze`, `client_hitch`
(> 50 ms), `disconnected`; server `client_joined`, `client_left`,
`input_stall`, `server_hitch`.
