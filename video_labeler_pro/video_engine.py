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