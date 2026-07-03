# MP-05: GameClient Implementation

## Context

The multiplayer branch has solid server-side infrastructure (MP-01 through MP-04): global tick counter, entity IDs, UDP transport, NetSyncService, delta compression, interpolation buffer, and a full GameServer with client management. The **next major step** is the client-side counterpart — a `GameClient` class that connects to the server, sends inputs, receives snapshots, and provides the building blocks for client-side prediction.

This is Phase 3 of the multiplayer roadmap (Phases 1-2 are complete).

---

## New File: `scripts/network/game_client.py` (~250-300 lines)

### Class: `GameClient`

Mirrors the GameServer's structure and message protocol. Pure networking logic — no Game/Player imports, no physics, no UI.

### Constructor

```python
GameClient(
    server_host: str = "127.0.0.1",
    server_port: int = 7777,
    player_name: str = "Player",
    transport: UDPTransport | None = None,  # inject for testing
)
```

- When `transport` is None, creates a `UDPTransport()` with ephemeral port
- Stores `_server_addr = (server_host, server_port)`
- Initial state: `ConnectionState.DISCONNECTED`

### Internal State

| Field | Type | Purpose |
|-------|------|---------|
| `_state` | `ConnectionState` | Connection lifecycle |
| `_player_id` | `int | None` | Assigned by server on connect |
| `_server_tick` | `int` | Last authoritative tick from snapshots |
| `_local_tick` | `int` | Local estimate, incremented each frame |
| `_snapshot_buffer` | `SnapshotBuffer` | Stores received snapshots (20-frame history) |
| `_last_full_snapshot` | `SimulationSnapshot | None` | Base for delta application |
| `_input_history` | `dict[int, list[str]]` | Sent inputs by tick (for reconciliation) |
| `_rtt_estimate` | `float` | RTT via exponential moving average |

### Public API

```python
# Lifecycle
connect() -> None              # Send connect_request, transition to CONNECTING
disconnect() -> None           # Send disconnect, transition to DISCONNECTED
update() -> None               # Call once per frame: process messages, heartbeat, timeout check
close() -> None                # Release transport resources

# Input
send_inputs(tick, inputs) -> None  # Send actions to server + store in history

# State queries (properties)
state -> ConnectionState
is_connected -> bool
player_id -> int | None
server_tick -> int
local_tick -> int
rtt -> float

# Snapshot access
get_latest_snapshot() -> SimulationSnapshot | None
get_snapshot_buffer() -> SnapshotBuffer

# Prediction support
get_unacknowledged_inputs(since_tick) -> dict[int, list[str]]

# Callbacks
on_connected(callback: Callable[[int], None])
on_disconnected(callback: Callable[[str], None])
on_player_joined(callback: Callable[[int, str], None])
on_player_left(callback: Callable[[int, str], None])
```

### Connection State Machine

```
DISCONNECTED --connect()--> CONNECTING --connect_accept--> CONNECTED --disconnect()--> DISCONNECTED
                               |                              |
                          max retries                    server_shutdown
                          or reject                      or timeout
                               |                              |
                               v                              v
                          DISCONNECTED                   DISCONNECTED
```

- **CONNECTING**: Sends `connect_request`, retries every 1s, gives up after 5 attempts
- **CONNECTED**: Increments `_local_tick`, sends heartbeats every 1s, detects server timeout at 10s
- **DISCONNECTING**: Immediate transition (no server ack wait — KISS)

### `update()` Flow (called every frame)

1. If CONNECTING: retry connect if interval elapsed
2. Process all incoming messages (dispatch by type)
3. If CONNECTED:
   - Increment `_local_tick`
   - Send heartbeat if interval elapsed
   - Check server timeout
   - Prune old `_input_history` entries (> 60 ticks behind server_tick)

### Message Handling (mirrors GameServer pattern)

| Incoming Message | Handler | Action |
|-----------------|---------|--------|
| `connect_accept` | Store `player_id` + `server_tick`, set `_local_tick`, fire callback, transition to CONNECTED |
| `connect_reject` | Fire `on_disconnected(reason)`, transition to DISCONNECTED |
| `snapshot` | If delta: `apply_delta()` on `_last_full_snapshot`. Store in buffer. Update `_server_tick` |
| `heartbeat_ack` | Compute RTT from `client_time` roundtrip |
| `player_joined` | Fire `on_player_joined(id, name)` callback |
| `player_left` | Fire `on_player_left(id, reason)` callback |
| `server_shutdown` | Fire `on_disconnected("server_shutdown")`, transition to DISCONNECTED |

### Constants

```python
CONNECT_RETRY_INTERVAL = 1.0   # seconds between connect retries
MAX_CONNECT_ATTEMPTS = 5       # give up after this many
HEARTBEAT_INTERVAL = 1.0       # seconds between heartbeats
SERVER_TIMEOUT = 10.0           # disconnect if no messages for this long
```

### Imports (all from existing modules)

```python
from scripts.network.client_state import ConnectionState
from scripts.network.delta import apply_delta
from scripts.network.interpolation import SnapshotBuffer
from scripts.network.messages import Message
from scripts.network.udp_transport import UDPTransport
from scripts.snapshot import SimulationSnapshot, SnapshotService
```

---

## New File: `tests/test_game_client.py` (~300 lines)

Uses real `UDPTransport` on localhost with unique ports per test class (19001-19069 range). Reuses `MockGame`/`MockPlayer` pattern from `tests/test_game_server.py`.

### Test Cases

**Connection:**
- Client starts in DISCONNECTED state
- Client connects to server (CONNECTING -> CONNECTED), gets player_id
- Client handles rejection (server full)
- Client retries on no response, gives up after MAX_CONNECT_ATTEMPTS
- `on_connected` / `on_disconnected` callbacks fire correctly

**Input Sending:**
- `send_inputs()` transmits to server (verify server receives them)
- Inputs stored in `_input_history`
- Old inputs pruned after 60 ticks

**Snapshot Reception:**
- Client receives full snapshot via `get_latest_snapshot()`
- Client reconstructs delta snapshot correctly
- Snapshots stored in buffer with correct ticks

**Heartbeat/RTT:**
- Client sends heartbeats after interval
- RTT computed from heartbeat roundtrip

**Disconnection:**
- Graceful disconnect transitions state
- Server shutdown message triggers disconnect
- Server timeout triggers disconnect

**Player Events:**
- `on_player_joined` fires when second client connects
- `on_player_left` fires when client disconnects

---

## What is explicitly NOT in this step

- **MultiplayerGameState** — Game loop integration comes later
- **Full client-side prediction with physics replay** — GameClient provides `get_unacknowledged_inputs()` as a building block; actual physics replay is a separate step
- **Remote entity interpolation rendering** — Existing `interpolate_entity()` will be used later at the rendering layer
- **Lobby / UI** — GameClient is headless
- **Reconnection logic** — Once disconnected, stays disconnected
- **Clock synchronization** — Simple tick increment for now
- **Input redundancy** — One tick of inputs per message (packet loss tolerance deferred)

---

## Verification

1. **Run new tests**: `python -m pytest tests/test_game_client.py -v`
2. **Run all multiplayer tests**: `python -m pytest tests/test_game_server.py tests/test_game_client.py tests/test_udp_transport.py tests/test_netsync_service.py tests/test_entity_id.py -v`
3. **Type check**: `python -m mypy scripts/network/game_client.py`
4. **Lint/format**: `python -m ruff check scripts/network/game_client.py && python -m black --check scripts/network/game_client.py`
5. **Integration smoke test**: Manually verify a GameClient can connect to a GameServer, send inputs, and receive a snapshot in a simple test script
