import pygame
import sys

class KeyboardManager:
    def __init__(self, game=None, editor=None):
        self.game = game
        self.editor = editor

    def handle_keydown(self):
        for event in pygame.event.get():
            
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            if self.editor is not None:
                self.handle_editor_event(event)
            else:
                self.handle_game_event(event)

       
              
    def handle_game_event(self, event):
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
                    self.game.sfx['jump'].play()

            # Arrow keys
            if event.key == pygame.K_LEFT:
                self.game.movement[0] = True
            if event.key == pygame.K_RIGHT:
                self.game.movement[1] = True
            if event.key == pygame.K_UP:
                if self.game.player.jump():
                    self.game.sfx['jump'].play()

            # Space
            if event.key == pygame.K_SPACE:
                self.game.player.dash()

            # Respawn
            if event.key == pygame.K_r:
                self.game.dead += 1
                self.game.player.lifes -= 1
                print(self.game.dead)

            # Save position
            if event.key == pygame.K_p:
                if self.game.saves > 0:
                    self.game.saves -= 1
                    self.game.player.respawn_pos = list(self.game.player.pos)
                    print('saved respawn pos: ', self.game.player.respawn_pos)

        # Stop.movement
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_a:
                self.game.movement[0] = False
            if event.key == pygame.K_d:
                self.game.movement[1] = False

            if event.key == pygame.K_LEFT:
                self.game.movement[0] = False
            if event.key == pygame.K_RIGHT:
                self.game.movement[1] = False
            
    def handle_editor_event(self, event):
        # Object placement
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.editor.clicking = True
            if event.button == 3:
                self.editor.right_clicking = True
            
            if self.editor.shift:
                if event.button == 4:
                    self.editor.tile_variant = (self.editor.tile_variant - 1) % len(self.editor.assets[self.editor.tile_list[self.editor.tile_group]])
                if event.button == 5:
                    self.editor.tile_variant = (self.editor.tile_variant + 1) % len(self.editor.assets[self.editor.tile_list[self.editor.tile_group]])
            else:
                if event.button == 4:
                    self.editor.tile_group = (self.editor.tile_group - 1) % len(self.editor.tile_list)
                    self.editor.tile_variant = 0
                if event.button == 5:
                    self.editor.tile_group = (self.editor.tile_group + 1) % len(self.editor.tile_list)
                    self.editor.tile_variant = 0

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.editor.clicking = False
            if event.button == 3:
                self.editor.right_clicking = False

        # Movement and other controls
        if event.type == pygame.KEYDOWN:
            # w, a, s, d
            if event.key == pygame.K_a:
                self.editor.movement[0] = True
            if event.key == pygame.K_d:
                self.editor.movement[1] = True
            if event.key == pygame.K_w:
                self.editor.movement[2] = True
            if event.key == pygame.K_s:
                self.editor.movement[3] = True
            
            if event.key == pygame.K_LEFT:
                self.editor.movement[0] = True
            if event.key == pygame.K_RIGHT:
                self.editor.movement[1] = True
            if event.key == pygame.K_UP:
                self.editor.movement[2] = True
            if event.key == pygame.K_DOWN:
                self.editor.movement[3] = True

            if event.key == pygame.K_g:
                self.editor.ongrid = not self.editor.ongrid
            if event.key == pygame.K_LSHIFT:
                self.editor.shift = True
            if event.key == pygame.K_o:
                self.editor.tilemap.save(self.editor.CURRENT_MAP)
            if event.key == pygame.K_t:
                self.editor.tilemap.autotile()
        
            if event.key == pygame.K_ESCAPE:
                self.editor.tilemap.save(self.editor.CURRENT_MAP)
                pygame.quit()
                sys.exit()

        if event.type == pygame.KEYUP:
            if event.key == pygame.K_a:
                self.editor.movement[0] = False
            if event.key == pygame.K_d:
                self.editor.movement[1] = False
            if event.key == pygame.K_w:
                self.editor.movement[2] = False
            if event.key == pygame.K_s:
                self.editor.movement[3] = False

            if event.key == pygame.K_LEFT:
                self.editor.movement[0] = False
            if event.key == pygame.K_RIGHT:
                self.editor.movement[1] = False
            if event.key == pygame.K_UP:
                self.editor.movement[2] = False
            if event.key == pygame.K_DOWN:
                self.editor.movement[3] = False

            if event.key == pygame.K_LSHIFT:
                self.editor.shift = False