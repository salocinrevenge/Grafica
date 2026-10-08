import pygame
from models import AnnotationModel

class MultiTrackTimeline:
    def __init__(self, x, y, w, h):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.Font(None, 18)
        self.header_w = 160
        self.eye_rects = {}
        self.scroll_offset_x = 0  # Offset de rolagem horizontal em pixels

    def draw_eye_icon(self, surface, rect, status):
        center_x, center_y = rect.center
        if status == 'prohibited':
            r = 7
            pygame.draw.circle(surface, (200, 50, 50), (center_x, center_y), r, width=2)
            pygame.draw.line(surface, (200, 50, 50), (center_x - 4, center_y - 4), (center_x + 4, center_y + 4), width=2)
        else:
            eye_color = (0, 200, 120) if status == 'active' else (120, 120, 120)
            pupil_color = (255, 255, 255) if status == 'active' else (160, 160, 160)
            eye_box = pygame.Rect(center_x - 9, center_y - 5, 18, 10)
            pygame.draw.ellipse(surface, eye_color, eye_box, width=2)
            pygame.draw.circle(surface, pupil_color, (center_x, center_y), 2)

    def draw(self, surface, engine, model, current_frame, selected_clip=None, zoom_level=1.0):
        pygame.draw.rect(surface, (25, 25, 25), self.rect, border_radius=6)
        pygame.draw.rect(surface, (50, 50, 50), self.rect, width=1, border_radius=6)

        total_frames = max(1, engine.get_total_timeline_frames())
        track_x = self.rect.x + self.header_w
        track_w = self.rect.width - self.header_w - 10

        virtual_track_w = int(track_w * zoom_level)
        max_scroll = max(0, virtual_track_w - track_w)
        self.scroll_offset_x = max(0, min(self.scroll_offset_x, max_scroll))

        self.eye_rects.clear()
        
        # Área de exibição recortada (não vaza para o cabeçalho)
        track_clip_rect = pygame.Rect(track_x, self.rect.y, track_w, self.rect.height)
        surface.set_clip(track_clip_rect)

        num_video_tracks = engine.get_num_tracks()
        total_rows = max(1, num_video_tracks + 1)  # 1 linha para Anotações + N para Vídeos
        row_h = max(22, (self.rect.height - 15) // total_rows)

        # --- 1. DESENHAR TRILHA DE ANOTAÇÃO (Primeira linha) ---
        ann_row_y = self.rect.y + 8
        ann_bar_r = pygame.Rect(track_x, ann_row_y + 2, track_w, row_h - 4)
        pygame.draw.rect(surface, (30, 30, 35), ann_bar_r, border_radius=3)

        if model.mode == AnnotationModel.MODE_HIERARCHICAL:
            segments = model.get_hierarchical_segments()
            palette = [(180, 80, 40), (60, 120, 180), (140, 60, 160), (50, 150, 100)]
            for idx, (s_start, s_end) in enumerate(segments):
                rel_start = s_start / float(total_frames)
                rel_dur = (s_end - s_start) / float(total_frames)
                px = track_x + int(rel_start * virtual_track_w) - self.scroll_offset_x
                pw = max(2, int(rel_dur * virtual_track_w))
                
                seg_r = pygame.Rect(px, ann_row_y + 3, pw, row_h - 6)
                col = palette[idx % len(palette)]
                pygame.draw.rect(surface, col, seg_r, border_radius=2)
                pygame.draw.rect(surface, (220, 220, 220), seg_r, width=1, border_radius=2)

                if pw > 35:
                    lbl = self.font.render(f"Ep. {idx+1}", True, (255, 255, 255))
                    surface.blit(lbl, (px + 4, ann_row_y + (row_h - lbl.get_height()) // 2))

        elif model.mode == AnnotationModel.MODE_CATEGORICAL:
            if len(model.series) > 0:
                curr_lbl_id = model.series[0]
                start_f = 0
                for f in range(1, len(model.series)):
                    lbl_id = model.series[f]
                    if lbl_id != curr_lbl_id or f == len(model.series) - 1:
                        if curr_lbl_id != -1:
                            rel_start = start_f / float(total_frames)
                            rel_dur = (f - start_f) / float(total_frames)
                            px = track_x + int(rel_start * virtual_track_w) - self.scroll_offset_x
                            pw = max(2, int(rel_dur * virtual_track_w))
                            seg_r = pygame.Rect(px, ann_row_y + 3, pw, row_h - 6)
                            col = model._get_color(curr_lbl_id)
                            pygame.draw.rect(surface, col, seg_r, border_radius=2)
                        start_f = f
                        curr_lbl_id = lbl_id

        # --- 2. DESENHAR TRILHAS DE VÍDEO ---
        if num_video_tracks > 0:
            for t_idx in range(num_video_tracks):
                row_y = ann_row_y + (t_idx + 1) * row_h
                is_en = engine.is_track_enabled(t_idx)

                track_bar_r = pygame.Rect(track_x, row_y + 2, track_w, row_h - 4)
                pygame.draw.rect(surface, (35, 35, 35), track_bar_r, border_radius=3)

                for clip in engine.clips:
                    if clip.track_idx == t_idx:
                        rel_start = clip.timeline_start / float(total_frames)
                        rel_dur = clip.duration_frames / float(total_frames)

                        clip_px = track_x + int(rel_start * virtual_track_w) - self.scroll_offset_x
                        clip_pw = max(4, int(rel_dur * virtual_track_w))
                        clip_r = pygame.Rect(clip_px, row_y + 3, clip_pw, row_h - 6)

                        is_sel = (selected_clip == clip)
                        if is_sel:
                            fill_color = (60, 140, 200) if is_en else (80, 80, 80)
                            border_color = (255, 220, 50)
                            border_w = 2
                        else:
                            fill_color = (40, 90, 140) if is_en else (50, 50, 50)
                            border_color = (70, 130, 190) if is_en else (70, 70, 70)
                            border_w = 1

                        pygame.draw.rect(surface, fill_color, clip_r, border_radius=3)
                        pygame.draw.rect(surface, border_color, clip_r, width=border_w, border_radius=3)

                        if clip_pw > 30:
                            txt_name = clip.filename
                            if len(txt_name) > 12:
                                txt_name = txt_name[:9] + "..."
                            txt_s = self.font.render(txt_name, True, (255, 255, 255) if is_en else (160, 160, 160))
                            surface.blit(txt_s, (clip_px + 4, row_y + (row_h - txt_s.get_height()) // 2))

            # AGULHA (Playhead)
            playhead_x = track_x + int((current_frame / float(total_frames)) * virtual_track_w) - self.scroll_offset_x
            if track_x <= playhead_x <= track_x + track_w:
                pygame.draw.line(surface, (255, 60, 60), (playhead_x, self.rect.y + 4), (playhead_x, self.rect.bottom - 4), 2)
                pygame.draw.polygon(surface, (255, 60, 60), [
                    (playhead_x - 4, self.rect.y + 2),
                    (playhead_x + 4, self.rect.y + 2),
                    (playhead_x, self.rect.y + 7)
                ])

        surface.set_clip(None)

        # --- 3. CABEÇALHO ESTÁTICO (Fixo na esquerda) ---
        pygame.draw.rect(surface, (25, 25, 25), (self.rect.x, self.rect.y, self.header_w - 5, self.rect.height), border_radius=6)
        pygame.draw.line(surface, (50, 50, 50), (track_x - 5, self.rect.y), (track_x - 5, self.rect.bottom), 1)

        # Rótulo do Cabeçalho de Anotações
        lbl_ann = self.font.render("Trilha Anotação", True, (255, 200, 100))
        surface.blit(lbl_ann, (self.rect.x + 12, ann_row_y + (row_h - lbl_ann.get_height()) // 2))

        if num_video_tracks == 0:
            msg = self.font.render("Nenhum vídeo carregado na linha do tempo", True, (100, 100, 100))
            surface.blit(msg, msg.get_rect(center=(self.rect.centerx + self.header_w // 2, self.rect.centery)))
            return

        enabled_count = sum(1 for t in range(num_video_tracks) if engine.is_track_enabled(t))
        m_pos = pygame.mouse.get_pos()

        for t_idx in range(num_video_tracks):
            row_y = ann_row_y + (t_idx + 1) * row_h
            eye_r = pygame.Rect(self.rect.x + 8, row_y + (row_h - 20) // 2, 24, 20)
            self.eye_rects[t_idx] = eye_r

            bg_eye = (45, 45, 45) if eye_r.collidepoint(m_pos) else (32, 32, 32)
            pygame.draw.rect(surface, bg_eye, eye_r, border_radius=4)
            pygame.draw.rect(surface, (60, 60, 60), eye_r, width=1, border_radius=4)

            is_en = engine.is_track_enabled(t_idx)
            status = 'active' if is_en else ('prohibited' if enabled_count >= 2 else 'inactive')
            self.draw_eye_icon(surface, eye_r, status)

            lbl_surf = self.font.render(f"Trilha Vídeo {t_idx + 1}", True, (220, 220, 220) if is_en else (120, 120, 120))
            surface.blit(lbl_surf, (self.rect.x + 36, row_y + (row_h - lbl_surf.get_height()) // 2))

    def handle_eye_click(self, pos, engine):
        for t_idx, rect in self.eye_rects.items():
            if rect.collidepoint(pos):
                engine.toggle_track_enabled(t_idx)
                return True
        return False

    def get_clip_and_frame_at_pixel(self, pos, engine, zoom_level=1.0):
        track_x = self.rect.x + self.header_w
        track_w = self.rect.width - self.header_w - 10
        total_frames = max(1, engine.get_total_timeline_frames())

        if not (track_x <= pos[0] <= track_x + track_w) or not (self.rect.y <= pos[1] <= self.rect.bottom):
            return None, None

        virtual_track_w = int(track_w * zoom_level)
        click_px_relative = pos[0] - track_x + self.scroll_offset_x
        rel_x = click_px_relative / float(virtual_track_w)
        clicked_frame = int(rel_x * total_frames)

        num_tracks = engine.get_num_tracks()
        if num_tracks == 0:
            return None, clicked_frame

        total_rows = max(1, num_tracks + 1)
        row_h = max(22, (self.rect.height - 15) // total_rows)
        row_idx = int((pos[1] - (self.rect.y + 8)) // row_h)

        if row_idx == 0:
            return None, clicked_frame

        t_idx = row_idx - 1
        if 0 <= t_idx < num_tracks:
            for clip in engine.clips:
                if clip.track_idx == t_idx and clip.timeline_start <= clicked_frame < clip.timeline_end:
                    return clip, clicked_frame

        return None, clicked_frame