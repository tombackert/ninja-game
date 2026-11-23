# Fullscreen: what it costs

Measured 2026-11-17 on an Apple M1, pygame-ce 2.5.6, no vsync.

**Result:** fullscreen through `pygame.SCALED` at 1280x720 costs nothing: 4.6 ms per frame, the same as the window, because the GPU does the upscaling. Native fullscreen (software scaling to 1920x1080) costs +2.6 ms per frame (+57 %) and still uses only about 45 % of the 16.7 ms a 60 FPS frame may take. The game uses SCALED (`apply_window_mode` in `scripts/displayManager.py`; F11 or Options -> Fullscreen).

## Real display

External monitor 1920x1080, campaign (levels 0-6) plus water level 25, median of 2 runs.

| Mode | Frame p50 (ms) | Water p50 (ms) | Flip (ms) |
| --- | ---: | ---: | ---: |
| Window 1280x720 (before) | 4.6 | 6.4 | 1.0 |
| Fullscreen SCALED, 1280x720 | 4.6 | 6.7 | 0.9 |
| Fullscreen native 1920x1080 | 7.2 | 9.0 | 1.9 |
| Fullscreen SCALED, 640x360 | 2.6 | 4.9 | 0.4 |

640x360 is cheapest, but the camera steps by whole game pixels again.

## Window size (headless)

Software scaling grows linearly with the pixel count, about 1.6 ms per megapixel. Only at 2880x1800 (native Retina) does the water level miss the budget at p99 (17.1 ms).

| Window | Frame p50 (ms) | Water p50 (ms) |
| --- | ---: | ---: |
| 1280x720 | 3.4 | 5.7 |
| 1440x900 | 4.0 | 6.2 |
| 1920x1080 | 5.5 | 7.7 |
| 2560x1440 | 7.8 | 10.0 |
| 2560x1600 | 8.4 | 10.7 |
| 2880x1800 | 10.1 | 12.4 |

## Method and limits

- The campaign from `tools/bench/session.py` with the window size patched, headless with the SDL dummy driver; the real-display runs replaced `set_mode` with each mode.
- The cost is in `Renderer._present`: the 640x360 image is scaled to the window in software every frame. With `SCALED` the GPU does it.
- On the real display every mode has more outliers (p99 12-13 ms) than headless. That comes from presenting on macOS, not from fullscreen.
