import pygame
from scripts.config import SCALER

class DisplayManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        display_info = pygame.display.Info()
        self.BASE_W = 640
        self.BASE_H = 360
        print(display_info.current_w, display_info.current_h)
        scale_x = display_info.current_w / self.BASE_W
        scale_y = display_info.current_h / self.BASE_H
        scale = min(scale_x, scale_y)
        scale *= SCALER
        if scale < 1:
            scale = 1
            
        self.WIN_W = int(self.BASE_W * scale)
        self.WIN_H = int(self.BASE_H * scale)
        
        self.WIN_W = min(self.WIN_W, display_info.current_w)
        self.WIN_H = min(self.WIN_H, display_info.current_h)
        self.scale = self.WIN_W / self.BASE_W