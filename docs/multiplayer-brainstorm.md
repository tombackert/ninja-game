# Multiplayer Brainstorm

**Date:** 2026-01-19
**Branch:** `multiplayer`
**Status:** Planning

This document outlines the design and implementation strategy for adding multiplayer functionality to Ninja Game.

---

## 1. State of the Art: Multiplayer Networking Approaches

### 1.1 Client-Server Architecture (Authoritative Server)

The most common model for multiplayer games. One machine (server) hosts the game, processes logic, and manages world state. Clients connect and send inputs.

**Key Principle:** Never trust clients. The server has final authority on all game state.

**Flow:**
```
Client → [Input] → Server → [Process] → Server → [State Update] → Client → [Render]
```

**Pros:**
- Cheat-resistant (server validates everything)
- Clear authority model
- Scales to many players

**Cons:**
- Requires dedicated server or host player
- Latency between input and visual feedback
- Server is single point of failure

**Solutions for Latency:**
1. **Client-Side Prediction** - Client immediately applies own inputs locally
2. **Server Reconciliation** - Correct prediction errors when server responds
3. **Entity Interpolation** - Smooth remote entity movement between snapshots

### 1.2 Rollback Netcode (GGPO-style)

Used primarily in fighting games and fast-paced action games where responsiveness is critical.

**How It Works:**
1. Game predicts remote player inputs (usually: same as last frame)
2. Simulation continues without waiting for network
3. When actual inputs arrive, compare to predictions
4. If different: rollback to last known-good state, replay with correct inputs
5. Players only notice latency when predictions are wrong

**Requirements:**
- **Determinism** - Same inputs + state = same result on all machines
- **State Serialization** - Full game state must be saveable/loadable
- **Fixed Timestep** - Frame-by-frame advancement
- **Fast Simulation** - Must resimulate many frames within one render frame

**Pros:**
- Near-zero perceived latency when predictions are correct
- Excellent for competitive games
- P2P friendly (no dedicated server needed)

**Cons:**
- Complex implementation
- CPU-intensive (multiple resimulations per frame)
- Visual "teleporting" when predictions fail
- Audio/visual effects need special handling during rollback

### 1.3 Delay-Based Netcode

Simplest approach: wait for all inputs before advancing simulation.

**Pros:** Simple, deterministic, no rollbacks needed
**Cons:** Noticeable input delay, poor experience on high-latency connections

### 1.4 Hybrid Approaches

Many modern games combine techniques:
- Server-authoritative for critical state (health, score, win conditions)
- Client-authoritative for movement (with server validation)
- Rollback for local player, interpolation for remote players

---

## 2. What Ninja Game Already Has

The codebase has **extensive networking infrastructure** already implemented (~60-70% complete).

### 2.1 Fully Implemented

| Component | File | Status |
|-----------|------|--------|
| **State Serialization** | `scripts/snapshot.py` | Complete - SimulationSnapshot captures tick, RNG, players, enemies, projectiles |
| **Deterministic RNG** | `scripts/rng_service.py` | Complete - Singleton with state serialization |
| **Replay System** | `scripts/replay.py` | Advanced - True re-simulation with input playback + snapshot correction |
| **Delta Compression** | `scripts/network/delta.py` | MVP - compute_delta/apply_delta for bandwidth optimization |
| **Interpolation** | `scripts/network/interpolation.py` | Production ready - SnapshotBuffer + interpolate_entity (~1.87µs/entity) |
| **Message Protocol** | `scripts/network/messages.py` | Basic - InputMessage, SnapshotMessage, AckMessage |
| **Rollback Buffer** | `scripts/rollback_buffer.py` | Framework - 600-frame ring buffer for reconciliation |

### 2.2 Partially Implemented / Stubbed

| Component | File | Status |
|-----------|------|--------|
| **NetSync Service** | `scripts/network/netsync_service.py` | Loopback only - No real transport |
| **Prediction Service** | `scripts/prediction_service.py` | Stubbed - `apply_input()` is `pass` |

### 2.3 Missing / Gaps

| Component | Impact |
|-----------|--------|
| **Real Network Transport** | Critical - No TCP/UDP implementation |
| **Global Tick Counter** | Critical - `game.tick` missing, snapshots use `tick=0` |
| **Entity ID System** | High - Entities lack unique IDs for network sync |
| **Authority/Ownership Model** | High - No concept of who controls what |
| **Input Timestamps** | Medium - Inputs are just string lists, no timing |
| **Connection State Machine** | Medium - No handshake, keep-alive, disconnect handling |

---

## 3. Recommended Approach

### 3.1 Architecture Decision: **Server-Authoritative with Client Prediction**

**Rationale:**
1. **Existing Infrastructure** - Snapshot/interpolation systems align with this model
2. **Cheat Prevention** - Server validates all state changes
3. **Scalability** - Can extend to 2+ players easily
4. **Complexity Balance** - Simpler than full rollback, better than pure delay-based
5. **Ghost System Reuse** - Existing GhostPlayer rendering works for remote players

### 3.2 High-Level Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                            SERVER                                    │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────────┐ │
│  │ Input Queue  │→ │ Game Simulation │→ │ Snapshot Broadcaster   │ │
│  │ (per client) │  │ (authoritative) │  │ (delta compressed)     │ │
│  └──────────────┘  └─────────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
         ↑                                          │
         │ InputMessage                             │ SnapshotMessage
         │ (tick, inputs)                           │ (tick, delta/full)
         │                                          ↓
┌─────────────────────────────────────────────────────────────────────┐
│                            CLIENT                                    │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────────┐ │
│  │ Local Input  │→ │ Prediction      │→ │ Renderer               │ │
│  │ + Send       │  │ + Reconciliation│  │ (interpolate remotes)  │ │
│  └──────────────┘  └─────────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 Tick Synchronization

- Server runs at fixed 60 Hz (16.67ms per tick)
- Clients send inputs tagged with estimated server tick
- Server broadcasts snapshots at 10-20 Hz (every 3-6 ticks)
- Clients interpolate between received snapshots
- Local player: predicted ahead, reconciled on server response

### 3.4 Network Protocol

**Transport:** UDP with reliability layer for critical messages

**Messages:**
```
Client → Server:
  - InputMessage { tick: u32, inputs: [string], timestamp: f64 }
  - PingMessage { client_time: f64 }

Server → Client:
  - SnapshotMessage { tick: u32, snapshot: delta | full }
  - PongMessage { client_time: f64, server_time: f64 }
  - PlayerJoinedMessage { player_id: u32, spawn_pos: [x, y] }
  - PlayerLeftMessage { player_id: u32 }
```

---

## 4. Technical Design

### 4.1 Game State Extensions

**Add to Game class:**
```python
class Game:
    tick: int = 0  # Global simulation tick counter
    players: dict[int, Player] = {}  # player_id -> Player
    local_player_id: int | None = None  # Which player we control
    is_server: bool = False
    is_client: bool = False
```

**Extend EntitySnapshot:**
```python
@dataclass
class EntitySnapshot:
    id: int  # Unique entity ID
    owner_id: int | None  # Player who controls this entity
    # ... existing fields
```

### 4.2 Network Transport Layer

```python
# scripts/network/transport.py
class UDPTransport(Transport):
    def __init__(self, host: str, port: int):
        self.socket = socket.socket(AF_INET, SOCK_DGRAM)
        self.socket.setblocking(False)

    def send(self, message: Message, address: tuple[str, int]) -> None:
        data = json.dumps(message.to_dict()).encode()
        self.socket.sendto(data, address)

    def receive(self) -> tuple[Message, tuple[str, int]] | None:
        try:
            data, addr = self.socket.recvfrom(65535)
            return Message.from_dict(json.loads(data)), addr
        except BlockingIOError:
            return None
```

### 4.3 Server Loop

```python
class GameServer:
    def __init__(self, port: int):
        self.transport = UDPTransport("0.0.0.0", port)
        self.game = Game(is_server=True)
        self.clients: dict[tuple[str, int], ClientState] = {}
        self.last_snapshot_tick = 0

    def update(self):
        # 1. Receive all pending inputs
        while msg := self.transport.receive():
            self.handle_message(msg)

        # 2. Apply inputs and advance simulation
        self.game.tick += 1
        for client in self.clients.values():
            inputs = client.input_buffer.get(self.game.tick, [])
            self.apply_inputs(client.player_id, inputs)
        self.game.update()

        # 3. Broadcast snapshot (every N ticks)
        if self.game.tick - self.last_snapshot_tick >= SNAPSHOT_INTERVAL:
            self.broadcast_snapshot()
            self.last_snapshot_tick = self.game.tick
```

### 4.4 Client Loop

```python
class GameClient:
    def __init__(self, server_addr: tuple[str, int]):
        self.transport = UDPTransport("0.0.0.0", 0)
        self.server_addr = server_addr
        self.game = Game(is_client=True)
        self.snapshot_buffer = SnapshotBuffer(max_size=20)
        self.pending_inputs: list[tuple[int, list[str]]] = []

    def update(self, local_inputs: list[str]):
        # 1. Send local inputs to server
        self.send_input(self.estimated_server_tick, local_inputs)
        self.pending_inputs.append((self.estimated_server_tick, local_inputs))

        # 2. Apply local inputs immediately (prediction)
        self.apply_local_inputs(local_inputs)

        # 3. Receive and process server snapshots
        while msg := self.transport.receive():
            if isinstance(msg, SnapshotMessage):
                self.reconcile(msg)

        # 4. Interpolate remote players for rendering
        self.interpolate_remote_players()
```

### 4.5 Reconciliation Flow

```python
def reconcile(self, server_snapshot: SnapshotMessage):
    # 1. Find our player in server snapshot
    server_player = server_snapshot.get_player(self.local_player_id)
    local_player = self.game.player

    # 2. Check for mismatch
    if self.state_differs(local_player, server_player):
        # 3. Restore to server state
        self.restore_player_state(server_player)

        # 4. Replay pending inputs from that tick onwards
        for tick, inputs in self.pending_inputs:
            if tick > server_snapshot.tick:
                self.apply_local_inputs(inputs)

    # 5. Discard acknowledged inputs
    self.pending_inputs = [
        (t, i) for t, i in self.pending_inputs
        if t > server_snapshot.tick
    ]
```

### 4.6 Remote Player Rendering

Reuse existing interpolation infrastructure:

```python
def interpolate_remote_players(self):
    render_tick = self.server_tick - INTERPOLATION_DELAY

    for player_id, buffer in self.remote_player_buffers.items():
        prev, nxt, t = buffer.get_surrounding_snapshots(render_tick)
        if prev and nxt:
            interpolated = interpolate_entity(prev, nxt, t)
            self.render_remote_player(player_id, interpolated)
```

---

## 5. Integration Points

### 5.1 StateManager Integration

Add new states:
- `LobbyState` - Server browser, create/join game
- `MultiplayerGameState` - Extends GameState for networked play

```python
class MultiplayerGameState(GameState):
    def __init__(self, network_role: str, server_addr: str = None):
        super().__init__()
        if network_role == "server":
            self.network = GameServer(port=7777)
        else:
            self.network = GameClient(server_addr)

    def update(self, dt):
        self.network.update()
        super().update(dt)
```

### 5.2 Input Router Integration

Extend to capture inputs for network transmission:

```python
class NetworkedInputRouter(InputRouter):
    def process(self, events, state_name) -> tuple[list[str], list[str]]:
        actions = super().process(events, state_name)
        # Separate local actions from network-relevant inputs
        network_inputs = [a for a in actions if a in NETWORKED_ACTIONS]
        return actions, network_inputs
```

### 5.3 Renderer Integration

Distinguish local vs remote players:

```python
def render_players(self, game):
    # Render remote players (interpolated, slightly transparent)
    for player_id, state in game.remote_players.items():
        self.render_entity(state, alpha=200, tint=(100, 100, 255))

    # Render local player (predicted, full opacity)
    self.render_entity(game.player, alpha=255)
```

### 5.4 Audio Integration

Only play sounds for local events:

```python
def play_sound(self, name: str, is_local: bool = True):
    if is_local or self.is_server:
        self.audio_service.play(name)
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

- [ ] Add `game.tick` counter to Game class
- [ ] Add unique IDs to all entities
- [ ] Implement `UDPTransport` class
- [ ] Add connection handshake protocol
- [ ] Create `LobbyState` for server browser

### Phase 2: Server Implementation (Week 2-3)

- [ ] Implement `GameServer` class
- [ ] Server-side input queue and processing
- [ ] Snapshot broadcasting (delta compressed)
- [ ] Player join/leave handling
- [ ] Basic cheat validation

### Phase 3: Client Implementation (Week 3-4)

- [ ] Implement `GameClient` class
- [ ] Client-side prediction
- [ ] Server reconciliation
- [ ] Remote player interpolation
- [ ] Connection state machine

### Phase 4: Integration (Week 4-5)

- [ ] Create `MultiplayerGameState`
- [ ] Integrate with existing StateManager
- [ ] UI for hosting/joining games
- [ ] Extend renderer for remote players
- [ ] Audio handling for networked events

### Phase 5: Polish & Testing (Week 5-6)

- [ ] Latency simulation testing
- [ ] Packet loss handling
- [ ] Bandwidth optimization
- [ ] Reconnection logic
- [ ] Performance profiling

---

## 7. Technical Considerations

### 7.1 Bandwidth Budget

**Target:** ~50 KB/s per client

| Data | Size | Frequency | Bandwidth |
|------|------|-----------|-----------|
| Input (client→server) | ~50 bytes | 60 Hz | 3 KB/s |
| Snapshot delta | ~200-500 bytes | 10 Hz | 2-5 KB/s |
| Full snapshot (resync) | ~2 KB | On demand | Variable |

### 7.2 Latency Budget

**Target:** 150ms round-trip playable, 250ms degraded

| Component | Budget |
|-----------|--------|
| Network RTT | ~50-100ms |
| Server processing | ~5ms |
| Client prediction | 0ms (instant) |
| Interpolation delay | 2-3 ticks (~33-50ms) |

### 7.3 Determinism Checklist

- [x] RNG is seeded and state-serializable
- [x] Fixed timestep simulation (60 Hz)
- [ ] Floating-point determinism (may need fixed-point for positions)
- [x] Input-driven updates only
- [ ] No frame-rate dependent logic

### 7.4 Security Considerations

- Server validates all state changes
- Rate-limit input messages per client
- Validate input sequences (no impossible actions)
- Sanitize player names and chat messages
- Consider anti-cheat for competitive play

---

## 8. Alternative Approaches Considered

### 8.1 Pure Rollback (GGPO-style)

**Why not chosen:**
- Higher complexity
- CPU-intensive (need to resimulate up to 15 frames in 16ms)
- Existing snapshot system better fits server-authoritative model
- 2-4 player platformer doesn't need fighting-game precision

### 8.2 Peer-to-Peer

**Why not chosen:**
- NAT traversal complexity
- No clear authority (harder cheat prevention)
- Existing architecture assumes single authoritative simulation

### 8.3 Lockstep

**Why not chosen:**
- Poor experience on high-latency connections
- Requires all players to wait for slowest
- Not suitable for action platformer

---

## 9. Open Questions

1. **Host Migration:** If host disconnects, can another player become server?
2. **Spectator Mode:** Should observers receive full state or limited view?
3. **Replay Recording:** Record multiplayer games for later viewing?
4. **Matchmaking:** Simple lobby or skill-based matching?
5. **Game Modes:** Co-op vs competitive vs race?

---

## 10. Resources

### Foundational Reading
- [Gabriel Gambetta - Fast-Paced Multiplayer](https://www.gabrielgambetta.com/client-server-game-architecture.html) - Client-side prediction, entity interpolation
- [Glenn Fiedler - Gaffer on Games](https://gafferongames.com/) - UDP protocol, game networking fundamentals
- [GGPO SDK](https://github.com/pond3r/ggpo) - Reference rollback implementation

### Curated Collections
- [Awesome Game Networking](https://github.com/rumaniel/Awesome-Game-Networking)
- [Multiplayer Networking Resources](https://multiplayernetworking.com/)

### Tutorials
- [Jimmy's Blog - Rollback Networking](https://outof.pizza/posts/rollback/)
- [SnapNet - Netcode Architectures](https://www.snapnet.dev/blog/netcode-architectures-part-2-rollback/)

---

## 11. Success Criteria

**MVP (Minimum Viable Product):**
- [ ] 2 players can connect over LAN
- [ ] Both players see each other moving in real-time
- [ ] Shooting and damage sync correctly
- [ ] Level completion triggers for both players

**Full Release:**
- [ ] Internet play with acceptable latency (<200ms)
- [ ] Graceful disconnect handling
- [ ] Multiple game modes (co-op, race)
- [ ] In-game server browser
- [ ] Replay recording for multiplayer games
