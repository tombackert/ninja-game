"""Online play by friend code: identity, rendezvous, candidates, hole punching.

See docs/online-connectivity-brainstorm.md. Each installation has a friend
code (``Identity``, stored in data/online.json). The host's server process
registers its presence and candidate addresses with the rendezvous (a
Cloudflare Worker, ``rendezvous/``) every few seconds (``HostOnline``); a
friend who knows the code sends its own candidates through the rendezvous
and gets the host's back (``JoinOnline``). Then both sides send ``punch``
packets to all of the other's candidates at once: each router takes the
other side's packets for replies, and the first candidate that answers is
the direct path the game uses, exactly like on the LAN.

Candidates are the addresses a socket may be reached at: the LAN IPv4
address, the IPv6 address and the public IPv4 address with port as STUN
servers saw them, all for the game's own socket.

HTTP calls to the rendezvous run in threads so neither the server's tick
loop nor the game's frames wait for them.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.network.messages import PROTOCOL_VERSION, Message
from scripts.network.stun import StunProbe
from scripts.network.udp_transport import UDPTransport

Address = Tuple[str, int]
Candidate = List[Any]  # [kind, host, port], kind "lan" | "v6" | "v4"

DEFAULT_RENDEZVOUS_URL = "https://ninja-rendezvous.tombackert.workers.dev"
# NINJA_ONLINE_FILE gives a second game on the same machine its own identity (tests)
ONLINE_FILE = os.environ.get("NINJA_ONLINE_FILE", "data/online.json")
# Nothing the pixel font (or a photo of the screen) makes look alike: none
# of 0/O/Q/D, 1/I/L, U/V, and of 2/Z, 5/S, 6/G, 8/B only the digit.
# 23^8 codes, ~36 bits.
CODE_ALPHABET = "23456789ACEFHJKMNPRTWXY"

HOST_POLL_S = 2.0  # presence refresh, and how quickly the host sees a join
PUNCH_INTERVAL_S = 0.1
PUNCH_TIMEOUT_S = 10.0
STUN_REFRESH_S = 30.0  # keeps the router's mapping of the server socket alive
HTTP_TIMEOUT_S = 6.0
KIND_ORDER = {"lan": 0, "v6": 1, "v4": 2}  # preferred path when several answer at once


def rendezvous_url() -> str:
    return os.environ.get("NINJA_RENDEZVOUS_URL", DEFAULT_RENDEZVOUS_URL).rstrip("/")


# --- Identity and friends ---


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def normalize_code(text: str) -> Optional[str]:
    """'k7hm 2xra' -> 'K7HM-2XRA'; None if it cannot be a friend code."""
    raw = "".join(ch for ch in text.upper() if ch.isalnum())
    if len(raw) != 8 or any(ch not in CODE_ALPHABET for ch in raw):
        return None
    return raw[:4] + "-" + raw[4:]


@dataclass
class Identity:
    """This installation's friend code and secret, its friends, the last direct address."""

    code: str
    token: str
    friends: List[Dict[str, str]] = field(default_factory=list)  # [{"code", "name"}]
    last_address: str = ""
    path: str = ""

    @staticmethod
    def load(path: Optional[str] = None) -> "Identity":
        """Read the identity file (default ONLINE_FILE), creating a new code on first use."""
        path = path or ONLINE_FILE
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            code = normalize_code(str(data.get("code", "")))
            token = str(data.get("token", ""))
            if code and len(token) >= 16:
                return Identity(
                    code=code,
                    token=token,
                    friends=[
                        {"code": c, "name": str(fr.get("name", ""))[:24]}
                        for fr in data.get("friends", [])
                        if isinstance(fr, dict) and (c := normalize_code(str(fr.get("code", ""))))
                    ],
                    last_address=str(data.get("last_address", "")),
                    path=path,
                )
        except (OSError, ValueError, TypeError):
            pass
        identity = Identity(code=new_code(), token=secrets.token_hex(16), path=path)
        identity.save()
        return identity

    def save(self) -> None:
        data = {"code": self.code, "token": self.token, "friends": self.friends, "last_address": self.last_address}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def add_friend(self, code: str, name: str = "") -> bool:
        """Add a friend by code (False if invalid, our own, or already there)."""
        code = normalize_code(code) or ""
        if not code or code == self.code or any(f["code"] == code for f in self.friends):
            return False
        self.friends.append({"code": code, "name": name[:24]})
        self.save()
        return True

    def remove_friend(self, code: str) -> None:
        self.friends = [f for f in self.friends if f["code"] != code]
        self.save()

    def set_friend_name(self, code: str, name: str) -> None:
        for f in self.friends:
            if f["code"] == code and name and f["name"] != name[:24]:
                f["name"] = name[:24]
                self.save()


# --- Rendezvous over HTTPS ---


class RendezvousError(Exception):
    """The rendezvous answered with an error (``kind``: offline, forbidden, ...) or not at all."""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(message or kind)
        self.kind = kind


def call_rendezvous(path: str, body: Dict[str, Any], url: Optional[str] = None) -> Dict[str, Any]:
    """POST JSON to the rendezvous (blocking); raises RendezvousError."""
    request = urllib.request.Request(
        (url or rendezvous_url()) + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", "user-agent": "ninja-game"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read().decode("utf-8")).get("error", "")
        except (ValueError, OSError):
            message = ""
        kind = {404: "offline", 403: "forbidden"}.get(e.code, "error")
        raise RendezvousError(kind, message or f"HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RendezvousError("unreachable", str(getattr(e, "reason", e))) from None


class Background:
    """One blocking call in a daemon thread; poll ``done``, then read ``result`` / ``error``."""

    def __init__(self, fn: Callable[..., Any], *args: Any) -> None:
        self.result: Any = None
        self.error: Optional[Exception] = None
        self._done = threading.Event()

        def run() -> None:
            try:
                self.result = fn(*args)
            except Exception as e:  # handed to the caller
                self.error = e
            finally:
                self._done.set()

        threading.Thread(target=run, name="rendezvous", daemon=True).start()

    @property
    def done(self) -> bool:
        return self._done.is_set()


# --- Candidates ---


def local_address(family: int, probe: str) -> Optional[str]:
    """The local address the system would send from towards ``probe`` (no packet is sent)."""
    try:
        s = socket.socket(family, socket.SOCK_DGRAM)
        try:
            s.connect((probe, 9))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def gather_candidates(port: int, stun: Dict[str, Address], ipv6: bool = True) -> List[Candidate]:
    """LAN IPv4, IPv6 and public IPv4 candidates of a socket bound to all interfaces on ``port``."""
    out: List[Candidate] = []
    lan = local_address(socket.AF_INET, "192.0.2.1")
    if lan and not lan.startswith("127."):
        out.append(["lan", lan, port])
    if ipv6:
        if "v6" in stun:
            out.append(["v6", stun["v6"][0], stun["v6"][1]])
        else:
            v6 = local_address(socket.AF_INET6, "2001:db8::1")
            if v6 and not v6.startswith("fe80") and v6 != "::1":
                out.append(["v6", v6, port])
    if "v4" in stun and stun["v4"][0] != lan:
        out.append(["v4", stun["v4"][0], stun["v4"][1]])
    return out


def candidate_addresses(candidates: List[Candidate]) -> List[Tuple[str, Address]]:
    """(kind, address) of well-formed candidates."""
    out = []
    for c in candidates or []:
        if isinstance(c, (list, tuple)) and len(c) == 3 and isinstance(c[1], str) and isinstance(c[2], int):
            out.append((str(c[0]), (c[1], c[2])))
    return out


# --- Punching ---


class Puncher:
    """Sends ``punch`` to every candidate of the other side until one answers.

    Both sides punch at the same time; a ``punch`` that gets through is
    answered with ``punch_ack``. Whatever arrives from a candidate proves
    the path works in that direction, and since we have been sending to it,
    our router lets the replies through too.
    """

    def __init__(self, transport: UDPTransport, candidates: List[Candidate], session: str) -> None:
        self.transport = transport
        self.targets = candidate_addresses(candidates)
        self.session = session
        self.started = time.monotonic()
        self._last_send = 0.0
        self.winner: Optional[Tuple[str, Address]] = None

    @property
    def timed_out(self) -> bool:
        return self.winner is None and time.monotonic() - self.started > PUNCH_TIMEOUT_S

    def update(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        if self.winner is not None or self.timed_out or now - self._last_send < PUNCH_INTERVAL_S:
            return
        self._last_send = now
        for _kind, addr in self.targets:
            self.transport.send(Message(type="punch", payload={"session": self.session}), addr)

    def on_message(self, message: Message, addr: Address) -> bool:
        """Handle punch / punch_ack from the other side; True if it was one."""
        if message.type == "punch":
            self.transport.send(Message(type="punch_ack", payload={"session": self.session}), addr)
        elif message.type != "punch_ack":
            return False
        for kind, target in self.targets:
            if target == addr:
                if self.winner is None or KIND_ORDER.get(kind, 9) < KIND_ORDER.get(self.winner[0], 9):
                    self.winner = (kind, target)
                break
        return True


# --- Host side (server process) ---


class HostOnline:
    """Presence at the rendezvous, join requests, punching, for the host's server.

    Drive it with ``update()`` once per server tick; it answers ``punch``
    packets through ``GameServer.on_punch``.
    """

    def __init__(
        self,
        server: Any,
        identity: Identity,
        name: str,
        level: int,
        url: Optional[str] = None,
        stun_servers: Optional[List[Tuple[str, int]]] = None,
    ) -> None:
        self.server = server
        self.identity = identity
        self.name = name
        self.level = level
        self.url = url or rendezvous_url()
        self.stun = StunProbe(server.transport.send_raw, stun_servers)
        server.transport.raw_handler = self.stun.on_packet
        self.candidates: List[Candidate] = []
        self.punchers: Dict[str, Puncher] = {}  # friend code -> puncher
        self.status = "starting"  # "online" once registered, else the last error
        self._call: Optional[Background] = None
        self._next_poll = 0.0
        self._next_stun = 0.0
        self._gathered = False
        self.events: List[Dict[str, Any]] = []  # for the session log

    def update(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        if now >= self._next_stun:
            self._next_stun = now + STUN_REFRESH_S
            self.stun.start()
            self._gathered = False
        self.stun.update(now)
        if self.stun.done and not self._gathered:
            # The candidates of the last probe stay valid until this one is done
            self._gathered = True
            self.candidates = gather_candidates(
                self.server.transport.port, self.stun.results, self.server.transport.ipv6
            )

        if self._call is not None and self._call.done:
            self._finish_poll(self._call)
            self._call = None
        if self._call is None and now >= self._next_poll and self.candidates:
            self._next_poll = now + HOST_POLL_S
            body = {
                "code": self.identity.code,
                "token": self.identity.token,
                "name": self.name,
                "version": PROTOCOL_VERSION,
                "level": self.level,
                "candidates": self.candidates,
            }
            self._call = Background(call_rendezvous, "/v1/host", body, self.url)

        connected = {c.address for c in self.server.clients.get_all_clients()}
        for code, puncher in list(self.punchers.items()):
            if puncher.timed_out or any(addr in connected for _, addr in puncher.targets):
                del self.punchers[code]
            else:
                puncher.update(now)

    def _finish_poll(self, call: Background) -> None:
        if call.error is not None:
            status = f"rendezvous {getattr(call.error, 'kind', 'error')}: {call.error}"
            if status != self.status:
                self.events.append({"event": "rendezvous_error", "error": status})
            self.status = status
            return
        if self.status != "online":
            self.events.append({"event": "hosting_online", "code": self.identity.code, "candidates": self.candidates})
        self.status = "online"
        for join in call.result.get("joins", []):
            code = join.get("from", "")
            self.punchers[code] = Puncher(self.server.transport, join.get("candidates", []), code)
            self.events.append(
                {
                    "event": "join_request",
                    "from": code,
                    "name": join.get("name", ""),
                    "candidates": join.get("candidates"),
                }
            )

    def on_punch(self, message: Message, addr: Address) -> None:
        """A punch reached the server: answer it (the friend's side of the path)."""
        self.server.transport.send(Message(type="punch_ack", payload=message.payload), addr)

    def stop(self) -> None:
        """Leave the rendezvous (best effort, short timeout)."""
        try:
            call_rendezvous("/v1/unhost", {"code": self.identity.code, "token": self.identity.token}, self.url)
        except RendezvousError:
            pass


# --- Join side (game client) ---


class JoinOnline:
    """Find a friend's game through the rendezvous and punch a path to it.

    Phases: ``stun`` (learn our addresses) -> ``asking`` (send our
    candidates, get the host's) -> ``punching`` -> ``connected`` (``result``
    is the transport and the host's address, ready for GameClient) or
    ``failed`` (``error`` says why).
    """

    def __init__(
        self,
        identity: Identity,
        friend_code: str,
        name: str,
        url: Optional[str] = None,
        stun_servers: Optional[List[Tuple[str, int]]] = None,
    ) -> None:
        self.identity = identity
        self.friend_code = friend_code
        self.name = name
        self.url = url or rendezvous_url()
        self.transport = UDPTransport()
        self.stun = StunProbe(self.transport.send_raw, stun_servers)
        self.transport.raw_handler = self.stun.on_packet
        self.phase = "stun"
        self.error = ""
        self.host_name = ""
        self.path_kind = ""
        self.result: Optional[Tuple[UDPTransport, Address]] = None
        self.candidates: List[Candidate] = []
        self._call: Optional[Background] = None
        self._puncher: Optional[Puncher] = None

    def update(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        if self.phase in ("connected", "failed"):
            return
        if not self.stun.started:
            self.stun.start()
        self._receive()
        self.stun.update(now)
        if self.phase == "stun" and self.stun.done:
            self.candidates = gather_candidates(self.transport.port, self.stun.results, self.transport.ipv6)
            body = {
                "to": self.friend_code,
                "from": self.identity.code,
                "token": self.identity.token,
                "name": self.name,
                "version": PROTOCOL_VERSION,
                "candidates": self.candidates,
            }
            self._call = Background(call_rendezvous, "/v1/join", body, self.url)
            self.phase = "asking"
        elif self.phase == "asking" and self._call is not None and self._call.done:
            call, self._call = self._call, None
            if call.error is not None:
                kind = getattr(call.error, "kind", "error")
                self._fail(
                    {
                        "offline": "not hosting right now",
                        "unreachable": "rendezvous not reachable",
                        "forbidden": "code taken by another install",
                    }.get(kind, str(call.error)[:40])
                )
                return
            host = call.result.get("host", {})
            self.host_name = host.get("name", "")
            if host.get("version") not in (None, PROTOCOL_VERSION):
                self._fail(f"other game version ({host.get('version')}, you {PROTOCOL_VERSION})")
                return
            if not host.get("candidates"):
                self._fail("host has no address")
                return
            self._puncher = Puncher(self.transport, host["candidates"], self.identity.code)
            self.phase = "punching"
        if self.phase == "punching" and self._puncher is not None:
            self._puncher.update(now)
            if self._puncher.winner is not None:
                self.path_kind, addr = self._puncher.winner
                self.transport.raw_handler = None
                self.result = (self.transport, addr)
                self.phase = "connected"
            elif self._puncher.timed_out:
                self._fail("no direct path found")

    def _receive(self) -> None:
        while True:
            got = self.transport.receive()
            if got is None:
                return
            message, addr, _header = got
            if self._puncher is not None:
                self._puncher.on_message(message, addr)

    def _fail(self, error: str) -> None:
        self.phase = "failed"
        self.error = error
        self.transport.close()

    def cancel(self) -> None:
        if self.phase != "connected":
            self.phase = "failed"
            self.error = "cancelled"
            self.transport.close()


__all__ = [
    "Identity",
    "HostOnline",
    "JoinOnline",
    "Puncher",
    "RendezvousError",
    "call_rendezvous",
    "gather_candidates",
    "normalize_code",
    "rendezvous_url",
]
