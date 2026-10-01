import pygame
import cv2
import os
import pandas as pd
import numpy as np
import argparse
import threading
from queue import Queue, Empty
import time
import colorsys

class VideoThread(threading.Thread):
    def __init__(self, video_path, frame_queue, seek_event):
        super().__init__()
        self.cap = cv2.VideoCapture(video_path)
        self.frame_queue = frame_queue
        self.seek_event = seek_event
        self.target_frame = 0
        self.speed = 1.0
        self.playing = False
        self.running = True
        self.daemon = True
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.max_buffer_frames = 60

    def run(self):
        while self.running:
            if self.seek_event.is_set():
                with self.frame_queue.mutex:
                    self.frame_queue.queue.clear()
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.target_frame)
                self.seek_event.clear()

            if self.playing:
                if self.frame_queue.qsize() < self.max_buffer_frames:
                    ret, frame = self.cap.read()
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        curr_idx = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                        self.frame_queue.put((curr_idx, frame))
                        
                        wait_time = (1.0 / self.fps) / self.speed
                        time.sleep(max(0.001, wait_time - 0.005))
                    else:
                        self.playing = False
                else:
                    time.sleep(0.01)
            else:
                time.sleep(0.01)

    def stop(self):
        self.running = False
        self.cap.release()

class VideoLabeler:
    def __init__(self, video_path, csv_path=None):
        pygame.init()
        self.screen_width = 1280
        self.screen_height = 950
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("VideoLabeler - Ferramenta de Anotação")
        
        self.font = pygame.font.Font(None, 22)
        self.font_bold = pygame.font.Font(None, 24)
        self.clock = pygame.time.Clock()
        
        # --- Threads ---
        self.video_path = video_path
        self.csv_path = csv_path if csv_path else f"{os.path.splitext(video_path)[0]}_annotations.csv"
        self.frame_queue = Queue(maxsize=128)
        self.seek_event = threading.Event()
        self.video_thread = VideoThread(video_path, self.frame_queue, self.seek_event)
        self.fps = self.video_thread.fps
        self.total_frames = int(self.video_thread.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps
        self.video_thread.start()

        # --- Dados de Anotação ---
        self.series = np.full(self.total_frames + 1, -1, dtype=int)
        self.label_map = {"None": -1}
        self.color_map = {-1: (50, 50, 50)}
        self.available_labels = []
        self.selected_label = None

        # --- Estado UI ---
        self.current_frame = 0
        self.speeds = [0.125, 0.25, 0.5, 1.0]
        self.speed_idx = 3 
        self.zoom_level = 1.0
        self.show_labels = True
        
        # Campo de Input de Texto
        self.input_text = ""
        self.input_active = False
        
        # Layout
        self.ui_split_y = 650 
        self.control_bar_y = 520
        self.panel_width = 300 
        self.last_surface = None
        self.buttons = {}
        self.label_rects = {}

        self.load_annotations()

    def _get_color(self, idx):
        if idx not in self.color_map:
            # Paleta inicial fixa com cores maximamente contrastantes
            palette = [
                (50, 50, 50),    # Cinza
                (255, 220, 0),    # Amarelo
                (50, 220, 50),    # Verde
                (50, 150, 255),   # Azul
                (255, 130, 0),    # Laranja
                (255, 50, 50),    # Vermelho
                (160, 50, 255),   # Roxo
                (230, 50, 255),   # Magenta
                (0, 230, 230),    # Ciano
                (255, 100, 180),  # Rosa
                (0, 250, 154),    # Verde Água
            ]
            
            if idx < len(palette):
                self.color_map[idx] = palette[idx]
            else:
                # Se houver mais rótulos que a paleta, distribui o tom (Hue) no espaço HSV usando a razão áurea
                hue = (idx * 0.618033988749895) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 0.95)
                self.color_map[idx] = (int(r * 255), int(g * 255), int(b * 255))
                
        return self.color_map[idx]

    def _add_label(self, name):
        name = name.strip()
        if name and name not in self.available_labels:
            self.available_labels.append(name)
            new_id = len(self.label_map) - 1
            self.label_map[name] = new_id
            self._get_color(new_id)
            if self.selected_label is None:
                self.selected_label = name
            self.input_text = ""
        # Reativa os atalhos do teclado desativando a caixa de texto
        self.input_active = False

    def load_annotations(self):
        if not os.path.exists(self.csv_path): return
        try:
            df = pd.read_csv(self.csv_path)
            df = df.sort_values('timestamp')
            prev_f = 0
            for _, row in df.iterrows():
                lbl = str(row['left_label']).strip()
                t_f = min(int(float(row['timestamp']) * self.fps), self.total_frames)
                self._add_label(lbl)
                lbl_id = self.label_map[lbl]
                self.series[prev_f:t_f] = lbl_id
                prev_f = t_f
            print(f"Anotações carregadas de: {self.csv_path}")
        except Exception as e:
            print(f"Erro ao carregar CSV: {e}")

    def save_annotations(self):
        data = []
        prev_lbl_id = self.series[0]
        
        for f in range(1, self.total_frames + 1):
            lbl_id = self.series[f]
            if lbl_id != prev_lbl_id:
                if prev_lbl_id != -1:
                    lbl_name = next((k for k, v in self.label_map.items() if v == prev_lbl_id), "None")
                    t_sec = f / self.fps
                    data.append({'timestamp': round(t_sec, 4), 'left_label': lbl_name})
                prev_lbl_id = lbl_id

        if prev_lbl_id != -1:
            lbl_name = next((k for k, v in self.label_map.items() if v == prev_lbl_id), "None")
            data.append({'timestamp': round(self.total_frames / self.fps, 4), 'left_label': lbl_name})

        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)
        print(f"Anotações salvas com sucesso em: {self.csv_path}")

    def update_video(self):
        try:
            while not self.frame_queue.empty():
                idx, frame = self.frame_queue.get_nowait()
                self.current_frame = idx 
                
                h, w = frame.shape[:2]
                target_h = self.control_bar_y - 40
                scale = target_h / h
                frame_res = cv2.resize(frame, (int(w * scale), target_h))
                self.last_surface = pygame.surfarray.make_surface(frame_res.swapaxes(0, 1))
        except Empty:
            pass

    def draw_button(self, text, x, y, w, h, cid, active=False, bg_color=None):
        r = pygame.Rect(x, y, w, h)
        m = pygame.mouse.get_pos()
        if bg_color:
            c = bg_color
        else:
            if active: c = (50, 150, 50)
            else: c = (120, 120, 120) if r.collidepoint(m) else (80, 80, 80)
            
        pygame.draw.rect(self.screen, c, r, border_radius=5)
        pygame.draw.rect(self.screen, (200, 200, 200), r, 1, border_radius=5)
        t = self.font.render(text, True, (255, 255, 255))
        self.screen.blit(t, t.get_rect(center=r.center))
        self.buttons[cid] = r

    def draw_input_box(self):
        bx, by = 20, self.control_bar_y + 45
        
        # Caixa de Texto
        input_rect = pygame.Rect(bx, by, 180, 30)
        color = (200, 255, 200) if self.input_active else (100, 100, 100)
        pygame.draw.rect(self.screen, (30, 30, 30), input_rect)
        pygame.draw.rect(self.screen, color, input_rect, 2)
        
        txt_surf = self.font.render(self.input_text + ("|" if self.input_active else ""), True, (255, 255, 255))
        self.screen.blit(txt_surf, (bx + 5, by + 7))
        self.buttons["input_box"] = input_rect
        
        # Botão com Tick de Adicionar
        self.draw_button("✔ Add", bx + 190, by, 60, 30, "add_label", bg_color=(40, 120, 40))

    def draw_label_panel(self):
        if not self.show_labels: return
        self.label_rects.clear()
        
        panel_rect = pygame.Rect(self.screen_width - self.panel_width, 0, self.panel_width, self.ui_split_y)
        pygame.draw.rect(self.screen, (30, 30, 30), panel_rect)
        pygame.draw.line(self.screen, (100, 100, 100), (self.screen_width - self.panel_width, 0), (self.screen_width - self.panel_width, self.ui_split_y), 2)
        
        header = self.font_bold.render("RÓTULOS DISPONÍVEIS:", True, (255, 255, 100))
        self.screen.blit(header, (self.screen_width - self.panel_width + 10, 15))
        
        y_offset = 50
        for lbl in self.available_labels:
            color = self._get_color(self.label_map[lbl])
            item_rect = pygame.Rect(self.screen_width - self.panel_width + 5, y_offset, self.panel_width - 10, 30)
            
            if lbl == self.selected_label:
                pygame.draw.rect(self.screen, (70, 70, 70), item_rect, border_radius=4)
                pygame.draw.rect(self.screen, (255, 200, 0), item_rect, 2, border_radius=4)
            
            pygame.draw.rect(self.screen, color, (self.screen_width - self.panel_width + 15, y_offset + 9, 12, 12))
            lbl_surf = self.font.render(lbl, True, (255, 255, 255))
            self.screen.blit(lbl_surf, (self.screen_width - self.panel_width + 35, y_offset + 7))
            
            self.label_rects[lbl] = item_rect
            y_offset += 35

    def draw_timelines(self):
        tl_x, tl_w = 60, self.screen_width - 120
        vis_f = self.total_frames / self.zoom_level
        start_f = max(0, min(self.current_frame - vis_f/2, self.total_frames - vis_f))
        if self.zoom_level <= 1.0: start_f = 0

        ry = self.ui_split_y - 30
        pygame.draw.line(self.screen, (150, 150, 150), (tl_x, ry), (tl_x + tl_w, ry), 2)
        
        for i in range(21):
            f_idx = start_f + (i/20) * vis_f
            x = tl_x + (i/20) * tl_w
            pygame.draw.line(self.screen, (100, 100, 100), (x, ry), (x, ry-5))
            if i % 2 == 0:
                txt = self.font.render(f"{f_idx/self.fps:.1f}s", True, (120, 120, 120))
                self.screen.blit(txt, (x - 15, ry - 22))

        # Timeline Principal
        y = self.ui_split_y + 10
        self.screen.blit(self.font.render("Sua Anotação:", True, (180, 180, 180)), (tl_x, y - 18))
        bar = pygame.Rect(tl_x, y, tl_w, 40)
        pygame.draw.rect(self.screen, (15, 15, 15), bar)

        step = 2 if self.zoom_level < 5 else 1
        for px in range(0, tl_w, step):
            f = int(start_f + (px/tl_w) * vis_f)
            if 0 <= f < len(self.series):
                c_idx = self.series[f]
                if c_idx != -1:
                    pygame.draw.line(self.screen, self._get_color(c_idx), (tl_x+px, y), (tl_x+px, y+40), step)

        m_pos = pygame.mouse.get_pos()
        if bar.collidepoint(m_pos):
            f_h = int(start_f + ((m_pos[0]-tl_x)/tl_w) * vis_f)
            l_h = self.series[min(f_h, len(self.series)-1)]
            l_n = next((k for k, v in self.label_map.items() if v == l_h), "None")
            self.screen.blit(self.font.render(l_n, True, (255,255,255), (0,0,0)), (m_pos[0]+10, m_pos[1]-15))

        if start_f <= self.current_frame <= start_f + vis_f:
            nx = tl_x + ((self.current_frame - start_f) / vis_f) * tl_w
            pygame.draw.line(self.screen, (255, 50, 50), (nx, ry), (nx, self.screen_height), 2)

    def handle_click(self, pos, button):
        # 1. Checa botões da interface
        for cid, r in self.buttons.items():
            if r.collidepoint(pos) and button == 1:
                if cid == "play": 
                    self.video_thread.playing = not self.video_thread.playing
                elif cid == "speed":
                    self.speed_idx = (self.speed_idx + 1) % len(self.speeds)
                    self.video_thread.speed = self.speeds[self.speed_idx]
                elif cid == "z_in": 
                    self.zoom_level = min(100.0, self.zoom_level * 2)
                elif cid == "z_out": 
                    self.zoom_level = max(1.0, self.zoom_level / 2)
                elif cid == "add_label": 
                    self._add_label(self.input_text)
                elif cid == "save": 
                    self.save_annotations()
                elif cid == "input_box":
                    self.input_active = True
                    return
                return

        # Clicou fora da caixa de texto: desativa o foco (religa atalhos)
        self.input_active = False

        # 2. Seleção de Rótulos no painel
        if self.show_labels:
            for lbl, r in self.label_rects.items():
                if r.collidepoint(pos) and button == 1:
                    self.selected_label = lbl
                    return

        # 3. Interação com a Timeline
        if pos[1] > self.ui_split_y - 40:
            tl_x, tl_w = 60, self.screen_width - 120
            vis_f = self.total_frames / self.zoom_level
            start_f = max(0, min(self.current_frame - vis_f/2, self.total_frames - vis_f)) if self.zoom_level > 1 else 0
            rel_x = (pos[0] - tl_x) / tl_w
            
            if 0 <= rel_x <= 1:
                clicked_frame = int(start_f + rel_x * vis_f)
                
                if button == 1:
                    self.current_frame = clicked_frame
                    self.video_thread.target_frame = self.current_frame
                    self.video_thread.seek_event.set()
                    
                elif button == 3 and self.selected_label is not None:
                    lbl_id = self.label_map[self.selected_label]
                    annotated_frames = np.where(self.series[:clicked_frame] != -1)[0]
                    start_fill = annotated_frames[-1] + 1 if len(annotated_frames) > 0 else 0
                    
                    if start_fill < clicked_frame:
                        self.series[start_fill:clicked_frame] = lbl_id

    def run(self):
        while True:
            self.screen.fill((20, 20, 20))
            self.clock.tick(60)
            
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.video_thread.stop()
                    self.save_annotations()
                    return
                if e.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_click(e.pos, e.button)
                if e.type == pygame.KEYDOWN:
                    # Modo de Escrita Ativo (Atalhos desligados)
                    if self.input_active:
                        if e.key == pygame.K_RETURN:
                            self._add_label(self.input_text)
                        elif e.key == pygame.K_ESCAPE:
                            self.input_active = False
                        elif e.key == pygame.K_BACKSPACE:
                            self.input_text = self.input_text[:-1]
                        else:
                            if e.unicode.isprintable():
                                self.input_text += e.unicode
                    # Controles de vídeo por atalho (Ativos apenas se NÃO estiver digitando)
                    else:
                        if e.key == pygame.K_SPACE:
                            self.video_thread.playing = not self.video_thread.playing
                        elif e.key == pygame.K_RIGHT:
                            self.current_frame = min(self.total_frames - 1, self.current_frame + int(self.fps * 5 * self.speeds[self.speed_idx]))
                            self.video_thread.target_frame = self.current_frame
                            self.video_thread.seek_event.set()
                        elif e.key == pygame.K_LEFT:
                            self.current_frame = max(0, self.current_frame - int(self.fps * 5 * self.speeds[self.speed_idx]))
                            self.video_thread.target_frame = self.current_frame
                            self.video_thread.seek_event.set()
                        elif e.key == pygame.K_s:
                            self.save_annotations()

            self.update_video()
            
            if self.last_surface:
                vid_w = self.last_surface.get_width()
                if self.show_labels:
                    available_space = self.screen_width - self.panel_width
                    vid_x = (available_space - vid_w) // 2
                else:
                    vid_x = (self.screen_width - vid_w) // 2
                self.screen.blit(self.last_surface, (vid_x, 10))

            # UI - Renderização
            bx, by = 20, self.control_bar_y
            self.draw_button("PLAY" if not self.video_thread.playing else "PAUSE", bx, by, 80, 30, "play")
            self.draw_button(f"{self.speeds[self.speed_idx]}x", bx + 90, by, 60, 30, "speed")
            self.draw_button("Zoom +", bx + 160, by, 70, 30, "z_in")
            self.draw_button("Zoom -", bx + 240, by, 70, 30, "z_out")
            self.draw_button("Salvar", bx + 320, by, 70, 30, "save", bg_color=(50, 100, 150))
            
            self.draw_input_box()

            info = f"Frame: {self.current_frame} | {self.current_frame/self.fps:.2f}s / {self.duration:.2f}s"
            self.screen.blit(self.font.render(info, True, (255,255,255)), (self.screen_width - self.panel_width - 260, by + 10))

            self.draw_label_panel()
            self.draw_timelines()
            pygame.display.flip()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="VideoLabeler - Ferramenta de Anotação de Rótulos de Vídeo")
    p.add_argument("--video", required=True, help="Caminho para o arquivo de vídeo")
    p.add_argument("--csv", default=None, help="Caminho opcional do arquivo CSV de saída")
    args = p.parse_args()

    app = VideoLabeler(args.video, args.csv)
    app.run()