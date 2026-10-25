"""Single-can segmentation + ByteTrack lock, with per-frame ROI optical flow.

Model: YOLOE-seg with text prompts ('soda can', 'aluminum can'), falling back to YOLO-World
boxes (an ellipse inscribed in the box stands in for the outline). It uses the repo's prepared
YOLOE weights (vision/prepare_model.py). model.track(persist=True, tracker=bytetrack.yaml)
locks onto the track id picked at calibration.

Latency design (async_model, the default):
* The model runs in a background thread on the newest frame.
* Every frame, the can outline (a polygon, never a full-frame mask) is carried forward by
  sparse LK flow inside a small ROI around the can, using a full affine so the stretch of a
  tilt is followed, not just the shift. That costs ~1 ms, so model time (15-40 ms) is off the
  frame->key path.
* When a model result arrives (from frame k), its outline is flowed from frame k to the
  current frame before use, so it is never stale.
* Shape statistics come from polygon moments (Green's theorem). No mask is rasterised in the
  loop.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from tilt_joystick.config import DetectorConfig
from tilt_joystick.features import MaskFeatures

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Detection:
    polygon: np.ndarray  # (N, 2) float32, processing-frame pixels
    score: float
    track_id: int | None
    kind: str = 'seg'  # seg | box | flow

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        x1, y1 = self.polygon.min(axis=0)
        x2, y2 = self.polygon.max(axis=0)
        return float(x1), float(y1), float(x2), float(y2)

    @property
    def area(self) -> float:
        return abs(float(cv2.contourArea(self.polygon)))


def polygon_features(poly: np.ndarray, score: float = 1.0) -> MaskFeatures | None:
    m = cv2.moments(poly.astype(np.float32))
    a = m['m00']
    if abs(a) < 30:
        return None
    return MaskFeatures(cx=m['m10'] / a, cy=m['m01'] / a, area=abs(a),
                        cxx=m['mu20'] / a, cxy=m['mu11'] / a, cyy=m['mu02'] / a, confidence=float(score))


def pick_device(device: str) -> str:
    if device != 'auto':
        return device
    import torch
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


def flow_polygon(prev_gray: np.ndarray, gray: np.ndarray, poly: np.ndarray) -> np.ndarray | None:
    """Carry an outline from prev_gray to gray with LK flow in a padded ROI. Returns None if lost."""
    h, w = gray.shape
    x1, y1 = np.floor(poly.min(axis=0)).astype(int)
    x2, y2 = np.ceil(poly.max(axis=0)).astype(int)
    pad = int(max(x2 - x1, y2 - y1) * .6) + 8
    x1, y1, x2, y2 = max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    a, b = prev_gray[y1:y2, x1:x2], gray[y1:y2, x1:x2]
    m = np.zeros(a.shape, np.uint8)
    cv2.fillPoly(m, [np.round(poly - (x1, y1)).astype(np.int32)], 255)
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))  # include the rim edge, where tilt shows
    pts = cv2.goodFeaturesToTrack(a, 80, .01, 3, mask=m)
    if pts is None or len(pts) < 5:
        return None
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(15, 15), maxLevel=3,
                                          criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, .03))
    back, st2, _ = cv2.calcOpticalFlowPyrLK(b, a, nxt, None, winSize=(15, 15), maxLevel=3)
    good = (st.ravel() == 1) & (st2.ravel() == 1) & (np.linalg.norm((back - pts).reshape(-1, 2), axis=1) < 1.0)
    p0, p1 = pts.reshape(-1, 2)[good], nxt.reshape(-1, 2)[good]
    if len(p0) < 5:
        return None
    M = None
    if len(p0) >= 8:
        M, inl = cv2.estimateAffine2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=1.5)
        if M is not None and (inl is None or inl.sum() < 6 or not .6 < abs(np.linalg.det(M[:, :2])) < 1.6):
            M = None
    if M is None:
        d = np.median(p1 - p0, axis=0)
        M = np.float32([[1, 0, d[0]], [0, 1, d[1]]])
    local = poly - (x1, y1)
    out = local @ M[:, :2].T + M[:, 2]
    return (out + (x1, y1)).astype(np.float32)


class CanDetector:
    def __init__(self, cfg: DetectorConfig, load_model: bool = True) -> None:
        self.cfg = cfg
        self.mode, self.model, self.notes = 'seg', None, []
        self.version, self.device = '-', 'cpu'
        self.model_ms = 0.0
        self.flow_ms = 0.0
        self.frame_i = 0
        self._lock = threading.Lock()
        self._job: tuple | None = None  # newest frame waiting for the model
        self._result: tuple | None = None  # (frame_i, gray, detections)
        self._wake = threading.Event()
        self._stop = False
        self._worker: threading.Thread | None = None
        self.reset_lock()
        if load_model:
            self._load()
            self._model_detections(np.zeros((360, 640, 3), np.uint8))  # warm-up: first real frame is fast
            self.reset_lock()

    # -------------------------------------------------------------- model
    def _load(self) -> None:
        os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'outputs/.ultralytics'))
        import ultralytics
        self.version = ultralytics.__version__
        self.device = pick_device(self.cfg.device)
        weights = Path(self.cfg.weights) if Path(self.cfg.weights).is_absolute() else ROOT / self.cfg.weights
        errors = []
        try:
            from ultralytics import YOLOE  # ultralytics >= 8.3.99
            if not weights.is_file():
                raise FileNotFoundError(f'{weights} missing; run python3 -m vision.prepare_model --size s')
            self.model = YOLOE(str(weights))
            self._set_prompts()
        except Exception as exc:  # no YOLOE in this ultralytics, or no weights
            errors.append(f'YOLOE: {exc}')
            try:
                from ultralytics import YOLOWorld
                self.model = YOLOWorld(self.cfg.fallback_weights)
                self.model.set_classes(list(self.cfg.prompts))
                self.mode = 'box'
            except Exception as exc2:
                errors.append(f'YOLO-World: {exc2}')
                raise RuntimeError('no can detector available: ' + '; '.join(errors)) from exc2
        self.notes += errors
        self.labels = {s.lower() for s in self.cfg.labels} | {s.lower() for s in self.cfg.prompts}

    def _set_prompts(self) -> None:
        """Narrow the vocabulary to the can prompts when the text encoder is available (faster, fewer
        false positives). The prepared desk weights already contain 'soda can', so failure is fine."""
        names = list(self.cfg.prompts)
        try:
            self.model.set_classes(names, self.model.get_text_pe(names))
        except Exception:
            try:
                self.model.set_classes(names)
            except Exception as exc:
                self.notes.append(f'kept prepared prompt set ({exc.__class__.__name__})')

    def describe(self) -> str:
        kind = 'YOLOE-seg' if self.mode == 'seg' else 'YOLO-World boxes'
        how = 'async model + per-frame ROI flow' if self.cfg.async_model else f'model every {self.cfg.detect_every} frame(s)'
        return f'ultralytics {self.version}, {kind}, {self.device}, {how}'

    def _model_detections(self, frame: np.ndarray) -> list[Detection]:
        t = time.perf_counter()
        result = self.model.track(frame, persist=True, tracker=self.cfg.tracker, conf=self.cfg.confidence,
                                  imgsz=self.cfg.image_size, device=self.device, verbose=False,
                                  retina_masks=False)[0]
        self.model_ms = (time.perf_counter() - t) * 1000
        out = []
        if result.boxes is None:
            return out
        polys = result.masks.xy if (self.mode == 'seg' and result.masks is not None) else [None] * len(result.boxes)
        for box, poly in zip(result.boxes, polys):
            if result.names[int(box.cls.item())].lower() not in self.labels:
                continue
            tid = int(box.id.item()) if box.id is not None else None
            if poly is not None and len(poly) >= 3:
                out.append(Detection(np.asarray(poly, np.float32), float(box.conf.item()), tid, 'seg'))
            else:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                e = cv2.ellipse2Poly((int((x1 + x2) / 2), int((y1 + y2) / 2)), (int((x2 - x1) / 2), int((y2 - y1) / 2)),
                                     0, 0, 360, 10)
                out.append(Detection(e.astype(np.float32), float(box.conf.item()), tid, 'box'))
        return out

    def _choose(self, dets: list[Detection]) -> Detection | None:
        if not dets:
            return None
        if self.locked_id is not None:
            same = [d for d in dets if d.track_id == self.locked_id]
            if same:
                return same[0]
        if self.prev_det is not None:  # id switched (ByteTrack re-init): nearest to where the can was
            pc = _centre(self.prev_det.bbox)
            best = min(dets, key=lambda d: np.hypot(*np.subtract(_centre(d.bbox), pc)))
            if np.hypot(*np.subtract(_centre(best.bbox), pc)) < 1.5 * _size(self.prev_det.bbox):
                self.locked_id = best.track_id
                return best
            return None
        best = max(dets, key=lambda d: d.score * np.sqrt(d.area))  # biggest confident can
        self.locked_id = best.track_id
        return best

    def reset_lock(self) -> None:
        self.locked_id = None
        self.prev_det = None
        self.prev_gray = None

    # -------------------------------------------------------------- async worker
    def _run_worker(self) -> None:
        while not self._stop:
            self._wake.wait(0.5)
            self._wake.clear()
            with self._lock:
                job, self._job = self._job, None
            if job is None:
                continue
            i, frame, gray = job
            try:
                dets = self._model_detections(frame)
            except Exception as exc:  # keep tracking on flow; surface the error once
                self.notes.append(f'model error: {exc}')
                dets = []
            with self._lock:
                self._result = (i, gray, dets)

    def _submit(self, frame: np.ndarray, gray: np.ndarray) -> None:
        if self._worker is None:
            self._worker = threading.Thread(target=self._run_worker, daemon=True, name='can-model')
            self._worker.start()
        with self._lock:
            self._job = (self.frame_i, frame, gray)  # replaces any older waiting frame
        self._wake.set()

    def close(self) -> None:
        self._stop = True
        self._wake.set()

    # -------------------------------------------------------------- per frame
    def track(self, frame: np.ndarray) -> tuple[Detection | None, MaskFeatures | None]:
        """frame is already at processing size. Returns the locked can in this frame."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.frame_i += 1
        t = time.perf_counter()
        det = None
        if self.cfg.async_model:
            with self._lock:
                result, self._result = self._result, None
            if result is not None:
                _, rgray, dets = result
                chosen = self._choose(dets)
                if chosen is not None:
                    poly = flow_polygon(rgray, gray, chosen.polygon)  # bring the model's outline up to now
                    det = Detection(poly, chosen.score, chosen.track_id, chosen.kind) if poly is not None else None
            if det is None and self.prev_det is not None:
                poly = flow_polygon(self.prev_gray, gray, self.prev_det.polygon)
                if poly is not None:
                    det = Detection(poly, self.prev_det.score, self.prev_det.track_id, 'flow')
            self._submit(frame, gray)  # model always works on the newest frame
        else:
            run_model = (self.frame_i - 1) % max(1, self.cfg.detect_every) == 0 or self.prev_det is None
            if not run_model:
                poly = flow_polygon(self.prev_gray, gray, self.prev_det.polygon)
                det = Detection(poly, self.prev_det.score, self.prev_det.track_id, 'flow') if poly is not None else None
            if det is None:
                det = self._choose(self._model_detections(frame))
        self.flow_ms = (time.perf_counter() - t) * 1000
        self.prev_det, self.prev_gray = det, gray
        return det, (polygon_features(det.polygon, det.score) if det is not None else None)


def _centre(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _size(b):
    return max(b[2] - b[0], b[3] - b[1])
