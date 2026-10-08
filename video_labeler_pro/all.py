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

import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog

class FileDialogHelper:
    @staticmethod
    def _zenity_select(title, multiple=False, save=False):
        try:
            cmd = ["zenity", "--file-selection", f"--title={title}"]
            if multiple:
                cmd.extend(["--multiple", "--separator=|"])
            if save:
                cmd.extend(["--save", "--confirm-overwrite"])
            
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                out = res.stdout.strip()
                return [p for p in out.split("|") if p] if multiple else out
        except Exception:
            pass
        return None

    @staticmethod
    def select_video_files():
        if sys.platform.startswith("linux"):
            res = FileDialogHelper._zenity_select("Selecione um ou mais vídeos", multiple=True)
            if res is not None:
                return res

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        paths = filedialog.askopenfilenames(
            title="Selecione um ou mais vídeos",
            filetypes=[("Vídeos", "*.mp4 *.avi *.mov *.mkv"), ("Todos os arquivos", "*.*")]
        )
        root.destroy()
        return list(paths)

    @staticmethod
    def select_save_project_file():
        if sys.platform.startswith("linux"):
            res = FileDialogHelper._zenity_select("Salvar Projeto", save=True)
            if res:
                if not res.endswith(".json"):
                    res += ".json"
                return res

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(
            title="Salvar Projeto",
            defaultextension=".json",
            filetypes=[("Projeto VideoLabeler (*.json)", "*.json"), ("Todos os arquivos", "*.*")]
        )
        root.destroy()
        return path

    @staticmethod
    def select_open_project_file():
        if sys.platform.startswith("linux"):
            res = FileDialogHelper._zenity_select("Carregar Projeto")
            if res:
                return res

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="Carregar Projeto",
            filetypes=[("Projeto VideoLabeler (*.json)", "*.json"), ("Todos os arquivos", "*.*")]
        )
        root.destroy()
        return path

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

import os
import json
import colorsys
import numpy as np

class VideoClip:
    """Representa um clipe de vídeo posicionado na timeline principal."""
    def __init__(self, filepath, clip_id, fps, total_source_frames):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.clip_id = clip_id
        self.fps = fps
        self.total_source_frames = total_source_frames
        
        self.in_point = 0
        self.out_point = total_source_frames
        self.timeline_start = 0

    @property
    def duration_frames(self):
        return max(1, self.out_point - self.in_point)

    @property
    def timeline_end(self):
        return self.timeline_start + self.duration_frames

    def global_to_source_frame(self, global_frame):
        if self.timeline_start <= global_frame < self.timeline_end:
            rel_frame = global_frame - self.timeline_start
            return self.in_point + rel_frame
        return None


class Node:
    """Nó para representação hierárquica em árvore binária."""
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.left = None
        self.right = None
        self.group_id = None


class AnnotationModel:
    MODE_CATEGORICAL = "categorical"
    MODE_HIERARCHICAL = "hierarchical"

    DEFAULT_CATEGORIES = ["Ação", "Interação", "Objeto", "Cena", "Outro"]

    def __init__(self, total_timeline_frames=1800, fps=30.0):
        self.mode = self.MODE_CATEGORICAL
        self.total_frames = total_timeline_frames
        self.fps = fps
        
        self.series = np.full(self.total_frames + 1, -1, dtype=int)
        self.label_map = {"None": -1}
        self.color_map = {-1: (50, 50, 50)}
        self.available_labels = list(self.DEFAULT_CATEGORIES)
        self.selected_label = self.available_labels[0] if self.available_labels else None

        self.cuts_history = []

    @property
    def CATEGORIES(self):
        return self.available_labels

    @property
    def categorical_annotations(self):
        annotations = {}
        id_to_label = {v: k for k, v in self.label_map.items()}
        for idx, val in enumerate(self.series):
            if val != -1 and val in id_to_label:
                annotations[str(idx)] = id_to_label[val]
        return annotations

    @categorical_annotations.setter
    def categorical_annotations(self, annotations_dict):
        self.reset_categorical()
        if not isinstance(annotations_dict, dict):
            return

        for frame_str, lbl_name in annotations_dict.items():
            try:
                frame_idx = int(frame_str)
            except (ValueError, TypeError):
                continue

            if 0 <= frame_idx < len(self.series):
                if lbl_name not in self.available_labels:
                    self.available_labels.append(lbl_name)

                if lbl_name not in self.label_map:
                    lbl_id = max(self.label_map.values(), default=-1) + 1
                    self.label_map[lbl_name] = lbl_id
                    self._get_color(lbl_id)
                else:
                    lbl_id = self.label_map[lbl_name]

                self.series[frame_idx] = lbl_id

    @property
    def hierarchical_cuts(self):
        return self.cuts_history

    @hierarchical_cuts.setter
    def hierarchical_cuts(self, cuts):
        self.cuts_history = list(cuts) if cuts is not None else []

    def set_total_frames(self, frames):
        old_frames = len(self.series)
        self.total_frames = max(1, frames)
        if self.total_frames > old_frames:
            new_series = np.full(self.total_frames + 1, -1, dtype=int)
            new_series[:old_frames] = self.series
            self.series = new_series
        else:
            self.series = self.series[:self.total_frames + 1]

    def reset_hierarchical(self):
        self.cuts_history.clear()

    def reset_categorical(self):
        self.series.fill(-1)

    def build_tree(self):
        root = Node(0, self.total_frames)
        history_records = []

        for f in self.cuts_history:
            def find_leaf(node, frame):
                if node.left is None and node.right is None:
                    if node.start < frame < node.end:
                        return node
                    return None
                if frame < node.left.end:
                    return find_leaf(node.left, frame)
                else:
                    return find_leaf(node.right, frame)

            leaf = find_leaf(root, f)
            if leaf is not None:
                left_child = Node(leaf.start, f)
                right_child = Node(f, leaf.end)
                leaf.left = left_child
                leaf.right = right_child
                history_records.append((leaf, left_child, right_child))

        return root, history_records

    def get_hierarchical_segments(self):
        root, _ = self.build_tree()
        leaves = []
        def collect_leaves(node):
            if node.left is None and node.right is None:
                leaves.append((node.start, node.end))
            else:
                collect_leaves(node.left)
                collect_leaves(node.right)
        collect_leaves(root)
        return leaves

    def add_hierarchical_cut(self, frame_idx):
        if 0 < frame_idx < self.total_frames:
            segments = self.get_hierarchical_segments()
            for start, end in segments:
                if start < frame_idx < end:
                    self.cuts_history.append(frame_idx)
                    break

    def undo_hierarchical_cut(self):
        if self.cuts_history:
            self.cuts_history.pop()

    def convert_hierarchical_to_categorical(self):
        self.reset_categorical()
        segments = self.get_hierarchical_segments()
        
        for idx, (s_start, s_end) in enumerate(segments):
            lbl_name = f"Episódio {idx + 1}"
            if lbl_name not in self.available_labels:
                self.available_labels.append(lbl_name)
                lbl_id = len(self.label_map) - 1
                self.label_map[lbl_name] = lbl_id
                self._get_color(lbl_id)
            
            lbl_id = self.label_map[lbl_name]
            self.series[s_start:min(s_end, len(self.series)-1)] = lbl_id

    def _get_color(self, idx):
        if idx not in self.color_map:
            palette = [
                (50, 50, 50), (255, 220, 0), (50, 220, 50), (50, 150, 255),
                (255, 130, 0), (255, 50, 50), (160, 50, 255), (230, 50, 255)
            ]
            if idx < len(palette):
                self.color_map[idx] = palette[idx]
            else:
                hue = (idx * 0.618033988749895) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
                self.color_map[idx] = (int(r * 255), int(g * 255), int(b * 255))
        return self.color_map[idx]

import pygame

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

        # Aplicação do Zoom: a largura virtual da trilha aumenta proporcionalmente
        virtual_track_w = int(track_w * zoom_level)
        max_scroll = max(0, virtual_track_w - track_w)
        self.scroll_offset_x = max(0, min(self.scroll_offset_x, max_scroll))

        self.eye_rects.clear()
        
        # Área recortada (Clip Viewport) para os blocos não vazarem o header
        track_clip_rect = pygame.Rect(track_x, self.rect.y, track_w, self.rect.height)
        surface.set_clip(track_clip_rect)

        num_tracks = engine.get_num_tracks()
        row_h = max(26, (self.rect.height - 15) // max(1, num_tracks))

        if num_tracks > 0:
            for t_idx in range(num_tracks):
                row_y = self.rect.y + 8 + t_idx * row_h
                is_en = engine.is_track_enabled(t_idx)

                # Fundo da trilha
                track_bar_r = pygame.Rect(track_x, row_y + 2, track_w, row_h - 4)
                pygame.draw.rect(surface, (35, 35, 35), track_bar_r, border_radius=3)

                # Clipes com Zoom e Scroll
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

            # Playhead
            playhead_x = track_x + int((current_frame / float(total_frames)) * virtual_track_w) - self.scroll_offset_x
            if track_x <= playhead_x <= track_x + track_w:
                pygame.draw.line(surface, (255, 60, 60), (playhead_x, self.rect.y + 4), (playhead_x, self.rect.bottom - 4), 2)
                pygame.draw.polygon(surface, (255, 60, 60), [
                    (playhead_x - 4, self.rect.y + 2),
                    (playhead_x + 4, self.rect.y + 2),
                    (playhead_x, self.rect.y + 7)
                ])

        surface.set_clip(None)  # Libera a máscara para desenhar o Header estático

        # Desenhar Cabeçalho Estático das Trilhas (Fica fixo por cima da rolagem)
        pygame.draw.rect(surface, (25, 25, 25), (self.rect.x, self.rect.y, self.header_w - 5, self.rect.height), border_radius=6)
        pygame.draw.line(surface, (50, 50, 50), (track_x - 5, self.rect.y), (track_x - 5, self.rect.bottom), 1)

        if num_tracks == 0:
            msg = self.font.render("Nenhum vídeo carregado na linha do tempo", True, (100, 100, 100))
            surface.blit(msg, msg.get_rect(center=(self.rect.centerx + self.header_w // 2, self.rect.centery)))
            return

        enabled_count = sum(1 for t in range(num_tracks) if engine.is_track_enabled(t))
        m_pos = pygame.mouse.get_pos()

        for t_idx in range(num_tracks):
            row_y = self.rect.y + 8 + t_idx * row_h
            eye_r = pygame.Rect(self.rect.x + 8, row_y + (row_h - 20) // 2, 24, 20)
            self.eye_rects[t_idx] = eye_r

            bg_eye = (45, 45, 45) if eye_r.collidepoint(m_pos) else (32, 32, 32)
            pygame.draw.rect(surface, bg_eye, eye_r, border_radius=4)
            pygame.draw.rect(surface, (60, 60, 60), eye_r, width=1, border_radius=4)

            is_en = engine.is_track_enabled(t_idx)
            status = 'active' if is_en else ('prohibited' if enabled_count >= 2 else 'inactive')
            self.draw_eye_icon(surface, eye_r, status)

            lbl_surf = self.font.render(f"Trilha {t_idx + 1}", True, (220, 220, 220) if is_en else (120, 120, 120))
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

        row_h = max(26, (self.rect.height - 15) // num_tracks)
        t_idx = int((pos[1] - (self.rect.y + 8)) // row_h)

        if 0 <= t_idx < num_tracks:
            for clip in engine.clips:
                if clip.track_idx == t_idx and clip.timeline_start <= clicked_frame < clip.timeline_end:
                    return clip, clicked_frame

        return None, clicked_frame

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

        # Botões de Modoa
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

import os
os.environ["OPENCV_FFMPEG_THREAD_COUNT"] = "1"

import cv2
import pygame

class VideoClip:
    def __init__(self, path, clip_id, fps, total_frames, in_point=0, out_point=None, timeline_start=0, track_idx=0):
        self.path = path
        self.clip_id = clip_id
        self.fps = fps
        self.total_source_frames = total_frames
        self.in_point = in_point
        self.out_point = total_frames if out_point is None else out_point
        self.timeline_start = timeline_start
        self.track_idx = track_idx
        
        self.cap = cv2.VideoCapture(path)
        self.last_frame_idx = -1
        self.last_surface = None

    @property
    def filename(self):
        return os.path.basename(self.path)

    @property
    def duration_frames(self):
        return max(1, self.out_point - self.in_point)

    @property
    def timeline_end(self):
        return self.timeline_start + self.duration_frames

    def global_to_source_frame(self, global_frame):
        if self.timeline_start <= global_frame < self.timeline_end:
            rel_frame = global_frame - self.timeline_start
            return self.in_point + rel_frame
        return None

    def get_frame_surface(self, global_frame, target_height=540):
        source_frame = self.global_to_source_frame(global_frame)
        if source_frame is None or source_frame < 0 or source_frame >= self.total_source_frames:
            return None

        if source_frame == self.last_frame_idx and self.last_surface is not None:
            return self.last_surface

        if source_frame == self.last_frame_idx + 1:
            ret, frame = self.cap.read()
        else:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame)
            ret, frame = self.cap.read()

        if not ret or frame is None:
            return self.last_surface

        self.last_frame_idx = source_frame

        h, w, _ = frame.shape
        aspect_ratio = w / h
        target_width = int(target_height * aspect_ratio)

        frame_resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        frame_rgb = frame_rgb.swapaxes(0, 1)

        self.last_surface = pygame.surfarray.make_surface(frame_rgb)
        return self.last_surface

    def split(self, cut_global_frame):
        if not (self.timeline_start < cut_global_frame < self.timeline_end):
            return None

        offset = cut_global_frame - self.timeline_start
        cut_source_frame = self.in_point + offset

        old_out = self.out_point
        self.out_point = cut_source_frame

        new_clip = VideoClip(
            path=self.path,
            clip_id=self.clip_id,
            fps=self.fps,
            total_frames=self.total_source_frames,
            in_point=cut_source_frame,
            out_point=old_out,
            timeline_start=cut_global_frame,
            track_idx=self.track_idx
        )
        return new_clip

    def to_dict(self):
        return {
            "path": self.path,
            "clip_id": self.clip_id,
            "fps": self.fps,
            "total_source_frames": self.total_source_frames,
            "in_point": self.in_point,
            "out_point": self.out_point,
            "timeline_start": self.timeline_start,
            "track_idx": self.track_idx
        }

    @staticmethod
    def from_dict(d):
        return VideoClip(
            path=d["path"],
            clip_id=d["clip_id"],
            fps=d["fps"],
            total_frames=d["total_source_frames"],
            in_point=d["in_point"],
            out_point=d["out_point"],
            timeline_start=d["timeline_start"],
            track_idx=d["track_idx"]
        )

    def release(self):
        if self.cap:
            self.cap.release()


class MultiVideoEngine:
    def __init__(self):
        self.clips = []
        self.track_enabled_state = {}

    def add_clip(self, clip):
        self.clips.append(clip)
        if clip.track_idx not in self.track_enabled_state:
            self.track_enabled_state[clip.track_idx] = (clip.track_idx < 2)

    def clear(self):
        for clip in self.clips:
            clip.release()
        self.clips.clear()
        self.track_enabled_state.clear()

    def get_num_tracks(self):
        if not self.clips:
            return 0
        return max(c.track_idx for c in self.clips) + 1

    def is_track_enabled(self, track_idx):
        return self.track_enabled_state.get(track_idx, False)

    def toggle_track_enabled(self, track_idx):
        enabled_count = sum(1 for t, en in self.track_enabled_state.items() if en)
        curr = self.is_track_enabled(track_idx)
        if curr:
            self.track_enabled_state[track_idx] = False
            return True
        else:
            if enabled_count < 2:
                self.track_enabled_state[track_idx] = True
                return True
            return False

    def get_total_timeline_frames(self):
        if not self.clips:
            return 0
        return max(c.timeline_end for c in self.clips)

    def get_active_clips_at_frame(self, global_frame):
        active = []
        num_tracks = self.get_num_tracks()
        for t_idx in range(num_tracks):
            if self.is_track_enabled(t_idx):
                for clip in self.clips:
                    if clip.track_idx == t_idx and clip.timeline_start <= global_frame < clip.timeline_end:
                        active.append(clip)
                        break
        return active[:2]

    def delete_clip(self, clip):
        if clip in self.clips:
            clip.release()
            self.clips.remove(clip)

    def to_dict(self):
        return {
            "clips": [c.to_dict() for c in self.clips],
            "track_enabled_state": {str(k): v for k, v in self.track_enabled_state.items()}
        }

    def load_dict(self, data):
        self.clear()
        for clip_d in data.get("clips", []):
            if os.path.exists(clip_d["path"]):
                c = VideoClip.from_dict(clip_d)
                self.clips.append(c)
        
        self.track_enabled_state = {int(k): v for k, v in data.get("track_enabled_state", {}).items()}

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
            msg = "Aguardando seleção de vídeos..." if is_loading_files else "Nenhum vídeo ativo neste frame. Ligue o olho de uma trilha."
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

from app import VideoLabelerApp

if __name__ == "__main__":
    app = VideoLabelerApp()
    app.run()