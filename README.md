# Ninja Game

![Pygame](https://raw.githubusercontent.com/pygame/pygame/main/docs/reST/_static/pygame_logo.svg)

[![Python](https://img.shields.io/badge/python-3.10.8-blue.svg?style=flat-square)](https://www.python.org/)
[![PyPiVersion](https://img.shields.io/pypi/v/pygame-ce.svg?v=1)](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![GitHub commit activity](https://img.shields.io/github/commit-activity/t/tombackert/ninja-game)
![GitHub last commit](https://img.shields.io/github/last-commit/tombackert/ninja-game)
![CI](https://github.com/tombackert/ninja-game/actions/workflows/ci.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](https://opensource.org/licenses/MIT)




This is a fun and challenging 2D Platformer game where you must use your skills to navigate through difficult worlds, defeat enemies, collect trophies, reach new goals or just have fun playing against your friends. 
This project is intended for anyone who is looking to dive into game dev, learn how basic game mechanics work, or stengthen their coding skills in a learning by doing approach.  

## The game features:

- Beautiful pixel art graphics
- Challenging Plattformer gameplay
- Enemy AI
- Very realistic game physics
- Great music
- Stunning sound and visual effects

![Thumbnail](https://github.com/tombackert/ninja-game/blob/main/data/thumbnails/ninja-game-thumbnail1.png)


## Getting Started:

1. Install [Python](https://www.python.org/downloads/) (Version used: Python 3.10.8)
2. Install [Pygame](https://pyga.me/) via  `pip install pygame-ce`
3. Clone or fork the game: `git clone https://github.com/tombackert/ninja-game.git`
4. Run the game
5. Explore the code and experiment with different levels and features

Headless (no window) test execution is configured in CI via SDL_VIDEODRIVER=dummy; you can replicate locally:

```
export SDL_VIDEODRIVER=dummy
pytest -q
```


## Contributing:
I encourage contributions to this project. Feel free to submit pull requests for new projects, improvements, or additional resources. Please refer to the CONTRIBUTING.md *(to be added...)* file (if you create one) for guidelines.

Here are some ways you can help:

- Create new levels with the level editor (very easy)
- Report bugs
- Document the game
- Code restructuring to make it more accessible
- Provide valuable tips on how to create state-of-the-art pixel art games
- Add new features
- I hope you enjoy playing Ninja Game!

### Dev Tooling (Pre-commit Hooks)

This repo ships a `.pre-commit-config.yaml` with fast quality gates (Ruff lint+format, Black, mypy (lenient), and basic hygiene hooks). To enable locally:

```
pip install pre-commit
pre-commit install
```

On each commit only changed files are checked; auto-fixes (Ruff / Black) are applied and re-staged automatically. You can run all hooks manually with:

```
pre-commit run --all-files
```


## Resources
Here are some resources that you might find helpful:
- [Pygame-Ce](https://pyga.me/)
- [Pygame-docs](https://pyga.me/docs/)
- [Pygame Github](https://github.com/pygame-community/pygame-ce)
- [Tutorial](https://www.youtube.com/watch?v=2gABYM5M0ww&t=20708s)


## Repo Goals

Goals of this repository:
1. Gain new insights and experience in game dev.
2. Strengthen object-oriented coding skills.
3. Acquire new skills in implementing industry standard software engineering practices.
4. Learn how to manage medium sized software projects.
5. Learn how to deploy software projects.


## Credits:
All credits belong to [DaFluffyPotato](https://www.youtube.com/@DaFluffyPotato) since the game is initally based on his amazing [tutorial](https://www.youtube.com/watch?v=2gABYM5M0ww&t=20708s) on [Pygame](https://www.pygame.org/docs/) game dev.


## License:
This repository is licensed under the MIT License.



