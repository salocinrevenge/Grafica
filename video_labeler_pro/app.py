import os
os.environ["OPENCV_FFMPEG_THREAD_COUNT"] = "1"

import pygame
import cv2
import threading

from models import AnnotationModel
from video_engine import MultiVideoEngine, VideoClip
from ui_widgets import MenuBar, MultiTrackTimeline, LabelPanel
from dialogs import ConfirmationModal, FileDialogHelper

class VideoLabelerApp:
    def __init__(self):
        pygame.init()
        self.screen_w = 1280
        self.screen_h = 800
        # Habilita suporte a janela redimensionável (RESIZABLE)
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)
        pygame.display.set_caption("VideoLabeler Pro - Editor Multi-Trilha & Anotação")

        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 22)

        self.engine = MultiVideoEngine()
        self.model = AnnotationModel()

        self.current_frame = 0
        self.playing = False
        self.zoom_level = 1.0
        self.pending_mode_change = None
        self.active_modal = None

        self.is_loading_files = False
        self.pending_video_paths = None

        self.update_layout()

    def update_layout(self):
        """Recalcula posições e tamanhos dos componentes ao redimensionar a janela."""
        self.menu_bar = MenuBar(self.screen_w)
        
        panel_w = 260
        self.label_panel = LabelPanel(self.screen_w - panel_w - 10, 35, panel_w, self.screen_h - 225)

        timeline_h = 135
        self.timeline = MultiTrackTimeline(10, self.screen_h - timeline_h - 10, self.screen_w - 20, timeline_h)

        ctrl_y = self.screen_h - timeline_h - 48
        self.btn_play_rect = pygame.Rect(10, ctrl_y, 80, 30)
        self.btn_cut_rect = pygame.Rect(100, ctrl_y, 110, 30)
        self.btn_undo_rect = pygame.Rect(220, ctrl_y, 120, 30)

    def open_file_dialog_async(self):
        if self.is_loading_files:
            return
        self.is_loading_files = True
        thread = threading.Thread(target=self._file_dialog_worker, daemon=True)
        thread.start()

    def _file_dialog_worker(self):
        paths = FileDialogHelper.select_video_files()
        self.pending_video_paths = paths
        self.is_loading_files = False

    def process_pending_videos(self):
        if self.pending_video_paths is None:
            return

        paths = self.pending_video_paths
        self.pending_video_paths = None

        if not paths:
            return

        self.playing = False
        self.engine.clear()

        for idx, path in enumerate(paths):
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

            clip = VideoClip(path, idx, fps, total_f)
            # Ativa os 2 primeiros vídeos por padrão ao carregar
            clip.enabled = (idx < 2)
            self.engine.add_clip(clip)

        self.model.set_total_frames(self.engine.get_total_timeline_frames())
        self.current_frame = 0
        pygame.event.clear()

    def request_mode_change(self, target_mode):
        if target_mode == self.model.mode:
            return

        if target_mode == AnnotationModel.MODE_HIERARCHICAL:
            self.pending_mode_change = target_mode
            self.active_modal = ConfirmationModal(
                self.screen,
                "Aviso de Mudança de Modo",
                "Mudar para o modo Hierárquico irá resetar todas as anotações atuais. Pressione Enter para confirmar."
            )
        else:
            self.model.convert_hierarchical_to_categorical()
            self.model.mode = target_mode

    def draw_controls(self):
        m_pos = pygame.mouse.get_pos()

        play_color = (60, 140, 60) if self.btn_play_rect.collidepoint(m_pos) else ((50, 120, 50) if self.playing else (70, 70, 70))
        pygame.draw.rect(self.screen, play_color, self.btn_play_rect, border_radius=4)
        t_play = self.font.render("PAUSE" if self.playing else "PLAY", True, (255, 255, 255))
        self.screen.blit(t_play, t_play.get_rect(center=self.btn_play_rect.center))

        if self.model.mode == AnnotationModel.MODE_HIERARCHICAL:
            cut_color = (210, 90, 50) if self.btn_cut_rect.collidepoint(m_pos) else (180, 80, 40)
            pygame.draw.rect(self.screen, cut_color, self.btn_cut_rect, border_radius=4)
            t_cut = self.font.render("Cortar (C)", True, (255, 255, 255))
            self.screen.blit(t_cut, t_cut.get_rect(center=self.btn_cut_rect.center))

            undo_color = (150, 70, 170) if self.btn_undo_rect.collidepoint(m_pos) else (120, 60, 140)
            pygame.draw.rect(self.screen, undo_color, self.btn_undo_rect, border_radius=4)
            t_undo = self.font.render("Desfazer (Ctrl+Z)", True, (255, 255, 255))
            self.screen.blit(t_undo, t_undo.get_rect(center=self.btn_undo_rect.center))

        info = f"Frame Global: {self.current_frame} / {self.model.total_frames}"
        txt_info = self.font.render(info, True, (200, 200, 200))
        self.screen.blit(txt_info, (self.screen_w - 280 - txt_info.get_width(), self.btn_play_rect.centery - txt_info.get_height() // 2))

    def render_video_viewports(self):
        """Renderiza as telas de vídeo (1 centralizada ou 2 lado a lado)."""
        enabled_clips = self.engine.get_enabled_clips()

        area_x = 10
        area_y = 35
        area_w = self.screen_w - 280
        area_h = self.screen_h - 225

        if area_w <= 0 or area_h <= 0:
            return

        if not enabled_clips:
            pygame.draw.rect(self.screen, (15, 15, 15), (area_x, area_y, area_w, area_h), border_radius=6)
            msg = "Aguardando seleção de vídeos..." if self.is_loading_files else "Nenhum vídeo visível. Clique no olho (👁️) de uma trilha."
            txt = self.font.render(msg, True, (160, 160, 160))
            self.screen.blit(txt, txt.get_rect(center=(area_x + area_w // 2, area_y + area_h // 2)))
            return

        if len(enabled_clips) == 1:
            clip = enabled_clips[0]
            surf = clip.get_frame_surface(self.current_frame, target_height=area_h)
            if surf:
                if surf.get_width() > area_w:
                    scale_ratio = area_w / float(surf.get_width())
                    surf = pygame.transform.scale(surf, (area_w, int(surf.get_height() * scale_ratio)))
                
                v_x = area_x + (area_w - surf.get_width()) // 2
                v_y = area_y + (area_h - surf.get_height()) // 2
                self.screen.blit(surf, (v_x, v_y))
                
                t_lbl = self.font.render(f"Vídeo: {clip.filename}", True, (200, 200, 200))
                self.screen.blit(t_lbl, (v_x + 5, v_y + 5))

        elif len(enabled_clips) >= 2:
            gap = 10
            half_w = (area_w - gap) // 2

            for i, clip in enumerate(enabled_clips[:2]):
                vp_x = area_x + i * (half_w + gap)
                pygame.draw.rect(self.screen, (10, 10, 10), (vp_x, area_y, half_w, area_h), border_radius=4)

                surf = clip.get_frame_surface(self.current_frame, target_height=area_h)
                if surf:
                    if surf.get_width() > half_w:
                        scale_ratio = half_w / float(surf.get_width())
                        surf = pygame.transform.scale(surf, (half_w, int(surf.get_height() * scale_ratio)))

                    v_x = vp_x + (half_w - surf.get_width()) // 2
                    v_y = area_y + (area_h - surf.get_height()) // 2
                    self.screen.blit(surf, (v_x, v_y))

                    t_lbl = self.font.render(f"Tela {i+1}: {clip.filename}", True, (220, 220, 220))
                    pygame.draw.rect(self.screen, (0, 0, 0), (vp_x + 5, area_y + 5, t_lbl.get_width() + 10, 22), border_radius=3)
                    self.screen.blit(t_lbl, (vp_x + 10, area_y + 8))

    def run(self):
        running = True
        while running:
            self.clock.tick(60)
            self.screen.fill((20, 20, 20))

            self.process_pending_videos()

            if self.playing and not self.active_modal and not self.is_loading_files:
                self.current_frame += 1
                if self.current_frame >= self.model.total_frames:
                    self.current_frame = 0

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False

                elif e.type == pygame.VIDEORESIZE:
                    self.screen_w = e.w
                    self.screen_h = e.h
                    self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)
                    self.update_layout()

                if self.active_modal:
                    res = self.active_modal.handle_event(e)
                    if res is True:
                        self.model.reset_hierarchical()
                        self.model.mode = self.pending_mode_change
                        self.active_modal = None
                    elif res is False:
                        self.active_modal = None
                    continue

                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    pos = e.pos
                    menu_action = self.menu_bar.handle_click(pos)
                    if menu_action == "Abrir Vídeo(s)...":
                        self.open_file_dialog_async()
                    elif menu_action in [AnnotationModel.MODE_CATEGORICAL, AnnotationModel.MODE_HIERARCHICAL]:
                        self.request_mode_change(menu_action)

                    if self.btn_play_rect.collidepoint(pos):
                        self.playing = not self.playing

                    elif self.model.mode == AnnotationModel.MODE_HIERARCHICAL:
                        if self.btn_cut_rect.collidepoint(pos):
                            self.model.add_hierarchical_cut(self.current_frame)
                        elif self.btn_undo_rect.collidepoint(pos):
                            self.model.undo_hierarchical_cut()

                    if self.model.mode == AnnotationModel.MODE_CATEGORICAL:
                        for lbl, r in self.label_panel.label_rects.items():
                            if r.collidepoint(pos):
                                self.model.selected_label = lbl

                    if self.timeline.rect.collidepoint(pos):
                        toggled = self.timeline.handle_click(pos, self.engine)
                        if not toggled:
                            track_x = self.timeline.rect.x + self.timeline.header_w
                            track_w = self.timeline.rect.width - self.timeline.header_w - 10
                            if track_x <= pos[0] <= track_x + track_w:
                                rel_x = (pos[0] - track_x) / float(track_w)
                                self.current_frame = int(rel_x * max(1, self.engine.get_total_timeline_frames()))

                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
                    if self.timeline.rect.collidepoint(e.pos) and self.model.mode == AnnotationModel.MODE_HIERARCHICAL:
                        track_x = self.timeline.rect.x + self.timeline.header_w
                        track_w = self.timeline.rect.width - self.timeline.header_w - 10
                        if track_x <= e.pos[0] <= track_x + track_w:
                            rel_x = (e.pos[0] - track_x) / float(track_w)
                            self.model.add_hierarchical_cut(int(rel_x * max(1, self.engine.get_total_timeline_frames())))

                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_SPACE:
                        self.playing = not self.playing
                    elif e.key == pygame.K_c and self.model.mode == AnnotationModel.MODE_HIERARCHICAL:
                        self.model.add_hierarchical_cut(self.current_frame)
                    elif e.key == pygame.K_z and (e.mod & pygame.KMOD_CTRL):
                        if self.model.mode == AnnotationModel.MODE_HIERARCHICAL:
                            self.model.undo_hierarchical_cut()

            self.render_video_viewports()
            self.draw_controls()

            if self.model.mode == AnnotationModel.MODE_CATEGORICAL:
                self.label_panel.draw(self.screen, self.model)
            
            self.timeline.draw(self.screen, self.engine, self.model, self.current_frame, self.zoom_level)
            self.menu_bar.draw(self.screen, self.model.mode)

            if self.active_modal:
                self.active_modal.draw()

            pygame.display.flip()

        pygame.quit()