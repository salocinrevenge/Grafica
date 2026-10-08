import pygame
import cv2
import os
import json
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
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
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

class Node:
    """Nó da árvore binária de divisões."""
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.left = None
        self.right = None
        self.group_id = None

class VideoSplitter:
    def __init__(self, video_path, json_path=None):
        pygame.init()
        self.screen_width = 1280
        self.screen_height = 800
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("VideoSplitter - Divisão e Agrupamento de Episódios")
        
        self.font = pygame.font.Font(None, 22)
        self.font_bold = pygame.font.Font(None, 24)
        self.clock = pygame.time.Clock()
        
        # Thread de Vídeo
        self.video_path = video_path
        self.json_path = json_path if json_path else f"{os.path.splitext(video_path)[0]}_cuts.json"
        self.frame_queue = Queue(maxsize=128)
        self.seek_event = threading.Event()
        self.video_thread = VideoThread(video_path, self.frame_queue, self.seek_event)
        self.fps = self.video_thread.fps
        self.total_frames = int(self.video_thread.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps
        self.video_thread.start()

        # Histórico de cortes (lista de frames de corte na ordem cronológica em que foram feitos)
        self.cuts_history = []

        # Estado UI
        self.current_frame = 0
        self.speeds = [0.125, 0.25, 0.5, 1.0]
        self.speed_idx = 3 
        self.zoom_level = 1.0
        
        # Layout
        self.ui_split_y = 600 
        self.control_bar_y = 500
        self.last_surface = None
        self.buttons = {}
        self.color_cache = {}

    def _get_color(self, idx):
        if idx not in self.color_cache:
            palette = [
                (50, 150, 255),  # Azul
                (255, 130, 0),   # Laranja
                (50, 220, 50),   # Verde
                (230, 50, 255),  # Magenta
                (255, 220, 0),   # Amarelo
                (0, 230, 230),   # Ciano
                (255, 50, 50),   # Vermelho
                (160, 50, 255),  # Roxo
                (255, 100, 180), # Rosa
                (0, 250, 154),   # Verde Água
            ]
            if idx < len(palette):
                self.color_cache[idx] = palette[idx]
            else:
                hue = (idx * 0.618033988749895) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
                self.color_cache[idx] = (int(r * 255), int(g * 255), int(b * 255))
        return self.color_cache[idx]

    def _build_tree(self):
        """Reconstrói a árvore de cortes a partir do histórico."""
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

    def _get_current_segments(self):
        """Retorna os segmentos folha atuais em ordem cronológica."""
        root, _ = self._build_tree()
        leaves = []
        
        def collect_leaves(node):
            if node.left is None and node.right is None:
                leaves.append((node.start, node.end))
            else:
                collect_leaves(node.left)
                collect_leaves(node.right)

        collect_leaves(root)
        return leaves

    def add_cut(self, frame_idx):
        """Subdivide o segmento que contém o frame informado."""
        if 0 < frame_idx < self.total_frames:
            segments = self._get_current_segments()
            for start, end in segments:
                if start < frame_idx < end:
                    self.cuts_history.append(frame_idx)
                    break

    def undo_cut(self):
        """Desfaz a última divisão realizada (Ctrl + Z)."""
        if self.cuts_history:
            self.cuts_history.pop()

    def save_json(self):
        """Gera e salva o JSON no formato de aglutinação hierárquica reversa."""
        root, history_records = self._build_tree()
        
        # 1. Coleta folhas na ordem cronológica
        leaf_nodes = []
        def collect_leaves(node):
            if node.left is None and node.right is None:
                leaf_nodes.append(node)
            else:
                collect_leaves(node.left)
                collect_leaves(node.right)

        collect_leaves(root)

        # 2. Atribui IDs 0 .. K-1 para os segmentos da camada mais granular
        first_layer_starts = [node.start for node in leaf_nodes]
        for idx, node in enumerate(leaf_nodes):
            node.group_id = idx

        next_group_id = len(leaf_nodes)

        # 3. Processa a fusão na ordem inversa das divisões feitas pelo usuário
        merges = []
        for parent_node, left_child, right_child in reversed(history_records):
            id_left = left_child.group_id
            id_right = right_child.group_id
            merges.append([id_left, id_right])
            
            parent_node.group_id = next_group_id
            next_group_id += 1

        output_data = {
            "number_steps": self.total_frames,
            "first_layer_starts": first_layer_starts,
            "above_layers_groups": [merges]
        }

        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)

        print(f"Arquivo salvo com sucesso em: {self.json_path}")

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

    def draw_button(self, text, x, y, w, h, cid, bg_color=None):
        r = pygame.Rect(x, y, w, h)
        m = pygame.mouse.get_pos()
        c = bg_color if bg_color else ((120, 120, 120) if r.collidepoint(m) else (80, 80, 80))
            
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

        ry = self.ui_split_y - 30
        pygame.draw.line(self.screen, (150, 150, 150), (tl_x, ry), (tl_x + tl_w, ry), 2)
        
        # Marcadores de tempo
        for i in range(21):
            f_idx = start_f + (i/20) * vis_f
            x = tl_x + (i/20) * tl_w
            pygame.draw.line(self.screen, (100, 100, 100), (x, ry), (x, ry-5))
            if i % 2 == 0:
                txt = self.font.render(f"{f_idx/self.fps:.1f}s", True, (120, 120, 120))
                self.screen.blit(txt, (x - 15, ry - 22))

        # Desenho dos segmentos de episódios
        y = self.ui_split_y + 10
        self.screen.blit(self.font.render("Segmentos / Episódios (Clique direito para cortar):", True, (180, 180, 180)), (tl_x, y - 18))
        bar = pygame.Rect(tl_x, y, tl_w, 50)
        pygame.draw.rect(self.screen, (15, 15, 15), bar)

        segments = self._get_current_segments()
        for idx, (seg_start, seg_end) in enumerate(segments):
            # Calcula coordenadas visíveis do segmento
            x1 = tl_x + max(0, (seg_start - start_f) / vis_f) * tl_w
            x2 = tl_x + min(1, (seg_end - start_f) / vis_f) * tl_w
            
            if x2 > x1:
                seg_rect = pygame.Rect(x1, y, x2 - x1, 50)
                color = self._get_color(idx)
                pygame.draw.rect(self.screen, color, seg_rect)
                pygame.draw.rect(self.screen, (20, 20, 20), seg_rect, 1) # Borda

                # Rótulo do segmento
                if x2 - x1 > 35:
                    lbl_txt = self.font_bold.render(f"Ep {idx}", True, (255, 255, 255))
                    self.screen.blit(lbl_txt, (x1 + 5, y + 15))

        # Indicador de Playhead (frame atual)
        if start_f <= self.current_frame <= start_f + vis_f:
            nx = tl_x + ((self.current_frame - start_f) / vis_f) * tl_w
            pygame.draw.line(self.screen, (255, 50, 50), (int(nx), ry), (int(nx), self.screen_height), 2)

    def handle_click(self, pos, button):
        # 1. Botões de Interface
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
                elif cid == "cut":
                    self.add_cut(self.current_frame)
                elif cid == "undo":
                    self.undo_cut()
                elif cid == "save": 
                    self.save_json()
                return

        # 2. Interação com a Timeline
        if pos[1] > self.ui_split_y - 30:
            tl_x, tl_w = 60, self.screen_width - 120
            vis_f = self.total_frames / self.zoom_level
            start_f = max(0, min(self.current_frame - vis_f/2, self.total_frames - vis_f)) if self.zoom_level > 1 else 0
            rel_x = (pos[0] - tl_x) / tl_w
            
            if 0 <= rel_x <= 1:
                clicked_frame = int(start_f + rel_x * vis_f)
                
                # Clique Esquerdo: Seeks no vídeo
                if button == 1:
                    self.current_frame = clicked_frame
                    self.video_thread.target_frame = self.current_frame
                    self.video_thread.seek_event.set()
                    
                # Clique Direito: Subdivide o segmento no ponto clicado
                elif button == 3:
                    self.add_cut(clicked_frame)

    def run(self):
        while True:
            self.screen.fill((20, 20, 20))
            self.clock.tick(60)
            
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.video_thread.stop()
                    self.save_json()
                    return
                if e.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_click(e.pos, e.button)
                if e.type == pygame.KEYDOWN:
                    # Atalho Ctrl + Z (Desfazer)
                    if (e.key == pygame.K_z and (e.mod & pygame.KMOD_CTRL)) or e.key == pygame.K_z:
                        self.undo_cut()
                    elif e.key == pygame.K_c or e.key == pygame.K_RETURN:
                        self.add_cut(self.current_frame)
                    elif e.key == pygame.K_SPACE:
                        self.video_thread.playing = not self.video_thread.playing
                    elif e.key == pygame.K_RIGHT:
                        self.current_frame = min(self.total_frames - 1, self.current_frame + int(self.fps * 5 * self.speeds[self.speed_idx]))
                        self.video_thread.target_frame = self.current_frame
                        self.video_thread.seek_event.set()
                    elif e.key == pygame.K_LEFT:
                        self.current_frame = max(0, self.current_frame - int(self.fps * 5 * self.speeds[self.speed_idx]))
                        self.video_thread.target_frame = self.current_frame
                        self.video_thread.seek_event.set()
                    elif (e.key == pygame.K_s and (e.mod & pygame.KMOD_CTRL)) or e.key == pygame.K_s:
                        self.save_json()

            self.update_video()
            
            if self.last_surface:
                vid_w = self.last_surface.get_width()
                vid_x = (self.screen_width - vid_w) // 2
                self.screen.blit(self.last_surface, (vid_x, 10))

            # UI - Botoes de Controle
            bx, by = 20, self.control_bar_y
            self.draw_button("PLAY" if not self.video_thread.playing else "PAUSE", bx, by, 80, 30, "play")
            self.draw_button(f"{self.speeds[self.speed_idx]}x", bx + 90, by, 60, 30, "speed")
            self.draw_button("Zoom +", bx + 160, by, 70, 30, "z_in")
            self.draw_button("Zoom -", bx + 240, by, 70, 30, "z_out")
            self.draw_button("Cortar (C)", bx + 320, by, 90, 30, "cut", bg_color=(180, 80, 40))
            self.draw_button("Desfazer (Ctrl+Z)", bx + 420, by, 130, 30, "undo", bg_color=(120, 60, 140))
            self.draw_button("Salvar (S)", bx + 560, by, 80, 30, "save", bg_color=(40, 120, 60))
            
            # Informações
            seg_count = len(self._get_current_segments())
            info = f"Frame: {self.current_frame} | {self.current_frame/self.fps:.2f}s / {self.duration:.2f}s | Segmentos: {seg_count}"
            self.screen.blit(self.font.render(info, True, (255,255,255)), (self.screen_width - 380, by + 10))

            self.draw_timelines()
            pygame.display.flip()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="VideoSplitter - Ferramenta de Divisão de Episódios")
    p.add_argument("--video", required=True, help="Caminho para o arquivo de vídeo")
    p.add_argument("--json", default=None, help="Caminho opcional do arquivo JSON de saída")
    args = p.parse_args()

    app = VideoSplitter(args.video, args.json)
    app.run()