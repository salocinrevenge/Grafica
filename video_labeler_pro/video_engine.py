import os
# Desativa decodificação paralela instável do FFmpeg
os.environ["OPENCV_FFMPEG_THREAD_COUNT"] = "1"

import cv2
import pygame

class VideoClip:
    def __init__(self, path, clip_id, fps, total_frames):
        self.path = path
        self.clip_id = clip_id
        self.fps = fps
        self.duration_frames = total_frames
        self.enabled = False  # Controlado pelo botão de olho
        self.cap = cv2.VideoCapture(path)
        
        # Cache de renderização
        self.last_frame_idx = -1
        self.last_surface = None

    @property
    def filename(self):
        return os.path.basename(self.path)

    @property
    def timeline_start(self):
        return 0  # Em trilhas paralelas, todos iniciam no frame 0

    @property
    def timeline_end(self):
        return self.duration_frames

    def get_frame_surface(self, local_frame, target_height=540):
        if local_frame < 0 or local_frame >= self.duration_frames:
            return None

        if local_frame == self.last_frame_idx and self.last_surface is not None:
            return self.last_surface

        if local_frame == self.last_frame_idx + 1:
            ret, frame = self.cap.read()
        else:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, local_frame)
            ret, frame = self.cap.read()

        if not ret or frame is None:
            return self.last_surface

        self.last_frame_idx = local_frame

        h, w, _ = frame.shape
        aspect_ratio = w / h
        target_width = int(target_height * aspect_ratio)

        frame_resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        frame_rgb = frame_rgb.swapaxes(0, 1)

        self.last_surface = pygame.surfarray.make_surface(frame_rgb)
        return self.last_surface

    def release(self):
        if self.cap:
            self.cap.release()


class MultiVideoEngine:
    def __init__(self):
        self.clips = []

    def add_clip(self, clip):
        self.clips.append(clip)

    def clear(self):
        for clip in self.clips:
            clip.release()
        self.clips.clear()

    def get_total_timeline_frames(self):
        if not self.clips:
            return 0
        # A duração total da timeline paralela é a duração do maior vídeo
        return max(c.duration_frames for c in self.clips)

    def get_enabled_clips(self):
        return [c for c in self.clips if c.enabled]

    def toggle_clip_enabled(self, clip_idx):
        """Alterna a visibilidade do vídeo respeitando o limite máximo de 2 ativos."""
        if 0 <= clip_idx < len(self.clips):
            clip = self.clips[clip_idx]
            enabled_count = len(self.get_enabled_clips())
            
            if clip.enabled:
                clip.enabled = False
            else:
                if enabled_count < 2:
                    clip.enabled = True
                    return True
                else:
                    return False  # Bloqueado (já existem 2 habilitados)
        return False