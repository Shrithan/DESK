"""Optional EdgeTAM corrections; optical flow still owns the frame-rate path.

One shared model, independent bounded camera memories. No GPU work runs on a
camera request thread. Upstream is loaded only when explicitly enabled.
"""
from pathlib import Path
import sys
import tempfile
import time

import cv2
import numpy as np


class EdgeTAMModel:
    def __init__(self, source, checkpoint, device, lock):
        source = Path(source).resolve()
        checkpoint = Path(checkpoint).resolve()
        if not (source / 'sam2/build_sam.py').is_file() or not checkpoint.is_file():
            raise FileNotFoundError('EdgeTAM source/checkpoint missing; see docs/temporal-tracking.md')
        sys.path.insert(0, str(source))
        import torch
        import sam2.modeling.backbones.timm as backbone
        from sam2.build_sam import build_sam2_video_predictor
        # The full checkpoint includes the backbone. Avoid downloading a second
        # set of ImageNet weights that would immediately be overwritten.
        original = backbone.create_model
        def without_pretrained(*args, **kwargs):
            return original(*args, **dict(kwargs, pretrained=False))
        backbone.create_model = without_pretrained
        try:
            with torch.inference_mode():
                self.predictor = build_sam2_video_predictor(
                    'configs/edgetam.yaml', str(checkpoint), device=device,
                    apply_postprocessing=False)
        finally:
            backbone.create_model = original
        self.lock = lock
        self.torch = torch

    def camera(self, detector):
        return TemporalCamera(self, detector)


class TemporalCamera:
    """Worker-only camera state. Re-enroll periodically to bound GPU memory.

    Detector refreshes discover new objects; temporal outputs carry the enrolled
    track ID and may never enroll a new object or impersonate a different ID.
    """
    max_objects = 4
    max_steps = 24
    semantic_interval = 1.0

    def __init__(self, model, detector):
        self.model, self.detector = model, detector
        self.state = None
        self.steps = 0
        self.last_semantic = -float('inf')
        self.last_ms = None
        self.status = 'waiting for enrolled objects'

    def reset(self):
        self.state = None
        self.steps = 0

    def detect(self, frame, seeds):
        start = time.perf_counter()
        enrolled = self.state['obj_ids'] if self.state else []
        seeds = [s for s in seeds if s.get('tracked', True) or s['track_id'] in enrolled]
        if not seeds or time.monotonic() - self.last_semantic >= self.semantic_interval:
            detections = self.detector.detect(frame)
            self.last_semantic = time.monotonic()
            self.reset()  # next temporal step uses the refreshed fast-tracker masks
            self.status = 'YOLOE discovery / refresh'
            return detections
        seeds = seeds[:self.max_objects]
        torch = self.model.torch
        with self.model.lock, torch.inference_mode():
            ids = [s['track_id'] for s in seeds]
            shape = frame.shape[:2]
            if (self.state is None or self.steps >= self.max_steps or
                    self.state['obj_ids'] != ids or
                    (self.state['video_height'], self.state['video_width']) != shape):
                self._enroll(frame, seeds)
                idx = 0
            else:
                idx = self.steps
                self.state['images'] = {idx: self._image(frame)}
                self.state['num_frames'] = idx + 1
            result = None
            for result in self.model.predictor.propagate_in_video(
                    self.state, start_frame_idx=idx, max_frame_num_to_track=0):
                pass  # exhaust generator so upstream tracking bookkeeping completes
            self.steps = idx + 1
            if result is None:
                return []
            _, object_ids, logits = result
            masks = (logits[:, 0] > 0).cpu().numpy()
        self.last_ms = round((time.perf_counter() - start) * 1000, 1)
        if idx == 0:
            self.status = 'EdgeTAM enrolled; waiting for next frame'
            return []  # initial prompt masks are not independent tracking evidence
        self.status = 'EdgeTAM temporal correction'
        labels = {s['track_id']: s['label'] for s in seeds}
        detections = []
        h, w = shape
        for oid, mask in zip(object_ids, masks):
            ys, xs = np.nonzero(mask)
            if not 48 < len(xs) < .65 * h * w:
                continue  # absent/ambiguous masks never become control measurements
            contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour = max(contours, key=cv2.contourArea)
            detections.append(dict(track_id=oid, label=labels[oid], score=.8,
                mask=mask.astype(np.uint8)*255,
                bbox=[int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)],
                center=[float(xs.mean()), float(ys.mean())],
                contour=cv2.approxPolyDP(contour, 2., True).reshape(-1, 2).tolist()))
        return detections

    def _enroll(self, frame, seeds):
        self.reset()
        # Upstream init_state expects a video/directory. Only the initialization
        # frame touches a temporary directory; it is removed before returning.
        with tempfile.TemporaryDirectory(prefix='desk-edgetam-') as directory:
            if not cv2.imwrite(str(Path(directory) / '00000.jpg'), frame):
                raise RuntimeError('Could not initialize EdgeTAM frame')
            self.state = self.model.predictor.init_state(directory, offload_video_to_cpu=True)
        for seed in seeds:
            self.model.predictor.add_new_mask(self.state, frame_idx=0,
                obj_id=seed['track_id'], mask=seed['mask'] > 0)

    def _image(self, frame):
        # Same RGB/ImageNet normalization as upstream JPEG loader.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        size = self.model.predictor.image_size
        rgb = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_LINEAR)
        image = self.model.torch.from_numpy(rgb.copy()).permute(2, 0, 1).float() / 255.
        mean = self.model.torch.tensor([.485, .456, .406])[:, None, None]
        std = self.model.torch.tensor([.229, .224, .225])[:, None, None]
        return (image - mean) / std
