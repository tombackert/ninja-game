import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["NINJA_GAME_TESTING"] = "1"

from game import Game  # noqa: E402
from scripts.entities import Player  # noqa: E402


def test_player_lives_property_alias():
    g = Game()
    p = g.player
    start = p.lives
    assert start == getattr(p, "lifes")  # alias returns same underlying value
    p.lives -= 1
    assert p.lives == getattr(p, "lifes")


def test_tilemap_save_uses_lives_key(tmp_path):
    g = Game()
    path = tmp_path / "save_test.json"
    tm = g.tilemap
    # Load current level to populate players
    # (Game.__init__ may not have invoked load sequence as expected
    # in headless test modifications)
    g.load_level(g.level)
    if not tm.players:
        p = Player(g, [0, 0], (8, 15), 0, lifes=3, respawn_pos=[0, 0])
        tm.players.append(p)
    tm.save(str(path))
    data = json.loads(path.read_text())
    players = data["entities_data"]["players"]
    assert "lives" in players[0]
    assert "lifes" not in players[0]


def test_tilemap_load_legacy_lifes(tmp_path):
    # Create legacy save with 'lifes'
    legacy = {
        "meta_data": {
            "map": 0,
            "timer": {"current_time": "00:00:00", "start_time": "00:00:00"},
        },
        "entities_data": {
            "players": [
                {
                    "id": 0,
                    "pos": [0, 0],
                    "velocity": [0, 0],
                    "air_time": 0,
                    "action": "idle",
                    "flip": False,
                    "alive": True,
                    "lifes": 7,
                    "respawn_pos": [0, 0],
                }
            ],
            "enemies": [],
        },
        "map_data": {"tilemap": {}, "tile_size": 16, "offgrid": []},
    }
    path = tmp_path / "legacy_save.json"
    path.write_text(json.dumps(legacy))

    g = Game()
    tm = g.tilemap
    tm.load(str(path))
    assert tm.players[0].lives == 7
    # Alias still accessible
    assert tm.players[0].lifes == 7
