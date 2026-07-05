"""UDP network-impairment proxy for multiplayer testing (real processes).

Sits between a game client and the dedicated server and applies
WLAN-like impairments to every packet in both directions:

- Base one-way delay (--delay-ms)
- Random jitter, uniform 0..jitter added per packet (--jitter-ms)
- Random packet loss (--loss, probability per packet)
- Periodic "doze" windows emulating Wi-Fi power-save/aggregation:
  server->client packets arriving during a doze window are held and
  released together at its end (--doze-ms / --doze-period-ms)

Multiple clients are supported (per-client NAT table). Per-second
forwarding stats are printed and optionally written as JSONL.

Usage:
    python tools/mp_netem.py --listen-port 21999 --server-port 21777 \
        --delay-ms 15 --jitter-ms 25 --loss 0.02 \
        --doze-ms 80 --doze-period-ms 300 --seed 7
"""

from __future__ import annotations

import argparse
import heapq
import itertools
import json
import random
import select
import socket
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="UDP impairment proxy")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--delay-ms", type=float, default=0.0, help="Base one-way delay per direction")
    parser.add_argument("--jitter-ms", type=float, default=0.0, help="Uniform random extra delay 0..jitter")
    parser.add_argument("--loss", type=float, default=0.0, help="Packet loss probability (0..1)")
    parser.add_argument("--doze-ms", type=float, default=0.0, help="Server->client hold window length")
    parser.add_argument("--doze-period-ms", type=float, default=0.0, help="Doze window repeats every this many ms")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--stats-file", default=None, help="Write per-second stats as JSONL")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    server_addr = (args.server_host, args.server_port)

    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen_sock.bind((args.listen_host, args.listen_port))
    listen_sock.setblocking(False)

    # NAT table: one server-facing socket per client address
    client_to_sock: dict[tuple[str, int], socket.socket] = {}
    sock_to_client: dict[socket.socket, tuple[str, int]] = {}

    # Delivery queue: (due_time, seq, out_sock, dest_addr, data)
    queue: list = []
    seq = itertools.count()

    stats = {"c2s": 0, "s2c": 0, "dropped": 0, "held": 0}
    delays_ms: list[float] = []
    stats_fh = open(args.stats_file, "a") if args.stats_file else None
    last_report = time.perf_counter()
    start = time.perf_counter()

    def doze_release_time(now: float) -> float | None:
        """If now falls inside a doze window, return the window's end."""
        if args.doze_ms <= 0 or args.doze_period_ms <= 0:
            return None
        phase = ((now - start) * 1000.0) % args.doze_period_ms
        if phase < args.doze_ms:
            return now + (args.doze_ms - phase) / 1000.0
        return None

    def schedule(out_sock: socket.socket, dest: tuple[str, int], data: bytes, s2c: bool) -> None:
        now = time.perf_counter()
        if rng.random() < args.loss:
            stats["dropped"] += 1
            return
        delay = args.delay_ms / 1000.0
        if args.jitter_ms > 0:
            delay += rng.uniform(0, args.jitter_ms) / 1000.0
        due = now + delay
        if s2c:
            release = doze_release_time(due)
            if release is not None:
                due = release
                stats["held"] += 1
        delays_ms.append((due - now) * 1000.0)
        stats["s2c" if s2c else "c2s"] += 1
        heapq.heappush(queue, (due, next(seq), out_sock, dest, data))

    print(
        f"[netem] {args.listen_host}:{args.listen_port} -> {args.server_host}:{args.server_port} "
        f"delay={args.delay_ms}ms jitter={args.jitter_ms}ms loss={args.loss} "
        f"doze={args.doze_ms}/{args.doze_period_ms}ms",
        flush=True,
    )

    try:
        while True:
            now = time.perf_counter()
            timeout = 0.001
            if queue:
                timeout = max(0.0, min(timeout, queue[0][0] - now))
            readable, _, _ = select.select([listen_sock, *sock_to_client], [], [], timeout)

            for sock in readable:
                try:
                    data, addr = sock.recvfrom(65535)
                except OSError:
                    continue
                if sock is listen_sock:
                    # client -> server
                    relay = client_to_sock.get(addr)
                    if relay is None:
                        relay = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        relay.bind(("127.0.0.1", 0))
                        relay.setblocking(False)
                        client_to_sock[addr] = relay
                        sock_to_client[relay] = addr
                        print(f"[netem] new client {addr} via {relay.getsockname()}", flush=True)
                    schedule(relay, server_addr, data, s2c=False)
                else:
                    # server -> client
                    schedule(listen_sock, sock_to_client[sock], data, s2c=True)

            now = time.perf_counter()
            while queue and queue[0][0] <= now:
                _, _, out_sock, dest, data = heapq.heappop(queue)
                try:
                    out_sock.sendto(data, dest)
                except OSError:
                    pass

            if now - last_report >= 1.0:
                sample = {
                    "t": time.time(),
                    **stats,
                    "queued": len(queue),
                    "delay_ms_max": round(max(delays_ms), 2) if delays_ms else 0,
                }
                if stats_fh:
                    stats_fh.write(json.dumps(sample) + "\n")
                    stats_fh.flush()
                print(f"[netem] {sample}", flush=True)
                stats.update({"c2s": 0, "s2c": 0, "dropped": 0, "held": 0})
                delays_ms.clear()
                last_report = now
    except KeyboardInterrupt:
        pass
    finally:
        listen_sock.close()
        for s in sock_to_client:
            s.close()
        if stats_fh:
            stats_fh.close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
