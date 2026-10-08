import pygame

class MenuBar:
    def __init__(self, width):
        self.width = width
        self.height = 30
        self.font = pygame.font.Font(None, 22)
        self.file_rect = pygame.Rect(5, 2, 110, 26)
        self.cat_rect = pygame.Rect(120, 2, 130, 26)
        self.hier_rect = pygame.Rect(255, 2, 130, 26)

    def draw(self, surface, current_mode):
        pygame.draw.rect(surface, (35, 35, 35), (0, 0, self.width, self.height))
        pygame.draw.line(surface, (60, 60, 60), (0, self.height), (self.width, self.height), 1)

        m_pos = pygame.mouse.get_pos()

        f_color = (60, 60, 60) if self.file_rect.collidepoint(m_pos) else (45, 45, 45)
        pygame.draw.rect(surface, f_color, self.file_rect, border_radius=4)
        t_file = self.font.render("Abrir Vídeo(s)...", True, (220, 220, 220))
        surface.blit(t_file, t_file.get_rect(center=self.file_rect.center))

        cat_active = (current_mode == "CATEGORICAL")
        c_color = (0, 120, 215) if cat_active else ((60, 60, 60) if self.cat_rect.collidepoint(m_pos) else (45, 45, 45))
        pygame.draw.rect(surface, c_color, self.cat_rect, border_radius=4)
        t_cat = self.font.render("Modo Categórico", True, (255, 255, 255) if cat_active else (200, 200, 200))
        surface.blit(t_cat, t_cat.get_rect(center=self.cat_rect.center))

        hier_active = (current_mode == "HIERARCHICAL")
        h_color = (0, 120, 215) if hier_active else ((60, 60, 60) if self.hier_rect.collidepoint(m_pos) else (45, 45, 45))
        pygame.draw.rect(surface, h_color, self.hier_rect, border_radius=4)
        t_hier = self.font.render("Modo Hierárquico", True, (255, 255, 255) if hier_active else (200, 200, 200))
        surface.blit(t_hier, t_hier.get_rect(center=self.hier_rect.center))

    def handle_click(self, pos):
        if self.file_rect.collidepoint(pos):
            return "Abrir Vídeo(s)..."
        elif self.cat_rect.collidepoint(pos):
            return "CATEGORICAL"
        elif self.hier_rect.collidepoint(pos):
            return "HIERARCHICAL"
        return None


class LabelPanel:
    def __init__(self, x, y, w, h):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.Font(None, 22)
        self.title_font = pygame.font.Font(None, 24)
        self.label_rects = {}

    def draw(self, surface, model):
        pygame.draw.rect(surface, (28, 28, 28), self.rect, border_radius=6)
        pygame.draw.rect(surface, (50, 50, 50), self.rect, width=1, border_radius=6)

        title = self.title_font.render("Painel de Rótulos", True, (220, 220, 220))
        surface.blit(title, (self.rect.x + 10, self.rect.y + 10))

        y_offset = self.rect.y + 40
        self.label_rects.clear()

        labels = getattr(model, 'available_labels', ["Classe A", "Classe B", "Classe C", "Classe D"])
        colors = getattr(model, 'label_colors', {
            "Classe A": (220, 70, 70),
            "Classe B": (70, 180, 70),
            "Classe C": (70, 130, 220),
            "Classe D": (220, 180, 50)
        })

        for lbl in labels:
            r = pygame.Rect(self.rect.x + 10, y_offset, self.rect.width - 20, 32)
            self.label_rects[lbl] = r

            is_sel = (getattr(model, 'selected_label', None) == lbl)
            bg_col = (50, 50, 70) if is_sel else (38, 38, 38)
            border_col = (100, 150, 255) if is_sel else (60, 60, 60)

            pygame.draw.rect(surface, bg_col, r, border_radius=4)
            pygame.draw.rect(surface, border_col, r, width=2 if is_sel else 1, border_radius=4)

            dot_col = colors.get(lbl, (180, 180, 180))
            pygame.draw.circle(surface, dot_col, (r.x + 16, r.centery), 6)

            txt = self.font.render(lbl, True, (240, 240, 240) if is_sel else (180, 180, 180))
            surface.blit(txt, (r.x + 32, r.centery - txt.get_height() // 2))

            y_offset += 38


class MultiTrackTimeline:
    def __init__(self, x, y, w, h):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.Font(None, 18)
        self.header_w = 160
        self.eye_rects = {}

    def draw_eye_icon(self, surface, rect, status):
        center_x, center_y = rect.center
        
        if status == 'prohibited':
            # Ícone de Proibido 🚫
            r = 7
            pygame.draw.circle(surface, (200, 50, 50), (center_x, center_y), r, width=2)
            pygame.draw.line(surface, (200, 50, 50), (center_x - 4, center_y - 4), (center_x + 4, center_y + 4), width=2)
        else:
            # Ícone do Olho 👁️
            eye_color = (0, 200, 120) if status == 'active' else (120, 120, 120)
            pupil_color = (255, 255, 255) if status == 'active' else (160, 160, 160)
            
            eye_box = pygame.Rect(center_x - 9, center_y - 5, 18, 10)
            pygame.draw.ellipse(surface, eye_color, eye_box, width=2)
            pygame.draw.circle(surface, pupil_color, (center_x, center_y), 2)

    def draw(self, surface, engine, model, current_frame, zoom_level=1.0):
        pygame.draw.rect(surface, (25, 25, 25), self.rect, border_radius=6)
        pygame.draw.rect(surface, (50, 50, 50), self.rect, width=1, border_radius=6)

        total_frames = max(1, engine.get_total_timeline_frames())
        track_x = self.rect.x + self.header_w
        track_w = self.rect.width - self.header_w - 10

        self.eye_rects.clear()

        pygame.draw.line(surface, (50, 50, 50), (track_x - 5, self.rect.y), (track_x - 5, self.rect.bottom), 1)

        num_clips = len(engine.clips)
        if num_clips == 0:
            msg = self.font.render("Nenhum vídeo carregado na linha do tempo", True, (100, 100, 100))
            surface.blit(msg, msg.get_rect(center=(self.rect.centerx + self.header_w // 2, self.rect.centery)))
            return

        enabled_count = len(engine.get_enabled_clips())
        row_h = max(26, (self.rect.height - 15) // num_clips)

        for i, clip in enumerate(engine.clips):
            row_y = self.rect.y + 8 + i * row_h
            
            # Botão de Olho
            eye_r = pygame.Rect(self.rect.x + 8, row_y + (row_h - 20) // 2, 24, 20)
            self.eye_rects[i] = eye_r

            m_pos = pygame.mouse.get_pos()
            bg_eye = (45, 45, 45) if eye_r.collidepoint(m_pos) else (32, 32, 32)
            pygame.draw.rect(surface, bg_eye, eye_r, border_radius=4)
            pygame.draw.rect(surface, (60, 60, 60), eye_r, width=1, border_radius=4)

            if clip.enabled:
                status = 'active'
            elif enabled_count >= 2:
                status = 'prohibited'
            else:
                status = 'inactive'

            self.draw_eye_icon(surface, eye_r, status)

            # Nome da Trilha
            txt_name = clip.filename
            if len(txt_name) > 15:
                txt_name = txt_name[:12] + "..."
            lbl_surf = self.font.render(f"T{i+1}: {txt_name}", True, (220, 220, 220) if clip.enabled else (120, 120, 120))
            surface.blit(lbl_surf, (self.rect.x + 36, row_y + (row_h - lbl_surf.get_height()) // 2))

            # Barra da Trilha Paralela
            track_bar_r = pygame.Rect(track_x, row_y + 2, track_w, row_h - 4)
            pygame.draw.rect(surface, (35, 35, 35), track_bar_r, border_radius=3)

            clip_ratio = clip.duration_frames / float(total_frames)
            clip_fill_w = int(track_w * clip_ratio)
            clip_fill_r = pygame.Rect(track_x, row_y + 3, clip_fill_w, row_h - 6)

            clip_color = (40, 90, 140) if clip.enabled else (50, 50, 50)
            pygame.draw.rect(surface, clip_color, clip_fill_r, border_radius=3)
            pygame.draw.rect(surface, (70, 130, 190) if clip.enabled else (70, 70, 70), clip_fill_r, width=1, border_radius=3)

        # Agulha da Timeline
        playhead_x = track_x + int((current_frame / float(total_frames)) * track_w)
        playhead_x = max(track_x, min(track_x + track_w, playhead_x))

        pygame.draw.line(surface, (255, 60, 60), (playhead_x, self.rect.y + 4), (playhead_x, self.rect.bottom - 4), 2)
        pygame.draw.polygon(surface, (255, 60, 60), [
            (playhead_x - 4, self.rect.y + 2),
            (playhead_x + 4, self.rect.y + 2),
            (playhead_x, self.rect.y + 7)
        ])

    def handle_click(self, pos, engine):
        for idx, rect in self.eye_rects.items():
            if rect.collidepoint(pos):
                engine.toggle_clip_enabled(idx)
                return True
        return False