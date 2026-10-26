import os
import json
import bisect
import colorsys
import numpy as np

class VideoClip:
    """Representa um clipe de vídeo posicionado na timeline principal."""
    def __init__(self, filepath, clip_id, fps, total_source_frames, track_idx=0):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.clip_id = clip_id
        self.fps = fps
        self.total_source_frames = total_source_frames
        self.track_idx = track_idx
        
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

    def split(self, split_global_frame):
        if not (self.timeline_start < split_global_frame < self.timeline_end):
            return None
        
        offset = split_global_frame - self.timeline_start
        split_source_frame = self.in_point + offset

        new_clip = VideoClip(
            filepath=self.filepath,
            clip_id=self.clip_id + 1000,
            fps=self.fps,
            total_source_frames=self.total_source_frames,
            track_idx=self.track_idx
        )
        new_clip.in_point = split_source_frame
        new_clip.out_point = self.out_point
        new_clip.timeline_start = split_global_frame

        self.out_point = split_source_frame
        return new_clip


class Node:
    """Nó para representação hierárquica em árvore binária."""
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.left = None
        self.right = None
        self.group_id = None


def fcluster(label_track, target_num_episodes):
    """
    Agrupa episódios hierarquicamente até atingir `target_num_episodes` e para.
    Por eficiência, reaproveita o recorte já calculado em `label_track`, atualizando
    apenas o delta (avançando nas fusões se o alvo tiver menos episódios, ou
    desfazendo fusões se o alvo tiver mais episódios).
    """
    return label_track.fcluster(target_num_episodes)


class HierarchicalLabelTrack:
    """
    Representa uma anotação hierárquica carregada de arquivo JSON.
    Mantém o estado do recorte atual para permitir que `fcluster` reaproveite
    o recorte já calculado e atualize apenas o delta de fusões.
    """
    def __init__(self, data, filepath="", fallback_total_frames=1800):
        self.filepath = filepath
        self.name = os.path.basename(filepath) if filepath else "Label"
        self.number_steps = int(data.get("number_steps", fallback_total_frames) or fallback_total_frames)

        raw_starts = data.get("first_layer_starts", [0])
        self.first_layer_starts = sorted(int(s) for s in raw_starts) if raw_starts else [0]
        self.base_num_episodes = len(self.first_layer_starts)

        self.above_layers_groups = data.get("above_layers_groups", [[]])
        self.merges = self._extract_merges(self.above_layers_groups)

        # Dicionário de intervalos conhecidos por group_id: id -> (start, end)
        self.node_intervals = {}
        # Dicionário de episódios ativos no recorte atual: id -> (start, end)
        self.active_nodes = {}
        # Lista ordenada de segmentos (start, end) do recorte atual
        self.cached_segments = []

        for i in range(self.base_num_episodes):
            s = self.first_layer_starts[i]
            e = self.first_layer_starts[i + 1] if (i + 1) < self.base_num_episodes else self.number_steps
            iv = (s, e)
            self.node_intervals[i] = iv
            self.active_nodes[i] = iv
            self.cached_segments.append(iv)

        # Quantidade de passos de fusão aplicados no recorte atual (0 .. len(merges))
        self.current_step = 0

    @staticmethod
    def _extract_merges(above_layers_groups):
        """
        Extrai a lista sequencial de fusões a partir de `above_layers_groups`.
        Suporta tanto o formato 3D `[[[a, b], [c, d], ...]]` quanto o formato 2D
        direto `[[a, b], [c, d], ...]` (como em `common_rep_upper.json`).
        """
        if not above_layers_groups or not isinstance(above_layers_groups, list):
            return []
        merges = []
        for item in above_layers_groups:
            if isinstance(item, list) and len(item) > 0:
                # Se o primeiro elemento já é um inteiro, `item` é diretamente um par/grupo [a, b] (formato 2D)
                if isinstance(item[0], (int, float)):
                    if len(item) >= 2:
                        merges.append([int(x) for x in item])
                else:
                    # Caso contrário, `item` é uma camada contendo grupos [[a, b], ...] (formato 3D)
                    for group in item:
                        if isinstance(group, list) and len(group) >= 2 and isinstance(group[0], (int, float)):
                            merges.append([int(x) for x in group])
        return merges

    def _remove_segment_sorted(self, iv):
        idx = bisect.bisect_left(self.cached_segments, iv)
        if idx < len(self.cached_segments) and self.cached_segments[idx] == iv:
            self.cached_segments.pop(idx)

    def _insert_segment_sorted(self, iv):
        bisect.insort_left(self.cached_segments, iv)

    def fcluster(self, target_num_episodes):
        """
        Junta (ou separa) episódios a partir do recorte já calculado até atingir
        `target_num_episodes` e para, atualizando apenas o delta.
        """
        if self.base_num_episodes <= 0:
            return []

        target = max(1, min(int(target_num_episodes), self.base_num_episodes))
        curr_count = len(self.active_nodes)

        if target == curr_count:
            return self.cached_segments

        # Caso 1: Alvo tem MENOS episódios que o recorte atual -> avança juntando apenas o delta
        while len(self.active_nodes) > target and self.current_step < len(self.merges):
            step = self.current_step
            group = self.merges[step]
            parent_id = self.base_num_episodes + step

            starts = []
            ends = []
            for child_id in group:
                iv = self.active_nodes.pop(child_id, None)
                if iv is None:
                    iv = self.node_intervals.get(child_id)
                else:
                    self._remove_segment_sorted(iv)
                if iv is not None:
                    starts.append(iv[0])
                    ends.append(iv[1])

            if starts and ends:
                merged_iv = (min(starts), max(ends))
                self.node_intervals[parent_id] = merged_iv
                self.active_nodes[parent_id] = merged_iv
                self._insert_segment_sorted(merged_iv)

            self.current_step += 1

        # Caso 2: Alvo tem MAIS episódios que o recorte atual -> retrocede desfazendo apenas o delta
        while len(self.active_nodes) < target and self.current_step > 0:
            self.current_step -= 1
            step = self.current_step
            group = self.merges[step]
            parent_id = self.base_num_episodes + step

            parent_iv = self.active_nodes.pop(parent_id, None)
            if parent_iv is not None:
                self._remove_segment_sorted(parent_iv)

            for child_id in group:
                child_iv = self.node_intervals.get(child_id)
                if child_iv is not None and child_id not in self.active_nodes:
                    self.active_nodes[child_id] = child_iv
                    self._insert_segment_sorted(child_iv)

        return self.cached_segments

    def get_segments(self):
        return self.cached_segments

    def get_num_episodes(self):
        return len(self.cached_segments)


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
        self.loaded_labels = []  # Até 2 instâncias de HierarchicalLabelTrack
        self.target_num_episodes = None
        self._manual_fcluster_track = None
        self._manual_cuts_snapshot = None

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
        self._manual_fcluster_track = None
        self._manual_cuts_snapshot = None

    @property
    def has_loaded_labels(self):
        return len(self.loaded_labels) > 0

    @property
    def is_hierarchical_locked(self):
        """Se estiver no modo hierárquico e tiver carregado os labels, torna-os não editáveis."""
        return self.mode == self.MODE_HIERARCHICAL and self.has_loaded_labels

    def load_hierarchical_label_files(self, filepaths):
        """
        Carrega até 2 arquivos JSON de labels hierárquicas distintas.
        Se 1 label já estiver carregada e o usuário abrir mais 1 arquivo, adiciona como segunda label.
        Se o usuário selecionar 2 arquivos de uma vez, carrega ambos.
        """
        if not filepaths:
            return

        new_tracks = []
        for path in filepaths[:2]:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Caso o JSON seja um projeto salvo com `hierarchical_cuts`, converte para estrutura hierárquica
            if "first_layer_starts" not in data and "hierarchical_cuts" in data:
                temp_model = AnnotationModel(total_timeline_frames=self.total_frames, fps=self.fps)
                temp_model.hierarchical_cuts = data.get("hierarchical_cuts", [])
                data = temp_model.to_hierarchical_export_dict()

            track = HierarchicalLabelTrack(data, filepath=path, fallback_total_frames=self.total_frames)
            new_tracks.append(track)

        if not new_tracks:
            return

        if len(new_tracks) >= 2:
            self.loaded_labels = new_tracks[:2]
        elif len(new_tracks) == 1:
            if len(self.loaded_labels) == 1:
                # Permite abrir a segunda label distinta em seguida
                if self.loaded_labels[0].filepath == new_tracks[0].filepath:
                    self.loaded_labels[0] = new_tracks[0]
                else:
                    self.loaded_labels.append(new_tracks[0])
            else:
                self.loaded_labels = [new_tracks[0]]

        if self.target_num_episodes is not None:
            for track in self.loaded_labels:
                fcluster(track, self.target_num_episodes)

    def clear_loaded_labels(self):
        self.loaded_labels.clear()
        self.target_num_episodes = None
        self._manual_fcluster_track = None
        self._manual_cuts_snapshot = None

    def apply_fcluster(self, target_num_episodes):
        """
        Aplica a função `fcluster` para ajustar o número de episódios,
        reaproveitando o recorte já calculado e atualizando apenas o delta.
        """
        try:
            target = max(1, int(target_num_episodes))
        except (ValueError, TypeError):
            return

        self.target_num_episodes = target

        if self.has_loaded_labels:
            for track in self.loaded_labels:
                fcluster(track, target)
        else:
            snapshot = tuple(self.cuts_history)
            if self._manual_fcluster_track is None or self._manual_cuts_snapshot != snapshot:
                export_data = self.to_hierarchical_export_dict()
                self._manual_fcluster_track = HierarchicalLabelTrack(
                    export_data,
                    filepath="Manual",
                    fallback_total_frames=self.total_frames
                )
                self._manual_cuts_snapshot = snapshot
            fcluster(self._manual_fcluster_track, target)

    def set_total_frames(self, frames):
        old_frames = len(self.series)
        self.total_frames = max(1, frames)
        if self.total_frames > old_frames:
            new_series = np.full(self.total_frames + 1, -1, dtype=int)
            new_series[:old_frames] = self.series
            self.series = new_series
        else:
            self.series = self.series[:self.total_frames + 1]
        self._manual_fcluster_track = None
        self._manual_cuts_snapshot = None

    def reset_hierarchical(self):
        if self.is_hierarchical_locked:
            return
        self.cuts_history.clear()
        self._manual_fcluster_track = None
        self._manual_cuts_snapshot = None

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
        if self.has_loaded_labels:
            return self.loaded_labels[0].get_segments()

        snapshot = tuple(self.cuts_history)
        if self._manual_fcluster_track is not None and self._manual_cuts_snapshot == snapshot:
            return self._manual_fcluster_track.get_segments()

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
        if self.is_hierarchical_locked:
            return
        if 0 < frame_idx < self.total_frames:
            root, _ = self.build_tree()
            leaves = []
            def collect_leaves(node):
                if node.left is None and node.right is None:
                    leaves.append((node.start, node.end))
                else:
                    collect_leaves(node.left)
                    collect_leaves(node.right)
            collect_leaves(root)
            for start, end in leaves:
                if start < frame_idx < end:
                    self.cuts_history.append(frame_idx)
                    self._manual_fcluster_track = None
                    self._manual_cuts_snapshot = None
                    self.target_num_episodes = None
                    break

    def undo_hierarchical_cut(self):
        if self.is_hierarchical_locked:
            return
        if self.cuts_history:
            self.cuts_history.pop()
            self._manual_fcluster_track = None
            self._manual_cuts_snapshot = None
            self.target_num_episodes = None

    def to_hierarchical_export_dict(self):
        """Gera a estrutura JSON no formato específico de anotação hierárquica."""
        total_frames = self.total_frames
        cuts = self.cuts_history

        if not cuts:
            return {
                "number_steps": total_frames,
                "first_layer_starts": [0],
                "above_layers_groups": [[]]
            }

        root, history_records = self.build_tree()

        # Coleta as folhas em ordem cronológica
        leaves = []
        def collect_leaves(node):
            if node.left is None and node.right is None:
                leaves.append(node)
            else:
                collect_leaves(node.left)
                collect_leaves(node.right)

        collect_leaves(root)

        # Atribui IDs de 0 a N-1 para a camada mais granular
        first_layer_starts = []
        for idx, leaf in enumerate(leaves):
            leaf.group_id = idx
            first_layer_starts.append(leaf.start)

        next_id = len(leaves)
        joins = []

        # Processa as junções na ordem inversa dos cortes (bottom-up merge)
        for parent, left_child, right_child in reversed(history_records):
            joins.append([left_child.group_id, right_child.group_id])
            parent.group_id = next_id
            next_id += 1

        return {
            "number_steps": total_frames,
            "first_layer_starts": first_layer_starts,
            "above_layers_groups": [joins]
        }

    def to_categorical_export_dict(self):
        return {
            "number_steps": self.total_frames,
            "categories": self.available_labels,
            "categorical_annotations": self.categorical_annotations
        }

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