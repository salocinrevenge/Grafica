import pygame
import cv2
import os
import pandas as pd
import numpy as np
import argparse
import threading
from queue import Queue, Empty
import time

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

    def run(self):
        while self.running:
            if self.seek_event.is_set():
                with self.frame_queue.mutex:
                    self.frame_queue.queue.clear()
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.target_frame)
                self.seek_event.clear()

            if self.playing:
                if self.frame_queue.qsize() < 60:
                    ret, frame = self.cap.read()
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        curr_idx = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                        self.frame_queue.put((curr_idx, frame))
                        
                        # Controle de velocidade real na thread
                        # Dorme o tempo de 1 frame dividido pela velocidade
                        wait_time = (1.0 / self.fps) / self.speed
                        time.sleep(max(0.001, wait_time - 0.005)) # Pequeno offset para processamento
                    else:
                        self.playing = False
                else:
                    time.sleep(0.01)
            else:
                # Se parado, apenas processa um seek se houver, senão descansa a CPU
                time.sleep(0.01)

    def stop(self):
        self.running = False
        self.cap.release()

class MultiLabelVideoPlayer:
    def __init__(self, video_path, csv_folder):
        pygame.init()
        self.screen_width = 1280
        self.screen_height = 950
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Visualizador de Anotações - Sincronizado")
        
        self.font = pygame.font.Font(None, 22)
        self.clock = pygame.time.Clock()
        
        # --- Threads ---
        self.frame_queue = Queue(maxsize=1280)
        self.seek_event = threading.Event()
        self.video_thread = VideoThread(video_path, self.frame_queue, self.seek_event)
        self.fps = self.video_thread.fps
        self.total_frames = int(self.video_thread.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps
        self.video_thread.start()

        # --- Dados ---
        self.csv_data = {} 
        self.label_map = {"None": -1}
        self.color_map = {-1: (50, 50, 50)}
        self._load_all_csvs(csv_folder)

        # --- Estado ---
        self.current_frame = 0
        self.scroll_y = 0
        self.speeds = [0.125, 0.25, 0.5, 1.0]
        self.speed_idx = 3 
        self.zoom_level = 1.0
        
        # Layout
        self.ui_split_y = 600 
        self.control_bar_y = 500
        self.timeline_spacing = 60
        self.last_surface = None
        self.buttons = {}

    def _load_all_csvs(self, folder):
        csv_files = sorted([f for f in os.listdir(folder) if f.endswith('.csv')])
        for file in csv_files:
            try:
                df = pd.read_csv(os.path.join(folder, file))
                series = np.full(self.total_frames + 1, -1, dtype=int)
                df = df.sort_values('timestamp')
                prev_f = 0
                for _, row in df.iterrows():
                    label = str(row['left_label']).strip()
                    t_f = min(int(float(row['timestamp']) * self.fps), self.total_frames)
                    if label not in self.label_map: self.label_map[label] = len(self.label_map) - 1
                    series[prev_f:t_f] = self.label_map[label]
                    prev_f = t_f
                if prev_f < self.total_frames: series[prev_f:] = self.label_map.get(label, -1)
                self.csv_data[file] = series
            except: pass

    def _get_color(self, idx):
        if idx not in self.color_map:
            np.random.seed(idx + 100)
            self.color_map[idx] = tuple(np.random.randint(80, 255, 3))
        return self.color_map[idx]

    def update_video(self):
        """Consome o frame da thread e atualiza a agulha."""
        try:
            while not self.frame_queue.empty():
                idx, frame = self.frame_queue.get_nowait()
                self.current_frame = idx # A agulha segue o frame real
                
                h, w = frame.shape[:2]
                target_h = self.control_bar_y - 40
                scale = target_h / h
                frame_res = cv2.resize(frame, (int(w * scale), target_h))
                self.last_surface = pygame.surfarray.make_surface(frame_res.swapaxes(0, 1))
        except Empty:
            pass

    def draw_button(self, text, x, y, w, h, cid):
        r = pygame.Rect(x, y, w, h)
        m = pygame.mouse.get_pos()
        c = (120, 120, 120) if r.collidepoint(m) else (80, 80, 80)
        pygame.draw.rect(self.screen, c, r, border_radius=5)
        pygame.draw.rect(self.screen, (200, 200, 200), r, 1, border_radius=5)
        t = self.font.render(text, True, (255, 255, 255))
        self.screen.blit(t, t.get_rect(center=r.center))
        self.buttons[cid] = r

    def draw_timelines(self):
        tl_x, tl_w = 60, self.screen_width - 120
        vis_f = self.total_frames / self.zoom_level
        start_f = max(0, min(self.current_frame - vis_f/2, self.total_frames - vis_f))
        if self.zoom_level <= 1.0: start_f = 0

        # Régua e Timelines (Lógica de desenho otimizada)
        ry = self.ui_split_y - 30
        pygame.draw.line(self.screen, (150, 150, 150), (tl_x, ry), (tl_x + tl_w, ry), 2)
        
        # Desenhar marcas de tempo
        for i in range(21):
            f_idx = start_f + (i/20) * vis_f
            x = tl_x + (i/20) * tl_w
            pygame.draw.line(self.screen, (100, 100, 100), (x, ry), (x, ry-5))
            if i % 2 == 0:
                txt = self.font.render(f"{f_idx/self.fps:.1f}s", True, (120, 120, 120))
                self.screen.blit(txt, (x - 15, ry - 22))

        m_pos = pygame.mouse.get_pos()
        for i, (name, series) in enumerate(self.csv_data.items()):
            y = self.ui_split_y + (i * self.timeline_spacing) + self.scroll_y
            if y < self.ui_split_y - 40 or y > self.screen_height: continue
            
            self.screen.blit(self.font.render(name[:30], True, (180, 180, 180)), (tl_x, y - 18))
            bar = pygame.Rect(tl_x, y, tl_w, 35)
            pygame.draw.rect(self.screen, (15, 15, 15), bar)

            # Desenho das cores
            for px in range(0, tl_w, 2):
                f = int(start_f + (px/tl_w) * vis_f)
                if 0 <= f < len(series):
                    c_idx = series[f]
                    if c_idx != -1:
                        pygame.draw.line(self.screen, self._get_color(c_idx), (tl_x+px, y), (tl_x+px, y+35), 2)

            if bar.collidepoint(m_pos):
                f_h = int(start_f + ((m_pos[0]-tl_x)/tl_w) * vis_f)
                l_h = series[min(f_h, len(series)-1)]
                l_n = next((k for k,v in self.label_map.items() if v==l_h), "None")
                self.screen.blit(self.font.render(l_n, True, (255,255,255), (0,0,0)), (m_pos[0]+10, m_pos[1]-15))

        # Agulha fixa no frame atual
        if start_f <= self.current_frame <= start_f + vis_f:
            nx = tl_x + ((self.current_frame - start_f) / vis_f) * tl_w
            pygame.draw.line(self.screen, (255, 50, 50), (nx, ry), (nx, self.screen_height), 2)

    def handle_click(self, pos):
        for cid, r in self.buttons.items():
            if r.collidepoint(pos):
                if cid == "play":
                    self.video_thread.playing = not self.video_thread.playing
                elif cid == "speed":
                    self.speed_idx = (self.speed_idx + 1) % len(self.speeds)
                    self.video_thread.speed = self.speeds[self.speed_idx]
                elif cid == "z_in": self.zoom_level = min(100.0, self.zoom_level * 2)
                elif cid == "z_out": self.zoom_level = max(1.0, self.zoom_level / 2)
                return

        if pos[1] > self.ui_split_y - 40:
            tl_x, tl_w = 60, self.screen_width - 120
            vis_f = self.total_frames / self.zoom_level
            start_f = max(0, min(self.current_frame - vis_f/2, self.total_frames - vis_f)) if self.zoom_level > 1 else 0
            rel_x = (pos[0] - tl_x) / tl_w
            if 0 <= rel_x <= 1:
                self.current_frame = int(start_f + rel_x * vis_f)
                self.video_thread.target_frame = self.current_frame
                self.video_thread.seek_event.set()

    def run(self):
        while True:
            self.screen.fill((20, 20, 20))
            self.clock.tick(60)
            
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.video_thread.stop()
                    return
                if e.type == pygame.MOUSEBUTTONDOWN:
                    if e.button == 1: self.handle_click(e.pos)
                    if e.button == 4: self.scroll_y = min(0, self.scroll_y + 40)
                    if e.button == 5: self.scroll_y -= 40
                if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                    self.video_thread.playing = not self.video_thread.playing

            self.update_video()
            
            if self.last_surface:
                self.screen.blit(self.last_surface, ((self.screen_width - self.last_surface.get_width())//2, 10))

            # UI
            bx, by = 20, self.control_bar_y
            self.draw_button("PLAY" if not self.video_thread.playing else "PAUSE", bx, by, 80, 30, "play")
            self.draw_button(f"{self.speeds[self.speed_idx]}x", bx + 90, by, 60, 30, "speed")
            self.draw_button("Zoom +", bx + 160, by, 70, 30, "z_in")
            self.draw_button("Zoom -", bx + 240, by, 70, 30, "z_out")
            
            info = f"{self.current_frame/self.fps:.2f}s / {self.duration:.2f}s | Speed: {self.speeds[self.speed_idx]}x"
            self.screen.blit(self.font.render(info, True, (255,255,255)), (self.screen_width - 300, by + 10))

            self.draw_timelines()
            pygame.display.flip()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--csvs", required=True)
    args = p.parse_args()
    MultiLabelVideoPlayer(args.video, args.csvs).run()
