"""Single-can segmentation + ByteTrack lock, with optical flow between model runs.

Model order: YOLOE-seg with text prompts ('soda can', 'aluminum can') -> YOLO-World boxes
(an ellipse inscribed in the box stands in for the mask). Uses the repo's prepared
YOLOE weights (vision/prepare_model.py) when present. Runs model.track(persist=True,
tracker=bytetrack.yaml) and locks onto the track id chosen at calibration.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from tilt_joystick.config import DetectorConfig
from tilt_joystick.features import MaskFeatures, mask_features

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Detection:
    mask: np.ndarray
    score: float
    track_id: int | None
    bbox: tuple[float, float, float, float]
    kind: str = 'seg'  # seg | box | flow


@dataclass
class Timing:
    stages: dict[str, float] = field(default_factory=dict)

    def mark(self, name: str, start: float) -> float:
        now = time.perf_counter()
        self.stages[name] = (now - start) * 1000
        return now


def pick_device(device: str) -> str:
    if device != 'auto':
        return device
    import torch
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


class CanDetector:
    def __init__(self, cfg: DetectorConfig) -> None:
        self.cfg = cfg
        os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'outputs/.ultralytics'))
        import ultralytics
        from ultralytics import YOLO
        self.version = ultralytics.__version__
        self.device = pick_device(cfg.device)
        self.mode, self.model = 'seg', None
        weights = ROOT / cfg.weights if not Path(cfg.weights).is_absolute() else Path(cfg.weights)
        errors = []
        try:
            from ultralytics import YOLOE  # ultralytics >= 8.3.99
            if not weights.is_file():
                raise FileNotFoundError(f'{weights} missing; run python -m vision.prepare_model --size s')
            self.model = YOLOE(str(weights))
            self._set_prompts()
        except Exception as exc:  # no YOLOE in this ultralytics, or no weights
            errors.append(f'YOLOE: {exc}')
            try:
                from ultralytics import YOLOWorld
                self.model = YOLOWorld(cfg.fallback_weights)
                self.model.set_classes(list(cfg.prompts))
                self.mode = 'box'
            except Exception as exc2:
                errors.append(f'YOLO-World: {exc2}')
                raise RuntimeError('no can detector available: ' + '; '.join(errors)) from exc2
        self.notes = errors
        self.labels = {s.lower() for s in cfg.labels} | {s.lower() for s in cfg.prompts}
        self.locked_id: int | None = None
        self.prev_gray = None
        self.prev_det: Detection | None = None
        self.frame_i = 0
        self.model_ms = 0.0
        self.track(np.zeros((360, 640, 3), np.uint8))  # warm-up so the first real frame is fast
        self.reset_lock()

    def _set_prompts(self) -> None:
        """Narrow the vocabulary to the can prompts if the text encoder is available (faster, fewer
        false positives). The prepared desk weights already contain 'soda can', so failure is fine."""
        names = list(self.cfg.prompts)
        try:
            self.model.set_classes(names, self.model.get_text_pe(names))
        except Exception:
            try:
                self.model.set_classes(names)
            except Exception as exc:
                self.notes = [f'kept prepared prompt set ({exc.__class__.__name__})']

    def describe(self) -> str:
        return f'ultralytics {self.version}, {"YOLOE-seg" if self.mode == "seg" else "YOLO-World boxes"}, {self.device}'

    def reset_lock(self) -> None:
        self.locked_id = None
        self.prev_det = None
        self.prev_gray = None

    # -------------------------------------------------------------- model
    def _model_detections(self, frame: np.ndarray) -> list[Detection]:
        t = time.perf_counter()
        result = self.model.track(frame, persist=True, tracker=self.cfg.tracker, conf=self.cfg.confidence,
                                  imgsz=self.cfg.image_size, device=self.device, verbose=False,
                                  retina_masks=self.mode == 'seg')[0]
        self.model_ms = (time.perf_counter() - t) * 1000
        h, w = frame.shape[:2]
        out = []
        if result.boxes is None:
            return out
        polys = result.masks.xy if (self.mode == 'seg' and result.masks is not None) else [None] * len(result.boxes)
        for box, poly in zip(result.boxes, polys):
            if result.names[int(box.cls.item())].lower() not in self.labels:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            mask = np.zeros((h, w), np.uint8)
            if poly is not None and len(poly) >= 3:
                cv2.fillPoly(mask, [np.round(poly).astype(np.int32)], 255)
                kind = 'seg'
            else:
                cv2.ellipse(mask, ((x1 + x2) / 2, (y1 + y2) / 2), ((x2 - x1) / 2, (y2 - y1) / 2), 0, 0, 360, 255, -1)
                kind = 'box'
            tid = int(box.id.item()) if box.id is not None else None
            out.append(Detection(mask, float(box.conf.item()), tid, (x1, y1, x2, y2), kind))
        return out

    def _choose(self, dets: list[Detection]) -> Detection | None:
        if not dets:
            return None
        if self.locked_id is not None:
            same = [d for d in dets if d.track_id == self.locked_id]
            if same:
                return same[0]
        if self.prev_det is not None:  # id switched (ByteTrack re-init): nearest to where the can was
            px, py = _centre(self.prev_det.bbox)
            best = min(dets, key=lambda d: np.hypot(*np.subtract(_centre(d.bbox), (px, py))))
            if np.hypot(*np.subtract(_centre(best.bbox), (px, py))) < 1.5 * _size(self.prev_det.bbox):
                self.locked_id = best.track_id
                return best
            return None
        best = max(dets, key=lambda d: d.score * np.sqrt(np.count_nonzero(d.mask)))  # biggest confident can
        self.locked_id = best.track_id
        return best

    # -------------------------------------------------------------- flow
    def _flow(self, gray: np.ndarray) -> Detection | None:
        """Translate the last mask by the median sparse-flow motion of points inside it."""
        prev = self.prev_det
        if prev is None or self.prev_gray is None:
            return None
        pts = cv2.goodFeaturesToTrack(self.prev_gray, 60, .01, 4, mask=prev.mask)
        if pts is None or len(pts) < 6:
            return None
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(self.prev_gray, gray, pts, None, winSize=(21, 21), maxLevel=3)
        good = st.ravel() == 1
        if good.sum() < 6:
            return None
        dx, dy = np.median((nxt - pts).reshape(-1, 2)[good], axis=0)
        m = np.float32([[1, 0, dx], [0, 1, dy]])
        mask = cv2.warpAffine(prev.mask, m, (gray.shape[1], gray.shape[0]), flags=cv2.INTER_NEAREST)
        x1, y1, x2, y2 = prev.bbox
        return Detection(mask, prev.score * .9, prev.track_id, (x1 + dx, y1 + dy, x2 + dx, y2 + dy), 'flow')

    def track(self, frame: np.ndarray) -> tuple[Detection | None, MaskFeatures | None]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        run_model = self.frame_i % max(1, self.cfg.detect_every) == 0 or self.prev_det is None
        self.frame_i += 1
        det = self._choose(self._model_detections(frame)) if run_model else self._flow(gray)
        if det is None and not run_model:
            det = self._choose(self._model_detections(frame))
        self.prev_det, self.prev_gray = det, gray
        return det, (mask_features(det.mask, det.score) if det is not None else None)


def _centre(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _size(b):
    return max(b[2] - b[0], b[3] - b[1])
