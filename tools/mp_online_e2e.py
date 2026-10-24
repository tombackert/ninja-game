"""E2E: a friend joins a hosted game by friend code (rendezvous + STUN + punching).

Starts ``server.py --online`` with a fresh host identity, then joins it in
this process like the game's "Join Friend" does: STUN on its own socket,
the join request through the rendezvous, punching the host's candidates,
then a normal game connection that plays a few seconds. Real STUN servers
are used, so this needs internet; the rendezvous is the deployed Worker
unless ``--rendezvous`` points at ``npx wrangler dev`` (rendezvous/).

    python tools/mp_online_e2e.py --rendezvous http://127.0.0.1:8787
    python tools/mp_online_e2e.py                 # deployed rendezvous
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pygame  # noqa: E402

from scripts.network.game_client import GameClient  # noqa: E402
from scripts.network.online import Identity, JoinOnline, call_rendezvous, rendezvous_url  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rendezvous", default=None, help="Rendezvous URL (default: the deployed one)")
    parser.add_argument("--port", type=int, default=27777, help="Host server port")
    parser.add_argument("--play", type=float, default=4.0, help="Seconds to play after joining")
    args = parser.parse_args()
    url = (args.rendezvous or rendezvous_url()).rstrip("/")
    tmp = tempfile.mkdtemp(prefix="mp_online_e2e_")
    host_id = Identity.load(os.path.join(tmp, "host.json"))
    friend_id = Identity.load(os.path.join(tmp, "friend.json"))
    print(f"[online] rendezvous {url}, host code {host_id.code}, friend code {friend_id.code}")

    env = dict(os.environ, NINJA_RENDEZVOUS_URL=url, NINJA_ONLINE_FILE=host_id.path)
    server = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(args.port), "--online", "--name", "E2E-Host", "--no-netlog"],
        env=env,
        stdout=open(os.path.join(tmp, "server.log"), "w"),
        stderr=subprocess.STDOUT,
    )
    failures = 0
    client = None
    try:
        started = time.monotonic()
        hosting = False
        while time.monotonic() - started < 15.0 and not hosting:
            time.sleep(0.5)
            try:
                status = call_rendezvous("/v1/status", {"codes": [host_id.code]}, url)
                hosting = status["friends"][host_id.code]["hosting"]
            except Exception as e:  # rendezvous not up yet
                print(f"[online] status: {e}")
        if not hosting:
            print("[online] FAIL: host never showed up at the rendezvous")
            return 1
        print(f"[online] ok   host online after {time.monotonic() - started:.1f} s")

        pygame.init()
        join = JoinOnline(friend_id, host_id.code, "E2E-Friend", url=url)
        started = time.monotonic()
        phases = []
        while join.phase not in ("connected", "failed") and time.monotonic() - started < 20.0:
            join.update()
            if not phases or phases[-1][0] != join.phase:
                phases.append((join.phase, time.monotonic() - started))
            time.sleep(0.005)
        print("[online] phases: " + ", ".join(f"{p} at {t:.2f} s" for p, t in phases))
        print(f"[online] friend candidates: {join.candidates}")
        if join.phase != "connected":
            print(f"[online] FAIL: join {join.phase}: {join.error}")
            return 1
        transport, addr = join.result
        print(f"[online] ok   path {join.path_kind} to {addr} after {time.monotonic() - started:.2f} s")

        client = GameClient(server_host=addr[0], server_port=addr[1], player_name="E2E-Friend", transport=transport)
        client.connect()
        deadline = time.monotonic() + 5.0
        while not client.is_connected and time.monotonic() < deadline:
            client.update()
            time.sleep(1 / 60)
        if not client.is_connected:
            print("[online] FAIL: no game connection over the punched path")
            return 1
        print(f"[online] ok   connected as player {client.player_id}")
        end = time.monotonic() + args.play
        snapshots = 0
        while time.monotonic() < end:
            client.update()
            client.send_input_state((True, False), [])
            snapshots += len(client.drain_new_snapshots())
            time.sleep(1 / 60)
        rate = snapshots / args.play
        print(f"[online] {'ok  ' if rate >= 20 else 'FAIL'} {rate:.1f} snapshots/s, RTT {client.rtt * 1000:.1f} ms")
        failures += rate < 20
    finally:
        if client is not None:
            client.disconnect()
            client.close()
        server.terminate()
        server.wait(5)
        with open(os.path.join(tmp, "server.log")) as f:
            online_lines = [line.rstrip() for line in f if line.startswith("Online:")]
        for line in online_lines:
            print(f"[server] {line[:200]}")
    print("[online] PASS" if not failures else f"[online] FAIL ({failures})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
