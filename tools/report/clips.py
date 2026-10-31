"""Short silent clips for the report, cut from the real game.

    startup   the real app in a throwaway sandbox: main menu, level list, play,
              driven by the keyboard events of the bot in tools/worlds/play.py
    ghost     a run racing the ghost of a better one, re-simulated like the trailer
    netplay   a two-player session over an emulated Wi-Fi with the network HUD open;
              on loopback, so it shows neither a friend code nor a real address

Usage:
    python -m tools.report.clips startup ghost netplay --out out/report/clips
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, List

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WIDTH, HEIGHT = 1280, 720
CRF = "27"


def encode(frames: str, fps: int, out: str) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            os.path.join(frames, "%05d.jpg"),
            "-vf",
            f"scale={WIDTH}:{HEIGHT}:flags=neighbor",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            CRF,
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            out,
        ],
        check=True,
    )


class Recorder:
    """Saves the display surface every `every` frames."""

    def __init__(self, directory: str, every: int = 2):
        self.directory = directory
        self.every = every
        self.frame = 0
        self.saved = 0
        os.makedirs(directory, exist_ok=True)

    def tick(self) -> None:
        import pygame

        self.frame += 1
        surface = pygame.display.get_surface()
        if surface is not None and self.frame % self.every == 0:
            pygame.image.save(surface, os.path.join(self.directory, f"{self.saved:05d}.jpg"))
            self.saved += 1


# --- startup -----------------------------------------------------------------


def startup_child(frames: str, level: int, play_frames: int) -> int:
    """Inside the sandbox: the bot's run, recorded from the first menu frame on."""
    from tools.worlds import play

    recorder = Recorder(frames)
    on_frame = play.Bot.on_frame

    def recorded(bot: Any) -> None:
        recorder.tick()
        on_frame(bot)
        if bot.game_frames >= play_frames:
            raise SystemExit

    play.Bot.on_frame = recorded
    play.bot_main(level, frames + "-bot", False)
    return 0


def startup(out_dir: str, level: int = 21, play_seconds: float = 5.0) -> None:
    from tools.worlds.play import build_sandbox

    sandbox = tempfile.mkdtemp(prefix="ninja_clip_")
    frames = tempfile.mkdtemp(prefix="ninja_clip_frames_")
    build_sandbox(sandbox, level)
    os.makedirs(frames + "-bot", exist_ok=True)
    env = dict(os.environ, PYTHONPATH=REPO)
    me = ["-m", "tools.report.clips", "startup-child", "--frames", frames, "--level", str(level)]
    me += ["--play-frames", str(int(play_seconds * 60))]
    subprocess.run([sys.executable, *me], cwd=sandbox, env=env, check=False)
    encode(frames, 30, os.path.join(out_dir, "startup.mp4"))
    shutil.rmtree(sandbox, ignore_errors=True)
    shutil.rmtree(frames, ignore_errors=True)
    shutil.rmtree(frames + "-bot", ignore_errors=True)


# --- ghost -------------------------------------------------------------------


def ghost(out_dir: str) -> None:
    from tools.trailer import Shot, Studio

    studio = Studio()
    pygame = studio.pg
    frames = tempfile.mkdtemp(prefix="ninja_clip_frames_")
    shot = Shot(level=2, start=30, frames=240, run="last", ghost="best")
    for i, frame in enumerate(studio.shot(shot)):
        if i % 2 == 0:
            pygame.image.save(frame, os.path.join(frames, f"{i // 2:05d}.jpg"))
    encode(frames, 30, os.path.join(out_dir, "ghost.mp4"))
    shutil.rmtree(frames, ignore_errors=True)


# --- netplay -----------------------------------------------------------------


def netplay_child(frames: str, port: int, duration: float, log: str) -> int:
    """The friend's game client of mp_netbench, recorded, with the network HUD open."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, REPO)
    import pygame

    from tools import mp_netbench

    recorder = Recorder(frames)
    real_get = pygame.event.get

    def get_events(*a: Any, **kw: Any) -> list:
        recorder.tick()
        if recorder.frame in (30, 32):  # off -> status line -> status line and graphs
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2, mod=0, unicode="", scancode=0))
            pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_F2, mod=0, unicode="", scancode=0))
        return real_get(*a, **kw)

    pygame.event.get = get_events
    args = argparse.Namespace(pattern="runner", log=log, duration=duration, port=port, name="Friend")
    return mp_netbench.client_main(args)


def netplay(out_dir: str, port: int = 25900, duration: float = 16.0) -> None:
    from tools.mp_netbench import PROFILES

    workdir = tempfile.mkdtemp(prefix="ninja_clip_net_")
    frames = os.path.join(workdir, "frames")
    procs: List[subprocess.Popen] = []
    bench = os.path.join(REPO, "tools", "mp_netbench.py")

    def spawn(cmd: List[str]) -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, *cmd], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
        return p

    try:
        spawn(["server.py", "--port", str(port), "--level", "0", "--no-netlog"])
        time.sleep(1.5)
        spawn(
            [
                "tools/mp_netem.py",
                "--listen-port",
                str(port + 1),
                "--server-port",
                str(port),
                *(PROFILES["wlan"][1] or []),
                "--seed",
                "7",
            ]
        )
        time.sleep(0.5)
        host = spawn(
            [
                bench,
                "--client",
                "--port",
                str(port),
                "--name",
                "Host",
                "--duration",
                str(duration + 2),
                "--log",
                os.path.join(workdir, "host.jsonl"),
            ]
        )
        time.sleep(1.0)
        friend = spawn(
            [
                "-m",
                "tools.report.clips",
                "netplay-child",
                "--frames",
                frames,
                "--port",
                str(port + 1),
                "--duration",
                str(duration),
                "--log",
                os.path.join(workdir, "friend.jsonl"),
            ]
        )
        friend.wait(timeout=duration + 60)
        host.wait(timeout=duration + 60)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
    # Skip the join: the clip starts with the HUD open and the graphs filled
    os.makedirs(frames + "-cut")
    names = sorted(os.listdir(frames))[150:330]
    for i, name in enumerate(names):
        shutil.copy(os.path.join(frames, name), os.path.join(frames + "-cut", f"{i:05d}.jpg"))
    encode(frames + "-cut", 30, os.path.join(out_dir, "netplay.mp4"))
    shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="+", choices=["startup", "ghost", "netplay", "startup-child", "netplay-child"])
    parser.add_argument("--out", default="out/report/clips")
    parser.add_argument("--level", type=int, default=21)
    parser.add_argument("--frames")
    parser.add_argument("--play-frames", type=int, default=300)
    parser.add_argument("--port", type=int)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--log")
    args = parser.parse_args()

    if args.clips == ["startup-child"]:
        return startup_child(args.frames, args.level, args.play_frames)
    if args.clips == ["netplay-child"]:
        return netplay_child(args.frames, args.port, args.duration, args.log)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    os.chdir(REPO)
    sys.path.insert(0, REPO)
    for clip in args.clips:
        if clip == "startup":
            startup(out, args.level)
        elif clip == "ghost":
            ghost(out)
        elif clip == "netplay":
            netplay(out)
        print(f"{clip}: {os.path.join(out, clip + '.mp4')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
