import pygame

class ConfirmationModal:
    def __init__(self, surface, title, message, on_confirm, on_cancel):
        self.surface = surface
        self.title = title
        self.message = message
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.font_title = pygame.font.Font(None, 24)
        self.font_body = pygame.font.Font(None, 20)

        w, h = 380, 160
        sw, sh = surface.get_size()
        self.rect = pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h)

        self.btn_confirm = pygame.Rect(self.rect.x + 30, self.rect.bottom - 45, 140, 30)
        self.btn_cancel = pygame.Rect(self.rect.right - 170, self.rect.bottom - 45, 140, 30)

    def draw(self):
        # Fundo escuro semi-transparente
        overlay = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.surface.blit(overlay, (0, 0))

        # Janela do Modal
        pygame.draw.rect(self.surface, (35, 35, 35), self.rect, border_radius=8)
        pygame.draw.rect(self.surface, (70, 70, 70), self.rect, width=1, border_radius=8)

        # Título e Mensagem
        t_surf = self.font_title.render(self.title, True, (255, 255, 255))
        m_surf = self.font_body.render(self.message, True, (200, 200, 200))
        self.surface.blit(t_surf, (self.rect.x + 20, self.rect.y + 20))
        self.surface.blit(m_surf, (self.rect.x + 20, self.rect.y + 55))

        # Botões
        m_pos = pygame.mouse.get_pos()
        c_bg = (200, 60, 60) if self.btn_confirm.collidepoint(m_pos) else (160, 50, 50)
        a_bg = (70, 70, 70) if self.btn_cancel.collidepoint(m_pos) else (50, 50, 50)

        pygame.draw.rect(self.surface, c_bg, self.btn_confirm, border_radius=4)
        pygame.draw.rect(self.surface, a_bg, self.btn_cancel, border_radius=4)

        tc = self.font_body.render("Confirmar", True, (255, 255, 255))
        ta = self.font_body.render("Cancelar", True, (255, 255, 255))
        self.surface.blit(tc, tc.get_rect(center=self.btn_confirm.center))
        self.surface.blit(ta, ta.get_rect(center=self.btn_cancel.center))

    def handle_click(self, pos):
        if self.btn_confirm.collidepoint(pos):
            if self.on_confirm:
                self.on_confirm()
            return True
        elif self.btn_cancel.collidepoint(pos):
            if self.on_cancel:
                self.on_cancel()
            return True
        return False