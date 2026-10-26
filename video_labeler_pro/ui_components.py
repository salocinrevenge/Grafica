import pygame
from models import AnnotationModel

class MenuBar:
    def __init__(self, screen_w):
        self.rect = pygame.Rect(0, 0, screen_w, 30)
        self.font = pygame.font.Font(None, 20)
        self.buttons = [
            ("Abrir Vídeos", pygame.Rect(10, 3, 90, 24)),
            ("Abrir Labels", pygame.Rect(105, 3, 95, 24)),
            ("Salvar Projeto", pygame.Rect(205, 3, 95, 24)),
            ("Carregar Projeto", pygame.Rect(305, 3, 105, 24)),
            ("Exportar", pygame.Rect(415, 3, 75, 24)),
            (AnnotationModel.MODE_CATEGORICAL, pygame.Rect(screen_w - 220, 3, 100, 24)),
            (AnnotationModel.MODE_HIERARCHICAL, pygame.Rect(screen_w - 115, 3, 105, 24))
        ]

    def draw(self, surface, current_mode):
        pygame.draw.rect(surface, (35, 35, 35), self.rect)
        pygame.draw.line(surface, (60, 60, 60), (0, 30), (self.rect.width, 30), 1)

        m_pos = pygame.mouse.get_pos()

        for label, rect in self.buttons:
            is_hover = rect.collidepoint(m_pos)
            is_active = (label == current_mode)

            if is_active:
                bg = (0, 120, 215)
                fg = (255, 255, 255)
            elif is_hover:
                bg = (60, 60, 60)
                fg = (255, 255, 255)
            else:
                bg = (45, 45, 45)
                fg = (200, 200, 200)

            pygame.draw.rect(surface, bg, rect, border_radius=4)
            
            disp_text = label
            if label == AnnotationModel.MODE_CATEGORICAL:
                disp_text = "Categorizado"
            elif label == AnnotationModel.MODE_HIERARCHICAL:
                disp_text = "Hierárquico"

            txt_surf = self.font.render(disp_text, True, fg)
            surface.blit(txt_surf, txt_surf.get_rect(center=rect.center))

    def handle_click(self, pos):
        for label, rect in self.buttons:
            if rect.collidepoint(pos):
                return label
        return None


class LabelPanel:
    def __init__(self, x, y, w, h):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.Font(None, 20)
        self.label_rects = {}

    def draw(self, surface, model):
        pygame.draw.rect(surface, (28, 28, 28), self.rect, border_radius=6)
        pygame.draw.rect(surface, (50, 50, 50), self.rect, width=1, border_radius=6)

        title = self.font.render("Categorias de Anotação", True, (220, 220, 220))
        surface.blit(title, (self.rect.x + 10, self.rect.y + 10))

        self.label_rects.clear()
        curr_y = self.rect.y + 35

        for idx, lbl in enumerate(model.available_labels):
            item_r = pygame.Rect(self.rect.x + 10, curr_y, self.rect.width - 20, 26)
            self.label_rects[lbl] = item_r

            is_sel = (model.selected_label == lbl)
            bg_col = (50, 80, 110) if is_sel else (38, 38, 38)
            border_col = (100, 180, 255) if is_sel else (55, 55, 55)

            pygame.draw.rect(surface, bg_col, item_r, border_radius=4)
            pygame.draw.rect(surface, border_col, item_r, width=1, border_radius=4)

            # Bolinha da cor associada
            lbl_id = model.label_map.get(lbl, idx)
            color = model._get_color(lbl_id)
            pygame.draw.circle(surface, color, (item_r.x + 15, item_r.centery), 6)

            txt = self.font.render(lbl, True, (255, 255, 255) if is_sel else (180, 180, 180))
            surface.blit(txt, (item_r.x + 30, item_r.centery - txt.get_height() // 2))

            curr_y += 30