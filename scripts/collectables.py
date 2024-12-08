import pygame

class Collectables:
    def __init__(self, game, pos, image):
        self.game = game
        self.pos = list(pos)
        self.size = (16, 16)
        self.image = image
        self.rect = pygame.Rect(self.pos[0], self.pos[1], self.size[0], self.size[1])

    def update(self, player_rect):
        return self.rect.colliderect(player_rect)

    def render(self, surf, offset=(0,0)):
        surf.blit(self.image, (self.pos[0]-offset[0], self.pos[1]-offset[1]))
