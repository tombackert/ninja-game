import pygame
import sys


class KeyboardManager:
    def __init__(self, game):
        self.game = game

    def handle_keyboard_input(self):
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # Movement keys
            if event.type == pygame.KEYDOWN:

                if event.key == pygame.K_ESCAPE:
                    self.game.paused = True

                # W, A, S, D
                if event.key == pygame.K_a:
                    self.game.movement[0] = True
                if event.key == pygame.K_d:
                    self.game.movement[1] = True
                if event.key == pygame.K_w:
                    if self.game.player.jump():
                        self.game.sfx["jump"].play()

                # Arrow keys
                if event.key == pygame.K_LEFT:
                    self.game.movement[0] = True
                if event.key == pygame.K_RIGHT:
                    self.game.movement[1] = True
                if event.key == pygame.K_UP:
                    if self.game.player.jump():
                        self.game.sfx["jump"].play()

                # Space for dash
                if event.key == pygame.K_SPACE:
                    self.game.player.dash()

                # X for shooting
                if event.key == pygame.K_x:
                    self.game.player.shoot()

                # Respawn
                if event.key == pygame.K_r:
                    self.game.dead += 1
                    self.game.player.lives -= 1
                    print(self.game.dead)

                # Save position
                if event.key == pygame.K_p:
                    if self.game.saves > 0:
                        self.game.saves -= 1
                        self.game.player.respawn_pos = list(self.game.player.pos)
                        print("saved respawn pos: ", self.game.player.respawn_pos)

            # Stop movement
            if event.type == pygame.KEYUP:
                if event.key == pygame.K_a:
                    self.game.movement[0] = False
                if event.key == pygame.K_d:
                    self.game.movement[1] = False

                if event.key == pygame.K_LEFT:
                    self.game.movement[0] = False
                if event.key == pygame.K_RIGHT:
                    self.game.movement[1] = False

    def handle_mouse_input(self):
        mouse_buttons = pygame.mouse.get_pressed()
        if mouse_buttons[0]:  # Left mouse button
            self.game.player.shoot()
        if mouse_buttons[2]:  # Right mouse button
            self.game.player.dash()
