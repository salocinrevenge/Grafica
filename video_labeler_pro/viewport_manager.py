import pygame

class ViewportManager:
    def __init__(self, font=None):
        self.font = font or pygame.font.Font(None, 22)
        self.rect = pygame.Rect(0, 0, 0, 0)

    def update_dimensions(self, screen_w, screen_h):
        area_x = 10
        area_y = 35
        area_w = screen_w - 280
        area_h = screen_h - 225
        self.rect = pygame.Rect(area_x, area_y, max(0, area_w), max(0, area_h))

    def render(self, surface, engine, current_frame, is_loading_files=False):
        active_clips = engine.get_active_clips_at_frame(current_frame)

        if self.rect.width <= 0 or self.rect.height <= 0:
            return

        if not active_clips:
            pygame.draw.rect(surface, (15, 15, 15), self.rect, border_radius=6)
            msg = "Aguardando seleção de vídeos..." if is_loading_files else "Nenhum vídeo ativo neste frame. Ligue o olho (👁️) de uma trilha."
            txt = self.font.render(msg, True, (160, 160, 160))
            surface.blit(txt, txt.get_rect(center=self.rect.center))
            return

        if len(active_clips) == 1:
            clip = active_clips[0]
            surf = clip.get_frame_surface(current_frame, target_height=self.rect.height)
            if surf:
                if surf.get_width() > self.rect.width:
                    scale_ratio = self.rect.width / float(surf.get_width())
                    surf = pygame.transform.scale(surf, (self.rect.width, int(surf.get_height() * scale_ratio)))

                v_x = self.rect.x + (self.rect.width - surf.get_width()) // 2
                v_y = self.rect.y + (self.rect.height - surf.get_height()) // 2
                surface.blit(surf, (v_x, v_y))

                t_lbl = self.font.render(f"Trilha {clip.track_idx + 1}: {clip.filename}", True, (200, 200, 200))
                pygame.draw.rect(surface, (0, 0, 0), (v_x + 5, v_y + 5, t_lbl.get_width() + 10, 22), border_radius=3)
                surface.blit(t_lbl, (v_x + 10, v_y + 8))

        elif len(active_clips) >= 2:
            gap = 10
            half_w = (self.rect.width - gap) // 2

            for i, clip in enumerate(active_clips[:2]):
                vp_x = self.rect.x + i * (half_w + gap)
                pygame.draw.rect(surface, (10, 10, 10), (vp_x, self.rect.y, half_w, self.rect.height), border_radius=4)

                surf = clip.get_frame_surface(current_frame, target_height=self.rect.height)
                if surf:
                    if surf.get_width() > half_w:
                        scale_ratio = half_w / float(surf.get_width())
                        surf = pygame.transform.scale(surf, (half_w, int(surf.get_height() * scale_ratio)))

                    v_x = vp_x + (half_w - surf.get_width()) // 2
                    v_y = self.rect.y + (self.rect.height - surf.get_height()) // 2
                    surface.blit(surf, (v_x, v_y))

                    t_lbl = self.font.render(f"Tela {i+1} (T{clip.track_idx + 1}): {clip.filename}", True, (220, 220, 220))
                    pygame.draw.rect(surface, (0, 0, 0), (vp_x + 5, self.rect.y + 5, t_lbl.get_width() + 10, 22), border_radius=3)
                    surface.blit(t_lbl, (vp_x + 10, self.rect.y + 8))