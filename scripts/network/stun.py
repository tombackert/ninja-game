"""Minimal STUN client (RFC 5389): the public address of a UDP socket.

A binding request is 20 bytes; the STUN server answers with the source
address and port it saw (XOR-MAPPED-ADDRESS). Sent from the game's own
socket, that is the address a friend on the internet can reach the socket
at, once the router lets the friend's packets in (hole punching, see
docs/online-connectivity-brainstorm.md). Over IPv6 it is the address the
socket really sends from, which on macOS is a rotating temporary address,
not the one ``ifconfig`` lists first.

The transport hands non-game packets to ``StunProbe.on_packet``; the probe
re-sends its requests until every server family has answered or it gives
up.
"""

from __future__ import annotations

import os
import socket
import struct
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_SUCCESS = 0x0101
ATTR_MAPPED_ADDRESS = 0x0001
ATTR_XOR_MAPPED_ADDRESS = 0x0020

# Public STUN servers; the second one is the backup
STUN_SERVERS: List[Tuple[str, int]] = [("stun.cloudflare.com", 3478), ("stun.l.google.com", 19302)]
RESEND_S = 0.5
GIVE_UP_S = 4.0

Address = Tuple[str, int]


def binding_request() -> Tuple[bytes, bytes]:
    """A binding request and its 12-byte transaction id."""
    tid = os.urandom(12)
    return struct.pack("!HHI", BINDING_REQUEST, 0, MAGIC_COOKIE) + tid, tid


def is_stun(data: bytes) -> bool:
    """STUN messages start with two zero bits and carry the magic cookie."""
    return len(data) >= 20 and data[0] < 0x40 and struct.unpack_from("!I", data, 4)[0] == MAGIC_COOKIE


def parse_response(data: bytes) -> Optional[Tuple[bytes, Address]]:
    """(transaction id, mapped address) of a binding success response, else None."""
    if not is_stun(data):
        return None
    msg_type, length = struct.unpack_from("!HH", data, 0)
    if msg_type != BINDING_SUCCESS:
        return None
    tid = data[8:20]
    pos, end = 20, min(len(data), 20 + length)
    mapped: Optional[Address] = None
    while pos + 4 <= end:
        attr, size = struct.unpack_from("!HH", data, pos)
        value = data[pos + 4 : pos + 4 + size]
        if attr == ATTR_XOR_MAPPED_ADDRESS:
            addr = _decode_address(value, data[4:20])
            if addr is not None:
                return tid, addr
        elif attr == ATTR_MAPPED_ADDRESS and mapped is None:
            mapped = _decode_address(value, None)
        pos += 4 + size + (-size % 4)  # attributes are padded to 4 bytes
    return (tid, mapped) if mapped is not None else None


def _decode_address(value: bytes, xor_key: Optional[bytes]) -> Optional[Address]:
    """Decode a (XOR-)MAPPED-ADDRESS value; the XOR key is cookie + transaction id."""
    if len(value) < 8:
        return None
    family = value[1]
    port = struct.unpack_from("!H", value, 2)[0]
    if family == 0x01:
        raw, af = value[4:8], socket.AF_INET
    elif family == 0x02 and len(value) >= 20:
        raw, af = value[4:20], socket.AF_INET6
    else:
        return None
    if xor_key is not None:
        port ^= MAGIC_COOKIE >> 16
        raw = bytes(a ^ b for a, b in zip(raw, xor_key))
    return socket.inet_ntop(af, raw), port


def encode_response(tid: bytes, addr: Address) -> bytes:
    """A binding success response with XOR-MAPPED-ADDRESS (for tests and local STUN)."""
    host, port = addr
    if ":" in host:
        family, raw = 0x02, socket.inet_pton(socket.AF_INET6, host)
    else:
        family, raw = 0x01, socket.inet_pton(socket.AF_INET, host)
    key = struct.pack("!I", MAGIC_COOKIE) + tid
    xored = bytes(a ^ b for a, b in zip(raw, key))
    value = struct.pack("!BBH", 0, family, port ^ (MAGIC_COOKIE >> 16)) + xored
    attr = struct.pack("!HH", ATTR_XOR_MAPPED_ADDRESS, len(value)) + value
    return struct.pack("!HHI", BINDING_SUCCESS, len(attr), MAGIC_COOKIE) + tid + attr


def resolve(servers: List[Tuple[str, int]]) -> Dict[str, List[Address]]:
    """IPv4 and IPv6 addresses of the STUN servers (blocking DNS)."""
    out: Dict[str, List[Address]] = {"v4": [], "v6": []}
    for host, port in servers:
        for family, key in ((socket.AF_INET, "v4"), (socket.AF_INET6, "v6")):
            try:
                infos = socket.getaddrinfo(host, port, family, socket.SOCK_DGRAM)
            except OSError:
                continue
            for info in infos[:1]:
                out[key].append((info[4][0], info[4][1]))
    return out


class StunProbe:
    """Learns the socket's public IPv4 and IPv6 address, without blocking the caller.

    DNS runs in a thread; requests go out through ``send`` (the game's own
    socket) from ``update()``, answers come in through ``on_packet``.
    ``results`` maps "v4"/"v6" to the mapped address once known.
    """

    def __init__(
        self,
        send: Callable[[bytes, Address], object],
        servers: Optional[List[Tuple[str, int]]] = None,
        resolver: Callable[[List[Tuple[str, int]]], Dict[str, List[Address]]] = resolve,
    ) -> None:
        self._send = send
        self._servers = list(servers if servers is not None else STUN_SERVERS)
        self._resolver = resolver
        self._targets: Optional[Dict[str, List[Address]]] = None
        self._pending: Dict[bytes, str] = {}  # transaction id -> family
        self._last_send = 0.0
        self._started = 0.0
        self.results: Dict[str, Address] = {}

    def start(self) -> None:
        """Resolve the servers in the background; ``update()`` sends once that is done."""
        self._started = time.monotonic()
        self._targets = None
        self._pending.clear()
        self.results = {}

        def run() -> None:
            self._targets = self._resolver(self._servers)

        threading.Thread(target=run, name="stun-dns", daemon=True).start()

    @property
    def started(self) -> bool:
        return bool(self._started)

    @property
    def done(self) -> bool:
        """Every family answered, or the probe gave up."""
        if not self._started:
            return False
        if self._targets is not None and all(f in self.results for f, addrs in self._targets.items() if addrs):
            return True
        return time.monotonic() - self._started > GIVE_UP_S

    def update(self, now: Optional[float] = None) -> None:
        """(Re-)send binding requests for the families still unanswered."""
        now = time.monotonic() if now is None else now
        if self._targets is None or self.done or now - self._last_send < RESEND_S:
            return
        self._last_send = now
        for family, addrs in self._targets.items():
            if family in self.results:
                continue
            for addr in addrs:
                packet, tid = binding_request()
                self._pending[tid] = family
                self._send(packet, addr)

    def on_packet(self, data: bytes, addr: Address) -> bool:
        """Consume a STUN answer; False if the packet is not one of ours."""
        parsed = parse_response(data)
        if parsed is None:
            return False
        tid, mapped = parsed
        family = self._pending.pop(tid, None)
        if family is None:
            return True  # a late answer to an older request
        self.results.setdefault(family, mapped)
        return True


__all__ = [
    "StunProbe",
    "binding_request",
    "encode_response",
    "is_stun",
    "parse_response",
    "resolve",
    "STUN_SERVERS",
]
