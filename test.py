import pygame

pygame.init()
sdl_version = pygame.version.SDL
print("SDL version", sdl_version)

video_driver = pygame.display.get_driver()
print("Video driver:", video_driver)

try:
    render_driver = pygame.display.get_render_driver()
    print("Render driver:", render_driver)
except AttributeError:
    print("Render driver: None")
