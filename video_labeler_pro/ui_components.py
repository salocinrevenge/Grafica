import pygame

class MenuBar:
    def __init__(self, width):
        self.width = width
        self.height = 30
        self.font = pygame.font.Font(None, 20)

        # Botões de Arquivo e Projeto
        self.btn_open = pygame.Rect(10, 3, 110, 24)
        self.btn_save_proj = pygame.Rect(125, 3, 110, 24)
        self.btn_load_proj = pygame.Rect(240, 3, 120, 24)

        # Botões de Modo
        self.btn_mode_cat = pygame.Rect(width - 240, 3, 110, 24)
        self.btn_mode_hier = pygame.Rect(width - 120, 3, 110, 24)

    def draw(self, surface, current_mode):
        pygame.draw.rect(surface, (30, 30, 30), (0, 0, self.width, self.height))
        pygame.draw.line(surface, (50, 50, 50), (0, self.height - 1), (self.width, self.height - 1))

        m_pos = pygame.mouse.get_pos()

        # Abrir Vídeo
        col_open = (60, 60, 60) if self.btn_open.collidepoint(m_pos) else (45, 45, 45)
        pygame.draw.rect(surface, col_open, self.btn_open, border_radius=4)
        t_open = self.font.render("Abrir Vídeos", True, (220, 220, 220))
        surface.blit(t_open, t_open.get_rect(center=self.btn_open.center))

        # Salvar Projeto
        col_save = (60, 60, 60) if self.btn_save_proj.collidepoint(m_pos) else (45, 45, 45)
        pygame.draw.rect(surface, col_save, self.btn_save_proj, border_radius=4)
        t_save = self.font.render("Salvar Projeto", True, (220, 220, 220))
        surface.blit(t_save, t_save.get_rect(center=self.btn_save_proj.center))

        # Carregar Projeto
        col_load = (60, 60, 60) if self.btn_load_proj.collidepoint(m_pos) else (45, 45, 45)
        pygame.draw.rect(surface, col_load, self.btn_load_proj, border_radius=4)
        t_load = self.font.render("Carregar Projeto", True, (220, 220, 220))
        surface.blit(t_load, t_load.get_rect(center=self.btn_load_proj.center))

        # Modo Categórico
        is_cat = (current_mode == "categorical")
        col_cat = (0, 120, 215) if is_cat else ((50, 50, 50) if self.btn_mode_cat.collidepoint(m_pos) else (38, 38, 38))
        pygame.draw.rect(surface, col_cat, self.btn_mode_cat, border_radius=4)
        t_cat = self.font.render("Categórico", True, (255, 255, 255) if is_cat else (180, 180, 180))
        surface.blit(t_cat, t_cat.get_rect(center=self.btn_mode_cat.center))

        # Modo Hierárquico
        is_hier = (current_mode == "hierarchical")
        col_hier = (0, 120, 215) if is_hier else ((50, 50, 50) if self.btn_mode_hier.collidepoint(m_pos) else (38, 38, 38))
        pygame.draw.rect(surface, col_hier, self.btn_mode_hier, border_radius=4)
        t_hier = self.font.render("Hierárquico", True, (255, 255, 255) if is_hier else (180, 180, 180))
        surface.blit(t_hier, t_hier.get_rect(center=self.btn_mode_hier.center))

    def handle_click(self, pos):
        if self.btn_open.collidepoint(pos):
            return "Abrir Vídeos"
        elif self.btn_save_proj.collidepoint(pos):
            return "Salvar Projeto"
        elif self.btn_load_proj.collidepoint(pos):
            return "Carregar Projeto"
        elif self.btn_mode_cat.collidepoint(pos):
            return "categorical"
        elif self.btn_mode_hier.collidepoint(pos):
            return "hierarchical"
        return None


class LabelPanel:
    def __init__(self, x, y, w, h):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.Font(None, 20)
        self.label_rects = {}

    def draw(self, surface, model):
        pygame.draw.rect(surface, (28, 28, 28), self.rect, border_radius=6)
        pygame.draw.rect(surface, (50, 50, 50), self.rect, width=1, border_radius=6)

        title = self.font.render("Rótulos Categóricos", True, (220, 220, 220))
        surface.blit(title, (self.rect.x + 12, self.rect.y + 12))

        self.label_rects.clear()
        curr_y = self.rect.y + 40

        # Obtém as categorias do modelo com fallback para lista vazia
        categories = getattr(model, 'CATEGORIES', [])

        for lbl in categories:
            btn_r = pygame.Rect(self.rect.x + 12, curr_y, self.rect.width - 24, 28)
            self.label_rects[lbl] = btn_r

            is_sel = (model.selected_label == lbl)
            bg_col = (0, 120, 215) if is_sel else (40, 40, 40)
            pygame.draw.rect(surface, bg_col, btn_r, border_radius=4)
            pygame.draw.rect(surface, (70, 70, 70), btn_r, width=1, border_radius=4)

            txt = self.font.render(lbl, True, (255, 255, 255) if is_sel else (180, 180, 180))
            surface.blit(txt, txt.get_rect(center=btn_r.center))

            curr_y += 34