# Online Connectivity Brainstorm

**Date:** 2026-10-23
**Status:** Brainstorm, direction agreed; nothing implemented yet

Today a friend joins by typing the host's IP address, and over the internet both players first need Tailscale. The goal: download the game and play online with friends, with no address typing, no extra tool, and no dedicated server to pay for or administer. Companion to [online-benchmark-brainstorm.md](online-benchmark-brainstorm.md), which covers measuring the online mode.

---

## 1. The Question

> könnte man nicht eine user freundlichere ux variante für den online modus bauen? immer die addresse des mitspielers einzugeben bei jedem starten des online spiels ist schon echt ein bisschen nervig. [...] ich weis das wir keinen dedizierten server für das spiel haben - und das will ich auch erstmal garnicht (kostet nur geld und muss adminestriert werden) [...] auch das wir tailscale erst runterladen müssen ist ein zusätzlicher schritt der reibung mitbringt. [...] optimal wäre: man läd das spiel runter und kann mit seinen freunden über online zocken

Couldn't the online mode have a friendlier UX? Typing the other player's address every time is annoying. Could it work with player names or aliases? Or can you only play over a fixed server? There is no dedicated server, and none is wanted (costs money, needs administration). Having to install Tailscale first adds friction too. Ideal: download the game and play online with friends.

## 2. Decisions

- **A serverless rendezvous is fine.** It runs as a Cloudflare Worker under the existing Cloudflare account; no machine to administer, free tier.
- **No dedicated game server.** Game traffic stays peer-to-peer: friend directly to the host's machine.
- **Tailscale becomes the fallback**, not the default.
- **Setup to plan for:** both players on MacBooks behind a Fritz!Box at home, both lines with IPv6 (this machine has a global IPv6 address, checked locally).

## 3. Two Separate Problems

1. **Finding:** who is hosting right now, and at which address? Home IPs change, so a fixed address does not work.
2. **Getting through:** both players sit behind a home router (NAT and firewall) that drops packets from outside unless something went out first.

## 4. Options Considered

| Approach | Examples | Cost / effort | Verdict |
| --- | --- | --- | --- |
| Dedicated server | most shooters | money and administration | ruled out |
| Platform service | Steam (friends, invites, Valve relays), Epic Online Services | Steam: 100 $ per app plus integration; EOS: free, but a C SDK to bind from Python | only if the game is ever released |
| VPN tool | Tailscale, formerly Hamachi | extra install per player | fallback |
| Automatic port mapping (UPnP) | older PC games | often disabled; no IPv4 mapping behind DS-Lite | partial at best |
| **Rendezvous + hole punching** | the technique under Tailscale, WebRTC (ICE), Parsec, Steam P2P | tiny serverless service, free tier | **chosen** |

Without any rendezvous, both players would have to exchange codes in both directions on every start (IPs change, and both sides must send first). That is worse than today.

## 5. Design: Rendezvous + Hole Punching

Routers let replies to outgoing packets through. If both sides send to each other at the same time, each router treats the other side's packet as a reply: the hole is "punched", and from then on the game runs directly from home to home, exactly like on the LAN today. The rendezvous only exchanges addresses; it never sees game traffic, only a few hundred bytes per session.

### 5.1 Candidates

Each side collects every address it might be reachable at (the ICE idea from WebRTC, kept minimal):

- **IPv6:** the global address, learned via STUN over IPv6 so it is the source address the socket really uses (see 7.2).
- **Public IPv4 and port:** learned via STUN over IPv4 from the game's own UDP socket. The Worker cannot provide this: it only sees HTTPS requests from a different socket and port, and it cannot receive UDP. Public STUN servers: `stun.cloudflare.com:3478`, with Google's `stun.l.google.com:19302` as backup (verify both, including IPv6, when building).
- **LAN IPv4:** so two players on the same network connect locally.

A STUN binding request is a 20-byte UDP packet; a client that parses `XOR-MAPPED-ADDRESS` is ~60 lines of Python, no dependency.

### 5.2 Flow

```
Host: server.py, UDP [::]:7777        Worker (rendezvous)            Friend: client UDP socket
  STUN (v4 + v6) -> candidates
  POST /presence {code, token, candidates, version, level, allowed}
       (refresh every ~20 s, record expires after ~60 s)
                                                                     GET /presence?codes=TOM-7F3K
                                                                       -> "hosting level 3" + host candidates
                                                                     STUN (v4 + v6) -> candidates
                                                                     POST /join {to, from, token, candidates}
  GET /joins (poll every ~1 s) <- friend candidates
  punch -> all friend candidates                                     punch -> all host candidates
  first pair that answers wins  <=========== direct UDP ===========>
                                                                     connect_request (existing protocol)
```

- **The server process punches, not the host's game client.** Its socket (port 7777) is the hole. The host's own client keeps talking to the local server over loopback, unchanged.
- **Punching:** small `punch` messages to every candidate of the other side every ~50-100 ms for up to ~5-10 s. The first candidate that answers wins; within a short window prefer LAN over IPv6 over public IPv4.
- **Worker state:** a Durable Object keeps presence and join requests consistent (KV is eventually consistent, too slow for a handshake). Durable Objects are available on the Workers Free plan; verify limits when building. Polling first; a WebSocket for instant invites can come later.
- **Dual-stack transport:** `UDPTransport` binds `0.0.0.0` today. It needs an `AF_INET6` socket on `::` with `IPV6_V6ONLY` off, and address normalization: IPv6 `recvfrom()` returns 4-tuples, IPv4 peers show up as `::ffff:a.b.c.d`, and `ClientState` is keyed by address.

## 6. UX

**Once:** the game shows the player's friend code, e.g. `TOM-7F3K`. Send it once by chat; the friend adds it.

**Every time after that:**

```
Multiplayer
  > Host online
    Friends
      Max      ● online, hosting level 3   [Join]
      Lisa     ○ offline
    Add friend
    Connect directly (IP)   <- fallback, as today (remembers the last address)
```

- Joining shows its progress: "Connecting... (IPv6)", then "Connected" or a clear failure with the fallback offered.
- The friends list shows a version mismatch before joining ("Max has another game version").
- Later: a room code instead of a friends list (like Among Us), and invites pushed into the friend's menu.

## 7. Where It Can Fail

### 7.1 NAT Types

Hole punching works on most home connections, not all. The hard case is DS-Lite/CGNAT (no own IPv4) combined with a strict NAT on the other side. IPv6 is the way out: no NAT, only a stateful firewall, and simultaneous sending works the same way. With IPv6 on both lines, the hardest case is covered for this setup. If no path answers: fall back to "Connect directly" (Tailscale). A relay as the last resort costs bandwidth and therefore money; only build it if a real case needs it (Cloudflare also offers a managed TURN service; check pricing then).

### 7.2 Mac and Fritz!Box Specifics

- **Fritz!Box IPv6 firewall:** stateful, drops unsolicited inbound packets, lets replies through; punching needs no port forwarding. Fritz!Box IPv4 NAT is usually punching-friendly; behind DS-Lite, IPv4 goes through the provider's CGNAT and is less predictable, so IPv6 is the primary path.
- **macOS temporary IPv6 addresses:** macOS sends from a rotating privacy address. If the advertised address differs from the one the socket sends from, the firewall state on both sides does not match. Learn the address via STUN over IPv6 and pin it for the session (bind the IPv6 socket to it), so the address the peer sees never changes mid-game.
- **macOS application firewall:** the "accept incoming connections" prompt on first host (see [multiplayer.md](multiplayer.md)) probably stays; verify whether it also appears with punched flows.
- **Keepalive:** the router forgets idle UDP mappings. Heartbeats (1/s) keep them during play; while waiting for a join, the presence refresh re-runs STUN.

### 7.3 Packet Size on IPv6

IPv6 routers never fragment, and fragmented IPv6 packets are dropped noticeably often on the internet (RFC 7872). This makes the oversized snapshots (section 6a of the benchmark brainstorm) even more important to fix on the direct IPv6 path.

## 8. Security and Privacy (Minimal v1)

- **Identity:** on first start each installation generates a random ID and a secret token. The friend code is a short readable form of the ID. The Worker stores the token hash on first registration (trust on first use), so only the owner can update its own presence.
- **Friends only:** the host publishes the friend codes it allows; the Worker only forwards joins from those codes. The server accepts `connect_request` only from loopback and from addresses it punched with.
- **Data:** presence records hold IP addresses and expire after ~60 s. Rate limiting per code.
- **Game traffic:** unencrypted JSON over UDP, as today. Fine among friends; revisit if the game is ever released.

## 9. Metrics for the Benchmark

Added to the online benchmark (layer "experience"):

- connection success rate
- setup time (click on Join until in game)
- chosen path (LAN / IPv6 / IPv4) and punch time
- disconnects and reconnects per session

## 10. Order of Work

Fits into the plan of the benchmark brainstorm (section 10 there):

1. **`NetStats` core and dev HUD** first, as agreed, so the first real evening is already measured.
2. **Quick wins:** protocol version check in the connect handshake; "Connect directly" remembers the last address.
3. **Dual-stack transport, STUN client, candidates.** Testable locally (two processes, host candidates) and on the LAN.
4. **Worker** (Durable Object; code in the repo, deployed with `wrangler` under the existing Cloudflare account, `wrangler login` once), identity and friend codes, presence, join and punching.
5. **Menu UX:** friends list, add friend, hosting status, join progress, fallback.
6. **First real test:** the friend at home, or a phone hotspot (German mobile networks put IPv4 behind CGNAT and provide IPv6, a good hard case). This is also the first real evening that calibrates the benchmark.

Later, only if needed: instant invites over WebSocket, a relay, Steam.

## 11. Open Questions

- **Friend code format:** random ID (simple) or derived from a key pair (allows signed requests)? Random ID plus token is enough for v1.
- **Polling or WebSocket** for presence and joins? Start with polling.
- **Separate LAN discovery** without the Worker (offline play on the same network)? Low priority; LAN candidates already cover the online case.
