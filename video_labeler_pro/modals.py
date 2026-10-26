import pygame

class ConfirmationModal:
    def __init__(self, width, height, font, message, on_confirm):
        self.width = width
        self.height = height
        self.font = font
        self.message = message
        self.on_confirm = on_confirm

        self.rect = pygame.Rect((width - 400) // 2, (height - 180) // 2, 400, 180)
        self.btn_ok = pygame.Rect(self.rect.centerx - 40, self.rect.bottom - 45, 80, 32)

    def handle_click(self, pos):
        if self.btn_ok.collidepoint(pos) and self.on_confirm:
            self.on_confirm()

    def draw(self, screen=None):
        target_screen = screen or pygame.display.get_surface()
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        target_screen.blit(overlay, (0, 0))

        pygame.draw.rect(target_screen, (35, 35, 35), self.rect, border_radius=8)
        pygame.draw.rect(target_screen, (70, 70, 70), self.rect, width=1, border_radius=8)

        txt = self.font.render(self.message, True, (240, 240, 240))
        target_screen.blit(txt, txt.get_rect(center=(self.rect.centerx, self.rect.y + 60)))

        m_pos = pygame.mouse.get_pos()
        btn_col = (0, 120, 215) if self.btn_ok.collidepoint(m_pos) else (0, 90, 170)
        pygame.draw.rect(target_screen, btn_col, self.btn_ok, border_radius=4)

        t_btn = self.font.render("OK", True, (255, 255, 255))
        target_screen.blit(t_btn, t_btn.get_rect(center=self.btn_ok.center))