import os
os.environ["OPENCV_FFMPEG_THREAD_COUNT"] = "1"

import pygame
import cv2
import json
import threading

from models import AnnotationModel
from video_engine import MultiVideoEngine, VideoClip
from ui_components import MenuBar, LabelPanel
from timeline_widget import MultiTrackTimeline
from modals import ConfirmationModal
from file_utils import FileDialogHelper
from viewport_manager import ViewportManager

class VideoLabelerApp:
    def __init__(self):
        pygame.init()
        self.screen_w = 1280
        self.screen_h = 800
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)
        pygame.display.set_caption("VideoLabeler Pro - Editor Multi-Trilha & Anotação")

        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 22)

        self.engine = MultiVideoEngine()
        self.model = AnnotationModel()
        self.viewport_mgr = ViewportManager(self.font)

        self.current_frame = 0
        self.playing = False
        self.zoom_level = 1.0  # Nível de Zoom inicial (1.0x)
        self.pending_mode_change = None
        self.active_modal = None

        self.active_tool = "ibeam"
        self.selected_clip = None
        self.is_dragging_clip = False
        self.is_dragging_playhead = False
        self.drag_start_x = 0
        self.drag_initial_start = 0

        self.is_loading_files = False
        self.pending_video_paths = None
        self.pending_project_load = None

        self.update_layout()

    def update_layout(self):
        self.menu_bar = MenuBar(self.screen_w)
        self.viewport_mgr.update_dimensions(self.screen_w, self.screen_h)

        panel_w = 260
        self.label_panel = LabelPanel(self.screen_w - panel_w - 10, 35, panel_w, self.screen_h - 225)

        timeline_h = 135
        self.timeline = MultiTrackTimeline(10, self.screen_h - timeline_h - 10, self.screen_w - 20, timeline_h)

        ctrl_y = self.screen_h - timeline_h - 48
        self.btn_play_rect = pygame.Rect(10, ctrl_y, 75, 30)
        
        # Botões de Ferramentas
        self.btn_tool_ibeam = pygame.Rect(90, ctrl_y, 35, 30)
        self.btn_tool_arrow = pygame.Rect(130, ctrl_y, 35, 30)
        self.btn_tool_cut = pygame.Rect(170, ctrl_y, 35, 30)

        # Botões de Zoom (+) e (-) do lado das ferramentas
        self.btn_zoom_in = pygame.Rect(215, ctrl_y, 30, 30)
        self.btn_zoom_out = pygame.Rect(250, ctrl_y, 30, 30)

        # Botões do Modo Hierárquico
        self.btn_cut_rect = pygame.Rect(290, ctrl_y, 100, 30)
        self.btn_undo_rect = pygame.Rect(400, ctrl_y, 110, 30)

    def request_mode_change(self, new_mode):
        self.model.mode = new_mode

    def apply_zoom(self, delta_zoom, mouse_pos=None):
        old_zoom = self.zoom_level
        new_zoom = max(1.0, min(10.0, round(old_zoom + delta_zoom, 1)))
        if new_zoom == old_zoom:
            return

        track_x = self.timeline.rect.x + self.timeline.header_w
        track_w = self.timeline.rect.width - self.timeline.header_w - 10
        total_frames = max(1, self.engine.get_total_timeline_frames())

        # Se o cursor estiver sobre a área de trilhas da linha do tempo
        if mouse_pos and track_x <= mouse_pos[0] <= track_x + track_w and self.timeline.rect.y <= mouse_pos[1] <= self.timeline.rect.bottom:
            offset_in_view = mouse_pos[0] - track_x
            virtual_x_old = offset_in_view + self.timeline.scroll_offset_x
            virtual_x_new = virtual_x_old * (new_zoom / old_zoom)
            new_scroll = virtual_x_new - offset_in_view
        else:
            # Caso o zoom seja alterado via botões, centraliza na agulha (playhead)
            playhead_ratio = self.current_frame / float(total_frames)
            virtual_playhead_new = playhead_ratio * (track_w * new_zoom)
            new_scroll = virtual_playhead_new - (track_w / 2)

        virtual_track_w_new = int(track_w * new_zoom)
        max_scroll = max(0, virtual_track_w_new - track_w)
        self.timeline.scroll_offset_x = max(0, min(int(new_scroll), max_scroll))
        self.zoom_level = new_zoom

    # --- Salvar / Carregar Projeto Assíncrono ---
    def open_file_dialog_async(self):
        if self.is_loading_files:
            return
        self.is_loading_files = True
        threading.Thread(target=self._file_dialog_worker, daemon=True).start()

    def _file_dialog_worker(self):
        paths = FileDialogHelper.select_video_files()
        self.pending_video_paths = paths
        self.is_loading_files = False

    def save_project_async(self):
        if self.is_loading_files:
            return
        self.is_loading_files = True
        threading.Thread(target=self._save_project_worker, daemon=True).start()

    def _save_project_worker(self):
        save_path = FileDialogHelper.select_save_project_file()
        if save_path:
            project_data = {
                "version": "1.0",
                "current_frame": self.current_frame,
                "zoom_level": self.zoom_level,
                "model_mode": getattr(self.model, "mode", AnnotationModel.MODE_CATEGORICAL),
                "engine": self.engine.to_dict(),
                "categorical_annotations": getattr(self.model, "categorical_annotations", {}),
                "hierarchical_cuts": getattr(self.model, "hierarchical_cuts", [])
            }
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=4)
        self.is_loading_files = False

    def load_project_async(self):
        if self.is_loading_files:
            return
        self.is_loading_files = True
        threading.Thread(target=self._load_project_worker, daemon=True).start()

    def _load_project_worker(self):
        load_path = FileDialogHelper.select_open_project_file()
        if load_path and os.path.exists(load_path):
            with open(load_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.pending_project_load = data
        self.is_loading_files = False

    def process_pending_events(self):
        if self.pending_video_paths is not None:
            paths = self.pending_video_paths
            self.pending_video_paths = None
            if paths:
                self.playing = False
                self.engine.clear()
                self.selected_clip = None

                for idx, path in enumerate(paths):
                    cap = cv2.VideoCapture(path)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    cap.release()

                    clip = VideoClip(path, idx, fps, total_f, track_idx=idx)
                    self.engine.add_clip(clip)

                self.model.set_total_frames(self.engine.get_total_timeline_frames())
                self.current_frame = 0

        if self.pending_project_load is not None:
            data = self.pending_project_load
            self.pending_project_load = None
            
            self.playing = False
            self.engine.load_dict(data.get("engine", {}))
            self.model.mode = data.get("model_mode", AnnotationModel.MODE_CATEGORICAL)
            self.model.categorical_annotations = data.get("categorical_annotations", {})
            self.model.hierarchical_cuts = data.get("hierarchical_cuts", [])
            self.model.set_total_frames(self.engine.get_total_timeline_frames())
            self.current_frame = data.get("current_frame", 0)
            self.zoom_level = data.get("zoom_level", 1.0)
            self.selected_clip = None

    def draw_controls(self):
        m_pos = pygame.mouse.get_pos()

        # Botão PLAY
        play_color = (60, 140, 60) if self.btn_play_rect.collidepoint(m_pos) else ((50, 120, 50) if self.playing else (70, 70, 70))
        pygame.draw.rect(self.screen, play_color, self.btn_play_rect, border_radius=4)
        t_play = self.font.render("PAUSE" if self.playing else "PLAY", True, (255, 255, 255))
        self.screen.blit(t_play, t_play.get_rect(center=self.btn_play_rect.center))

        # Desenho dos Botões de Ferramenta
        tools = [
            ("ibeam", self.btn_tool_ibeam),
            ("arrow", self.btn_tool_arrow),
            ("cut", self.btn_tool_cut)
        ]

        for tool_id, rect in tools:
            is_active = (self.active_tool == tool_id)
            is_hover = rect.collidepoint(m_pos)
            bg_col = (0, 120, 215) if is_active else ((60, 60, 60) if is_hover else (40, 40, 40))
            border_col = (100, 180, 255) if is_active else (60, 60, 60)

            pygame.draw.rect(self.screen, bg_col, rect, border_radius=4)
            pygame.draw.rect(self.screen, border_col, rect, width=1, border_radius=4)

            cx, cy = rect.center
            icon_col = (255, 255, 255) if is_active or is_hover else (180, 180, 180)

            if tool_id == "ibeam":
                pygame.draw.line(self.screen, icon_col, (cx, cy - 7), (cx, cy + 7), 2)
                pygame.draw.line(self.screen, icon_col, (cx - 4, cy - 7), (cx + 4, cy - 7), 2)
                pygame.draw.line(self.screen, icon_col, (cx - 4, cy + 7), (cx + 4, cy + 7), 2)
            elif tool_id == "arrow":
                arrow_pts = [(cx - 4, cy - 7), (cx - 4, cy + 7), (cx + 5, cy + 1)]
                pygame.draw.polygon(self.screen, icon_col, arrow_pts)
                pygame.draw.polygon(self.screen, (0, 0, 0), arrow_pts, width=1)
            elif tool_id == "cut":
                pygame.draw.circle(self.screen, icon_col, (cx - 4, cy + 4), 3, width=1)
                pygame.draw.circle(self.screen, icon_col, (cx + 4, cy + 4), 3, width=1)
                pygame.draw.line(self.screen, icon_col, (cx - 4, cy + 4), (cx + 5, cy - 6), 2)
                pygame.draw.line(self.screen, icon_col, (cx + 4, cy + 4), (cx - 5, cy - 6), 2)

        # Botões de ZOOM (+) e (-)
        for b_rect, symbol in [(self.btn_zoom_in, "+"), (self.btn_zoom_out, "-")]:
            is_hover = b_rect.collidepoint(m_pos)
            bg_col = (70, 70, 70) if is_hover else (45, 45, 45)
            pygame.draw.rect(self.screen, bg_col, b_rect, border_radius=4)
            pygame.draw.rect(self.screen, (70, 70, 70), b_rect, width=1, border_radius=4)
            t_sym = self.font.render(symbol, True, (255, 255, 255))
            self.screen.blit(t_sym, t_sym.get_rect(center=b_rect.center))

        t_zoom = self.font.render(f"Zoom: {self.zoom_level:.1f}x", True, (160, 160, 160))
        self.screen.blit(t_zoom, (self.btn_zoom_out.right + 10, self.btn_play_rect.centery - t_zoom.get_height() // 2))

        # Botões do Modo Hierárquico
        if self.model.mode == AnnotationModel.MODE_HIERARCHICAL:
            cut_color = (210, 90, 50) if self.btn_cut_rect.collidepoint(m_pos) else (180, 80, 40)
            pygame.draw.rect(self.screen, cut_color, self.btn_cut_rect, border_radius=4)
            t_cut = self.font.render("Cortar (C)", True, (255, 255, 255))
            self.screen.blit(t_cut, t_cut.get_rect(center=self.btn_cut_rect.center))

            undo_color = (150, 70, 170) if self.btn_undo_rect.collidepoint(m_pos) else (120, 60, 140)
            pygame.draw.rect(self.screen, undo_color, self.btn_undo_rect, border_radius=4)
            t_undo = self.font.render("Desfazer (Ctrl+Z)", True, (255, 255, 255))
            self.screen.blit(t_undo, t_undo.get_rect(center=self.btn_undo_rect.center))

        info = f"Frame: {self.current_frame} / {self.model.total_frames}"
        txt_info = self.font.render(info, True, (200, 200, 200))
        self.screen.blit(txt_info, (self.screen_w - 280 - txt_info.get_width(), self.btn_play_rect.centery - txt_info.get_height() // 2))


    def run(self):
        running = True
        while running:
            self.clock.tick(60)
            self.screen.fill((20, 20, 20))

            self.process_pending_events()

            # --- Navegação pelas Setas do Teclado ---
            keys = pygame.key.get_pressed()
            scroll_speed = 20
            track_w = self.timeline.rect.width - self.timeline.header_w - 10
            virtual_track_w = int(track_w * self.zoom_level)
            max_scroll = max(0, virtual_track_w - track_w)

            if keys[pygame.K_LEFT]:
                self.timeline.scroll_offset_x = max(0, self.timeline.scroll_offset_x - scroll_speed)
            elif keys[pygame.K_RIGHT]:
                self.timeline.scroll_offset_x = min(max_scroll, self.timeline.scroll_offset_x + scroll_speed)

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

                elif e.type == pygame.MOUSEWHEEL:
                    m_pos = pygame.mouse.get_pos()
                    if self.timeline.rect.collidepoint(m_pos):
                        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                            self.timeline.scroll_offset_x -= e.y * 30
                        else:
                            # Aplica Zoom mantendo a posição sob o mouse fixa
                            self.apply_zoom(0.2 if e.y > 0 else -0.2, mouse_pos=m_pos)

                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    pos = e.pos
                    menu_action = self.menu_bar.handle_click(pos)
                    if menu_action == "Abrir Vídeos":
                        self.open_file_dialog_async()
                    elif menu_action == "Salvar Projeto":
                        self.save_project_async()
                    elif menu_action == "Carregar Projeto":
                        self.load_project_async()
                    elif menu_action in [AnnotationModel.MODE_CATEGORICAL, AnnotationModel.MODE_HIERARCHICAL]:
                        self.request_mode_change(menu_action)

                    if self.btn_play_rect.collidepoint(pos):
                        self.playing = not self.playing

                    elif self.btn_tool_ibeam.collidepoint(pos):
                        self.active_tool = "ibeam"
                    elif self.btn_tool_arrow.collidepoint(pos):
                        self.active_tool = "arrow"
                    elif self.btn_tool_cut.collidepoint(pos):
                        self.active_tool = "cut"

                    elif self.btn_zoom_in.collidepoint(pos):
                        self.apply_zoom(0.5)
                    elif self.btn_zoom_out.collidepoint(pos):
                        self.apply_zoom(-0.5)

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
                        toggled = self.timeline.handle_eye_click(pos, self.engine)
                        if not toggled:
                            clip, clicked_frame = self.timeline.get_clip_and_frame_at_pixel(pos, self.engine, self.zoom_level)

                            if self.active_tool == "ibeam":
                                if clicked_frame is not None:
                                    self.current_frame = max(0, min(clicked_frame, max(1, self.engine.get_total_timeline_frames())))
                                    self.is_dragging_playhead = True

                            elif self.active_tool == "arrow":
                                if clip is not None:
                                    self.selected_clip = clip
                                    self.is_dragging_clip = True
                                    self.drag_start_x = pos[0]
                                    self.drag_initial_start = clip.timeline_start
                                else:
                                    self.selected_clip = None

                            elif self.active_tool == "cut":
                                if clip is not None and clicked_frame is not None:
                                    new_clip = clip.split(clicked_frame)
                                    if new_clip:
                                        self.engine.add_clip(new_clip)
                                        self.selected_clip = new_clip
                                        self.model.set_total_frames(self.engine.get_total_timeline_frames())

                elif e.type == pygame.MOUSEMOTION:
                    if self.active_tool == "ibeam" and getattr(self, 'is_dragging_playhead', False):
                        track_x = self.timeline.rect.x + self.timeline.header_w
                        track_w = self.timeline.rect.width - self.timeline.header_w - 10
                        total_f = max(1, self.engine.get_total_timeline_frames())
                        virtual_track_w = int(track_w * self.zoom_level)
                        rel_x = (e.pos[0] - track_x + self.timeline.scroll_offset_x) / float(virtual_track_w)
                        self.current_frame = max(0, min(total_f, int(rel_x * total_f)))

                    elif self.active_tool == "arrow" and self.is_dragging_clip and self.selected_clip:
                        track_w = self.timeline.rect.width - self.timeline.header_w - 10
                        total_f = max(1, self.engine.get_total_timeline_frames())
                        virtual_track_w = int(track_w * self.zoom_level)
                        delta_x = e.pos[0] - self.drag_start_x
                        delta_frames = int((delta_x / float(virtual_track_w)) * total_f)
                        self.selected_clip.timeline_start = max(0, self.drag_initial_start + delta_frames)
                        self.model.set_total_frames(self.engine.get_total_timeline_frames())

                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    self.is_dragging_clip = False
                    self.is_dragging_playhead = False

                elif e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                        if self.selected_clip is not None:
                            self.engine.delete_clip(self.selected_clip)
                            self.selected_clip = None
                            self.model.set_total_frames(self.engine.get_total_timeline_frames())

                    elif e.key == pygame.K_SPACE:
                        self.playing = not self.playing

            # Renderização
            self.viewport_mgr.render(self.screen, self.engine, self.current_frame, self.is_loading_files)
            self.draw_controls()

            if self.model.mode == AnnotationModel.MODE_CATEGORICAL:
                self.label_panel.draw(self.screen, self.model)

            self.timeline.draw(self.screen, self.engine, self.model, self.current_frame, self.selected_clip, self.zoom_level)
            self.menu_bar.draw(self.screen, self.model.mode)

            if self.active_modal:
                self.active_modal.draw()

            pygame.display.flip()

        pygame.quit()