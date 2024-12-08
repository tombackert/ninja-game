import pygame

class Collectables:
    def __init__(self, game, pos, animation):
        self.game = game
        self.pos = list(pos)
        self.size = (16, 16)
        self.animation = animation.copy()
        self.rect = pygame.Rect(self.pos[0], self.pos[1], self.size[0], self.size[1])

    def update(self, player_rect):
        self.animation.update()
        return self.rect.colliderect(player_rect)

    def render(self, surf, offset=(0,0)):
        # Aktuelles Frame holen
        current_frame = self.animation.img()
        
        # Originale Größe
        w, h = current_frame.get_size()
        
        # Auf halbe Größe skalieren
        scaled_w = w - w*1/3
        scaled_h = h - h*1/3
        scaled_frame = pygame.transform.scale(current_frame, (scaled_w, scaled_h))
        
        # Münze nach oben verschieben, damit sie "in der Luft schwebt"
        # Angenommen, sie soll um die Hälfte der Größen-Differenz nach oben:
        diff_y = (h - scaled_h) // 2
        
        # Render-Position berechnen
        render_x = self.pos[0] - offset[0]
        render_y = self.pos[1] - offset[1] + diff_y  # nach oben schieben
        
        surf.blit(scaled_frame, (render_x, render_y))