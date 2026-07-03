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
| Dedicated server | `server.py` | 60 Hz fixed-timestep loop, per-second perf metrics (`--metrics-file`) |
| World simulation | `scripts/network/headless_game.py` | Full sim without rendering: players, enemies (AI targets nearest player), projectiles, collectables, respawns |
| Networking (server) | `scripts/network/game_server.py` | Connections, input ingestion, snapshot broadcast (30 Hz, delta-compressed, periodic full) |
| Networking (client) | `scripts/network/game_client.py` | Connection lifecycle, input sending, snapshot reconstruction, RTT, tick resync |
| Client gameplay | `scripts/multiplayer_state.py` | Prediction (rewind+replay), interpolation, world application, HUD |
| Lobby UI | `scripts/multiplayer_menu.py` | Host/Join menu states, server subprocess spawn |

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

## E2E testing

```bash
python tools/mp_e2e.py --duration 10   # real processes: server + 2 bots
```

Asserts cross-client state identity per tick (delta-chain integrity), input
application, enemy/projectile sync, 60 ticks/s server, ~60 fps clients,
snapshot rate, RTT and ack lag. `--keep-logs` retains JSONL metrics.

Windowed instances can run scripted too:

```bash
NINJA_MP_AUTOPILOT=runner NINJA_MP_METRICS=/tmp/a.jsonl python app.py --multiplayer
```

Patterns: `runner` (moves/jumps/dashes), `shooter` (jumps/shoots).
`NINJA_MP_METRICS` appends one JSON line per second (fps, rtt, ack lag,
reconcile error, entity counts).
