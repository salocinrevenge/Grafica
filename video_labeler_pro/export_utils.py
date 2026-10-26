import os
import json
import cv2
import numpy as np
from models import AnnotationModel

def export_project_data(export_folder, engine, model, progress_callback=None):
    """
    Exporta as anotações (.json) e os vídeos recortados/sincronizados.
    """
    # 1. Salvar Anotações
    if model.mode == AnnotationModel.MODE_HIERARCHICAL:
        ann_filename = "hierarchical_labels.json"
        ann_data = model.to_hierarchical_export_dict()
    else:
        ann_filename = "categorical_labels.json"
        ann_data = model.to_categorical_export_dict()

    ann_path = os.path.join(export_folder, ann_filename)
    with open(ann_path, "w", encoding="utf-8") as f:
        json.dump(ann_data, f, indent=4)

    # 2. Exportar Vídeos Recortados / Sincronizados
    total_timeline_frames = max(1, engine.get_total_timeline_frames())
    num_tracks = engine.get_num_tracks()

    if not engine.clips:
        return

    processed_paths = set()

    for t_idx in range(num_tracks):
        track_clips = [c for c in engine.clips if c.track_idx == t_idx]
        if not track_clips:
            continue

        primary_clip = track_clips[0]
        filepath = primary_clip.filepath
        
        base_name = os.path.basename(filepath)
        name_no_ext, ext = os.path.splitext(base_name)
        ext_clean = ext if ext.lower() in ['.mp4', '.avi', '.mov', '.mkv'] else '.mp4'
        out_filename = f"{name_no_ext}_syncronized{ext_clean}"
        
        counter = 1
        out_path = os.path.join(export_folder, out_filename)
        while out_path in processed_paths:
            out_filename = f"{name_no_ext}_{counter}_syncronized{ext_clean}"
            out_path = os.path.join(export_folder, out_filename)
            counter += 1
        processed_paths.add(out_path)

        cap = cv2.VideoCapture(filepath)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        fps = primary_clip.fps or cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

        caps = {}
        for c in track_clips:
            if c.filepath not in caps:
                caps[c.filepath] = cv2.VideoCapture(c.filepath)

        black_frame = np.zeros((height, width, 3), dtype=np.uint8)

        for f in range(total_timeline_frames):
            active_clip = None
            for c in track_clips:
                if c.timeline_start <= f < c.timeline_end:
                    active_clip = c
                    break

            if active_clip:
                src_frame = active_clip.global_to_source_frame(f)
                c_cap = caps.get(active_clip.filepath)
                if c_cap and src_frame is not None:
                    curr_pos = int(c_cap.get(cv2.CAP_PROP_POS_FRAMES))
                    if curr_pos != src_frame:
                        c_cap.set(cv2.CAP_PROP_POS_FRAMES, src_frame)
                    ret, frame = c_cap.read()
                    if ret and frame is not None:
                        if frame.shape[1] != width or frame.shape[0] != height:
                            frame = cv2.resize(frame, (width, height))
                        writer.write(frame)
                    else:
                        writer.write(black_frame)
                else:
                    writer.write(black_frame)
            else:
                writer.write(black_frame)

            if progress_callback:
                progress_callback(t_idx, num_tracks, f, total_timeline_frames)

        writer.release()
        for c_cap in caps.values():
            c_cap.release()