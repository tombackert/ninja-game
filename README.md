# Ninja Game

![Pygame](https://raw.githubusercontent.com/pygame/pygame/main/docs/reST/_static/pygame_logo.svg)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg?style=flat-square)](https://www.python.org/)
[![Pygame-CE](https://img.shields.io/pypi/v/pygame-ce.svg?style=flat-square&label=pygame-ce)](https://pypi.org/project/pygame-ce/)
[![CI](https://github.com/tombackert/ninja-game/actions/workflows/ci.yml/badge.svg)](https://github.com/tombackert/ninja-game/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](https://opensource.org/licenses/MIT)

A 2D platformer built with Pygame, featuring deterministic gameplay, modular AI, and a foundation for multiplayer and reinforcement learning integration.

![Thumbnail](https://github.com/tombackert/ninja-game/blob/main/data/thumbnails/ninja-game-thumbnail1.png)


## Features

- **Platformer Mechanics** - Double jump, wall slide, dash, and shooting
- **Modular AI System** - Pluggable enemy behaviors (Patrol, Shooter, Chaser, Jumper)
- **Ghost Replay System** - Race against your best runs with deterministic re-simulation
- **Level Editor** - Create and edit levels with the built-in editor
- **Per-Level Soundtracks** - Distinct audio identity for each level
- **Configurable Controls** - Rebindable key bindings
- **Performance HUD** - Real-time metrics overlay (F1)

## Architecture

The codebase follows a state-driven architecture with clear separation of concerns:

```
├── app.py              # Main entry point (StateManager-based)
├── editor.py           # Level editor
├── scripts/            # Core game logic
│   ├── entities.py     # Player, Enemy, PhysicsEntity
│   ├── state_manager.py
│   ├── input_router.py # Event → Action mapping
│   ├── renderer.py     # Unified rendering pipeline
│   ├── ai/             # Pluggable AI behaviors
│   ├── network/        # Multiplayer foundation
│   └── weapons/        # Extensible weapon system
├── data/               # Assets, maps, settings
└── tests/              # Pytest suite
```

For detailed architecture documentation, see [docs/architecture.md](docs/architecture.md).

## Getting Started

### Prerequisites

- Python 3.10+
- Pygame-CE

### Installation

```bash
# Clone the repository
git clone https://github.com/tombackert/ninja-game.git
cd ninja-game

# Install dependencies
pip install pygame-ce

# Run the game
python app.py
```

### Running Tests

Tests run headless using the SDL dummy driver:

```bash
export SDL_VIDEODRIVER=dummy
pytest -q
```

### Level Editor

```bash
python editor.py
```

## Controls

| Action | Key |
|--------|-----|
| Move   | Arrow Keys / WASD |
| Jump   | W / Up |
| Dash   | Space / Left click |
| Shoot  | Rigth click |
| Pause  | Escape |
| Performance HUD | F1 |

## Development

### Pre-commit Hooks

This repository uses pre-commit hooks for code quality (Ruff, Black, mypy):

```bash
pip install pre-commit
pre-commit install
```

Run all hooks manually:

```bash
pre-commit run --all-files
```

### Project Structure

| Directory | Purpose |
|-----------|---------|
| `scripts/` | Core game logic (~52 modules) |
| `scripts/ai/` | AI policy implementations |
| `scripts/network/` | Multiplayer infrastructure |
| `scripts/weapons/` | Weapon system |
| `data/` | Assets, maps, saves, settings |
| `tests/` | Pytest test suite (~44 test files) |
| `docs/` | Architecture and patch notes |
| `experiments/` | Benchmarks and prototypes |

## Contributing

Contributions are welcome. Here are some ways to help:

- **Create levels** - Use the level editor to design new challenges
- **Report bugs** - Open an issue with reproduction steps
- **Add features** - Check the [backlog](docs/backlog.md) for ideas
- **Improve documentation** - Help others understand the codebase
- **Add AI behaviors** - Extend the policy system with new enemy types

## Resources

- [Pygame-CE Documentation](https://pyga.me/docs/)
- [Pygame-CE GitHub](https://github.com/pygame-community/pygame-ce)

## Credits

Based on the tutorial by [DaFluffyPotato](https://www.youtube.com/@DaFluffyPotato): [Pygame Platformer Tutorial](https://www.youtube.com/watch?v=2gABYM5M0ww)

## Citation

If you use this project in your research or work, please cite it as:

```bibtex
@software{backert2025ninjagame,
  author       = {Backert, Tom},
  title        = {Ninja Game: A Deterministic 2D Platformer with Modular AI},
  year         = {2025},
  url          = {https://github.com/tombackert/ninja-game},
  version      = {3.0}
}
```

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.
