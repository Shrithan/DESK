"""Conservative CPU tracker. Quality metrics are heuristics, not probabilities."""
from dataclasses import dataclass
from uuid import uuid4
import cv2
import numpy as np


@dataclass
class Target:
    object_id: str
    gray: np.ndarray
    mask: np.ndarray
    points: np.ndarray
    ids: list[str]
    state: str = "tracked"


class Tracker:
    def __init__(self):
        self.targets = {}
        self.last_timestamp = {}

    def select(self, frame, camera_id, pixel_x, pixel_y, timestamp_ms,
               calibration_version, mask=None):
        """Select a connected color region, or accept an externally prompted mask.

        Flood fill is a restricted fallback: it can reject textured objects or
        leak onto similar backgrounds. Caller must show mask for confirmation.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        x, y = int(pixel_x), int(pixel_y)
        if not (0 <= x < w and 0 <= y < h):
            raise ValueError("selection is outside image")
        if mask is None:
            flood = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(frame.copy(), flood, (x, y), 0, (35,)*3, (35,)*3,
                          cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))
            mask = flood[1:-1, 1:-1]
        mask = np.asarray(mask, np.uint8)
        if mask.shape != gray.shape or not mask[y, x]:
            raise ValueError("mask must match image and contain click")
        area = np.count_nonzero(mask)
        if area < 40 or area > h*w*.65:
            raise ValueError("ambiguous region; supply a confirmed segmentation mask")
        points = cv2.goodFeaturesToTrack(gray, 150, .01, 5, mask=mask)
        if points is None or len(points) < 6:
            raise ValueError("target lacks enough trackable texture")
        object_id = 'obj_' + uuid4().hex[:12]
        target = Target(object_id, gray, mask.copy(), points,
                        [f'{object_id}:f_{i}' for i in range(len(points))])
        self.targets[(camera_id, object_id)] = target
        self.last_timestamp[(camera_id, object_id)] = timestamp_ms
        return self._observation(target, camera_id, timestamp_ms, calibration_version)

    def deselect(self, camera_id, object_id):
        self.last_timestamp.pop((camera_id, object_id), None)
        return self.targets.pop((camera_id, object_id), None) is not None

    def update(self, frame, camera_id, timestamp_ms, calibration_version):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        observations = []
        for (cam, oid), target in self.targets.items():
            if cam != camera_id:
                continue
            key = (cam, oid)
            if timestamp_ms <= self.last_timestamp[key]:
                raise ValueError("timestamps must increase per camera and object")
            gap = timestamp_ms - self.last_timestamp[key]
            self.last_timestamp[key] = timestamp_ms
            if target.state == 'lost':
                observations.append(self._observation(target, cam, timestamp_ms, calibration_version))
                continue
            valid = None
            if gray.shape == target.gray.shape and gap <= 500:
                nxt, status, _ = cv2.calcOpticalFlowPyrLK(target.gray, gray, target.points, None)
                if nxt is not None:
                    back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, target.gray, nxt, None)
                    if back is not None:
                        valid = (status.ravel() == 1) & (back_status.ravel() == 1)
                        valid &= np.linalg.norm(back-target.points, axis=2).ravel() < 1.0
            if valid is None or valid.sum() < max(6, len(target.points)*.5):
                target.state = 'lost'
            else:
                old = target.points[valid]
                new = nxt[valid]
                transform, inliers = cv2.estimateAffinePartial2D(old, new, method=cv2.RANSAC,
                                                               ransacReprojThreshold=2)
                if transform is None or inliers.sum() < max(6, len(old)*.7):
                    target.state = 'lost'
                else:
                    keep = inliers.ravel().astype(bool)
                    target.ids = [fid for fid, ok in zip(target.ids, valid) if ok]
                    target.ids = [fid for fid, ok in zip(target.ids, keep) if ok]
                    target.points = new[keep]
                    target.mask = cv2.warpAffine(target.mask, transform, (gray.shape[1], gray.shape[0]),
                                                  flags=cv2.INTER_NEAREST)
                    if np.count_nonzero(target.mask) < 40:
                        target.state = 'lost'
                    target.gray = gray
            observations.append(self._observation(target, cam, timestamp_ms, calibration_version))
        return observations

    @staticmethod
    def _observation(target, camera, timestamp, calibration):
        visible = target.state == 'tracked'
        x, y, w, h = cv2.boundingRect(target.mask) if visible else (0, 0, 0, 0)
        return dict(type='object_observation', schema_version='vision.proposal.v1',
                    timestamp_ms=timestamp, camera_id=camera, object_id=target.object_id,
                    calibration_version=calibration, bbox_xyxy=[x,y,x+w,y+h] if visible else None,
                    mask_ref=None, confidence=None, tracking_state=target.state,
                    features=[dict(track_id=fid, pixel_xy=p[0].tolist())
                              for fid,p in zip(target.ids,target.points)] if visible else [],
                    quality={'feature_count': len(target.points) if visible else 0})
