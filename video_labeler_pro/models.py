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
        
        # Trim (Pontos de entrada e saída no arquivo fonte)
        self.in_point = 0
        self.out_point = total_source_frames
        
        # Posição na timeline global (em frames)
        self.timeline_start = 0

    @property
    def duration_frames(self):
        return max(1, self.out_point - self.in_point)

    @property
    def timeline_end(self):
        return self.timeline_start + self.duration_frames

    def global_to_source_frame(self, global_frame):
        """Converte um frame da timeline global para o frame correspondente do arquivo fonte."""
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
    MODE_CATEGORICAL = "Categorizado / Episódios"
    MODE_HIERARCHICAL = "Hierárquico"

    def __init__(self, total_timeline_frames=1800, fps=30.0):
        self.mode = self.MODE_CATEGORICAL
        self.total_frames = total_timeline_frames
        self.fps = fps
        
        # --- Dados Categorizados ---
        self.series = np.full(self.total_frames + 1, -1, dtype=int)
        self.label_map = {"None": -1}
        self.color_map = {-1: (50, 50, 50)}
        self.available_labels = []
        self.selected_label = None

        # --- Dados Hierárquicos ---
        self.cuts_history = []

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

    # --- Métodos Hierárquicos ---
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
        """Converte os segmentos hierárquicos em rótulos de episódios no modo categorizado."""
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