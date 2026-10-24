"""Tests for online play by friend code (scripts/network/online.py, stun.py, dual-stack transport)."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

import pygame

from scripts.network import stun
from scripts.network.game_client import GameClient
from scripts.network.game_server import GameServer
from scripts.network.headless_game import HeadlessGame
from scripts.network.messages import Message
from scripts.network.online import (
    HostOnline,
    Identity,
    JoinOnline,
    Puncher,
    call_rendezvous,
    gather_candidates,
    new_code,
    normalize_code,
)
from scripts.network.udp_transport import UDPTransport, normalize_address, resolve_address

# RFC 5769 sample responses (2.2 IPv4, 2.3 IPv6): 192.0.2.1:32853 and
# 2001:db8:1234:5678:11:2233:4455:6677 port 32853
RFC5769_V4 = bytes.fromhex(
    "0101003c2112a442b7e7a701bc34d686fa87dfae8022000b7465737420766563746f7220"
    "00200008"
    "0001a147e112a643"
    "000800142b91f599fd9e90c38c7489f92af9ba53f06be7d780280004c07d4c96"
)
RFC5769_V6 = bytes.fromhex(
    "010100482112a442b7e7a701bc34d686fa87dfae8022000b7465737420766563746f7220"
    "00200014"
    "0002a1470113a9faa5d3f179bc25f4b5bed2b9d9"
    "00080014a382954e4be67bf11784c97c8292c275bfe3ed4180280004c8fb0b4c"
)


def setUpModule():
    pygame.init()


def _ipv6_loopback() -> bool:
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.bind(("::1", 0))
        s.close()
        return True
    except OSError:
        return False


def _drain(transport: UDPTransport, seconds: float = 0.3) -> List[Any]:
    got = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        result = transport.receive()
        if result is None:
            time.sleep(0.005)
            continue
        got.append(result)
    return got


class TestStun(unittest.TestCase):
    def test_rfc5769_ipv4_response(self):
        tid, addr = stun.parse_response(RFC5769_V4)
        self.assertEqual(tid, bytes.fromhex("b7e7a701bc34d686fa87dfae"))
        self.assertEqual(addr, ("192.0.2.1", 32853))

    def test_rfc5769_ipv6_response(self):
        _tid, addr = stun.parse_response(RFC5769_V6)
        self.assertEqual(addr, ("2001:db8:1234:5678:11:2233:4455:6677", 32853))

    def test_encode_round_trip(self):
        packet, tid = stun.binding_request()
        self.assertEqual(len(packet), 20)
        self.assertTrue(stun.is_stun(packet))
        for addr in (("203.0.113.7", 7777), ("2a01:41e1::1", 50123)):
            self.assertEqual(stun.parse_response(stun.encode_response(tid, addr)), (tid, addr))

    def test_game_packets_are_not_stun(self):
        self.assertFalse(stun.is_stun(b'{"header": {"sequence": 0}, "message": {}}'))
        self.assertIsNone(stun.parse_response(stun.binding_request()[0]))  # a request, not a response


class FakeStun:
    """A local STUN server answering with the address it saw, on IPv4 and IPv6 loopback."""

    def __init__(self) -> None:
        self.sockets = []
        self.servers = []
        for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            if family == socket.AF_INET6 and not _ipv6_loopback():
                continue
            s = socket.socket(family, socket.SOCK_DGRAM)
            s.bind((host, 0))
            s.settimeout(0.1)
            self.sockets.append(s)
            self.servers.append((host, s.getsockname()[1]))
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def resolver(self, servers):
        out = {"v4": [], "v6": []}
        for host, port in self.servers:
            out["v6" if ":" in host else "v4"].append((host, port))
        return out

    def _serve(self) -> None:
        while self._running:
            for s in self.sockets:
                try:
                    data, addr = s.recvfrom(2048)
                except OSError:
                    continue
                if stun.is_stun(data):
                    s.sendto(stun.encode_response(data[8:20], normalize_address(addr)), addr)

    def close(self) -> None:
        self._running = False
        self._thread.join(1.0)
        for s in self.sockets:
            s.close()


class TestStunProbe(unittest.TestCase):
    def test_probe_learns_the_mapped_addresses_through_the_transport(self):
        fake = FakeStun()
        transport = UDPTransport()
        try:
            probe = stun.StunProbe(transport.send_raw, servers=[("x", 1)], resolver=fake.resolver)
            transport.raw_handler = probe.on_packet
            probe.start()
            deadline = time.time() + 2.0
            while not probe.done and time.time() < deadline:
                probe.update()
                transport.receive()
                time.sleep(0.01)
            self.assertEqual(probe.results["v4"], ("127.0.0.1", transport.port))
            if len(fake.servers) == 2:
                self.assertEqual(probe.results["v6"], ("::1", transport.port))
        finally:
            transport.close()
            fake.close()


class TestDualStackTransport(unittest.TestCase):
    def test_ipv4_and_ipv6_peers_on_one_socket(self):
        server = UDPTransport("::", 0)
        clients = [UDPTransport("127.0.0.1", 0)]
        if server.ipv6 and _ipv6_loopback():
            clients.append(UDPTransport("::1", 0))
        try:
            for client in clients:
                target = ("::1" if client.ipv6 else "127.0.0.1", server.port)
                client.send(Message(type="ping", payload={}), target)
                got = _drain(server, 0.2)
                self.assertEqual(len(got), 1)
                _msg, addr, _header = got[0]
                self.assertEqual(addr, client.local_addr)  # plain (host, port), no ::ffff:
                server.send(Message(type="pong", payload={}), addr)
                self.assertEqual(_drain(client, 0.2)[0][0].type, "pong")
        finally:
            server.close()
            for c in clients:
                c.close()

    def test_stun_packets_go_to_the_raw_handler(self):
        server = UDPTransport("::", 0)
        sender = UDPTransport("127.0.0.1", 0)
        seen = []
        server.raw_handler = lambda data, addr: seen.append(addr)
        try:
            sender.send_raw(stun.binding_request()[0], ("127.0.0.1", server.port))
            sender.send(Message(type="ping", payload={}), ("127.0.0.1", server.port))
            got = _drain(server, 0.2)
            self.assertEqual([m.type for m, _, _ in got], ["ping"])
            self.assertEqual(seen, [sender.local_addr])
        finally:
            server.close()
            sender.close()

    def test_addresses_are_normalized(self):
        self.assertEqual(normalize_address(("::ffff:192.168.1.5", 7777, 0, 0)), ("192.168.1.5", 7777))
        self.assertEqual(normalize_address(("2A01:41E1:0:0::1", 7777, 0, 0)), ("2a01:41e1::1", 7777))
        self.assertEqual(resolve_address("localhost", 7777), ("127.0.0.1", 7777))
        self.assertEqual(resolve_address("2A01:41E1::1", 7777), ("2a01:41e1::1", 7777))


class TestIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "online.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_codes(self):
        code = new_code()
        self.assertRegex(code, r"^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$")
        self.assertEqual(normalize_code("k7qm 2xra"), "K7QM-2XRA")
        self.assertEqual(normalize_code("K7QM-2XRO"), "K7QM-2XR0")  # O is read as 0
        self.assertIsNone(normalize_code("K7QM-2XR"))
        self.assertIsNone(normalize_code("K7QM-2XRU"))  # U is not in the alphabet

    def test_created_once_then_loaded(self):
        first = Identity.load(self.path)
        second = Identity.load(self.path)
        self.assertEqual((first.code, first.token), (second.code, second.token))
        self.assertGreaterEqual(len(first.token), 32)

    def test_friends(self):
        me = Identity.load(self.path)
        self.assertTrue(me.add_friend("k7qm-2xra", "Max"))
        self.assertFalse(me.add_friend("K7QM2XRA"))  # already there
        self.assertFalse(me.add_friend(me.code))  # ourselves
        self.assertFalse(me.add_friend("hello"))
        me.set_friend_name("K7QM-2XRA", "Maxi")
        again = Identity.load(self.path)
        self.assertEqual(again.friends, [{"code": "K7QM-2XRA", "name": "Maxi"}])
        again.remove_friend("K7QM-2XRA")
        self.assertEqual(Identity.load(self.path).friends, [])

    def test_a_broken_file_gives_a_new_identity(self):
        with open(self.path, "w") as f:
            f.write("{broken")
        self.assertIsNotNone(normalize_code(Identity.load(self.path).code))


class TestPuncher(unittest.TestCase):
    def test_both_sides_find_the_path_and_prefer_lan(self):
        a, b = UDPTransport(), UDPTransport()
        try:
            unreachable = ["v4", "192.0.2.1", 9]  # TEST-NET, never answers
            pa = Puncher(a, [unreachable, ["lan", "127.0.0.1", b.port]], "A")
            pb = Puncher(b, [["v4", "127.0.0.1", a.port]], "B")
            deadline = time.time() + 2.0
            while (pa.winner is None or pb.winner is None) and time.time() < deadline:
                for p in (pa, pb):
                    p.update()
                    while (got := p.transport.receive()) is not None:
                        p.on_message(got[0], got[1])
                time.sleep(0.01)
            self.assertEqual(pa.winner, ("lan", ("127.0.0.1", b.port)))
            self.assertEqual(pb.winner, ("v4", ("127.0.0.1", a.port)))
        finally:
            a.close()
            b.close()

    def test_candidates(self):
        cands = gather_candidates(7777, {"v4": ("203.0.113.7", 40000), "v6": ("2a01:41e1::1", 7777)})
        kinds = {c[0]: c for c in cands}
        self.assertEqual(kinds["v4"], ["v4", "203.0.113.7", 40000])
        self.assertEqual(kinds["v6"], ["v6", "2a01:41e1::1", 7777])


class FakeRendezvous:
    """The rendezvous Worker's API (rendezvous/src/index.js), in memory, over local HTTP."""

    def __init__(self) -> None:
        state: Dict[str, Any] = {"presence": {}, "joins": {}, "tokens": {}}
        self.state = state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                status, out = route(self.path, body)
                data = json.dumps(out).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        def authorized(code, token):
            return state["tokens"].setdefault(code, token) == token

        def route(path, body):
            if path == "/v1/host":
                if not authorized(body["code"], body["token"]):
                    return 403, {"error": "code belongs to someone else"}
                state["presence"][body["code"]] = body
                return 200, {"ok": True, "joins": state["joins"].pop(body["code"], [])}
            if path == "/v1/join":
                if not authorized(body["from"], body["token"]):
                    return 403, {"error": "code belongs to someone else"}
                host = state["presence"].get(body["to"])
                if host is None:
                    return 404, {"error": "offline"}
                join = {k: body[k] for k in ("from", "name", "version", "candidates")}
                state["joins"].setdefault(body["to"], []).append(join)
                return 200, {"ok": True, "host": {k: host[k] for k in ("name", "level", "version", "candidates")}}
            if path == "/v1/status":
                friends = {}
                for code in body["codes"]:
                    p = state["presence"].get(code)
                    friends[code] = (
                        {"hosting": True, "name": p["name"], "level": p["level"]} if p else {"hosting": False}
                    )
                return 200, {"ok": True, "friends": friends}
            if path == "/v1/unhost":
                state["presence"].pop(body["code"], None)
                return 200, {"ok": True}
            return 404, {"error": "not found"}

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class TestJoinByCode(unittest.TestCase):
    """Host and friend find each other through the rendezvous and punch a path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.host_id = Identity.load(os.path.join(self.tmp.name, "host.json"))
        self.friend_id = Identity.load(os.path.join(self.tmp.name, "friend.json"))
        self.rendezvous = FakeRendezvous()
        self.stun = FakeStun()

    def tearDown(self):
        self.stun.close()
        self.rendezvous.close()
        self.tmp.cleanup()

    def test_friend_joins_by_code(self):
        game = HeadlessGame(level=0)
        server = GameServer(port=20010, game=game)
        server.on_player_join(lambda pid, name: game.add_player(pid))
        host = HostOnline(server, self.host_id, "Tom", 0, url=self.rendezvous.url, stun_servers=[("x", 1)])
        host.stun._resolver = self.stun.resolver
        server.on_punch = host.on_punch
        client = None
        try:
            deadline = time.time() + 5.0
            while host.status != "online" and time.time() < deadline:
                server.update()
                host.update()
                time.sleep(0.01)
            self.assertEqual(host.status, "online")
            status = call_rendezvous("/v1/status", {"codes": [self.host_id.code]}, self.rendezvous.url)
            self.assertTrue(status["friends"][self.host_id.code]["hosting"])

            join = JoinOnline(
                self.friend_id, self.host_id.code, "Max", url=self.rendezvous.url, stun_servers=[("x", 1)]
            )
            join.stun._resolver = self.stun.resolver
            deadline = time.time() + 8.0
            while join.phase not in ("connected", "failed") and time.time() < deadline:
                join.update()
                server.update()
                host.update()
                time.sleep(0.01)
            self.assertEqual(join.phase, "connected", join.error)

            transport, (addr_host, addr_port) = join.result
            client = GameClient(server_host=addr_host, server_port=addr_port, player_name="Max", transport=transport)
            client.connect()
            deadline = time.time() + 3.0
            while not client.is_connected and time.time() < deadline:
                server.update()
                host.update()
                client.update()
                time.sleep(0.01)
            self.assertTrue(client.is_connected)
            self.assertEqual(len(game.players), 1)
            # The host picks the join request up with its next presence call
            # (on loopback the friend's punches get through before that)
            deadline = time.time() + 3.0
            while "join_request" not in [e["event"] for e in host.events] and time.time() < deadline:
                server.update()
                host.update()
                time.sleep(0.01)
            join_request = next(e for e in host.events if e["event"] == "join_request")
            self.assertEqual((join_request["from"], join_request["name"]), (self.friend_id.code, "Max"))
        finally:
            if client is not None:
                client.close()
            server.shutdown()

    def test_joining_a_friend_who_is_not_hosting_fails_clearly(self):
        join = JoinOnline(self.friend_id, self.host_id.code, "Max", url=self.rendezvous.url, stun_servers=[("x", 1)])
        join.stun._resolver = self.stun.resolver
        deadline = time.time() + 5.0
        while join.phase not in ("connected", "failed") and time.time() < deadline:
            join.update()
            time.sleep(0.01)
        self.assertEqual((join.phase, join.error), ("failed", "not hosting right now"))


if __name__ == "__main__":
    unittest.main()
