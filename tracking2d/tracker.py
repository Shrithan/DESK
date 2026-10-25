"""Conservative CPU tracker. Quality metrics are heuristics, not probabilities."""
from dataclasses import dataclass
from uuid import uuid4
import cv2
import time

import numpy as np


@dataclass(frozen=True)
class TrackingTuning:
    flow_error_px: float = 1.0
    surviving_fraction: float = .5
    inlier_fraction: float = .7
    ransac_error_px: float = 2.0
    max_gap_ms: int = 500
    grace_ms: int = 0
    flow_window: int = 21
    pyramid_levels: int = 3

    @classmethod
    def responsive(cls):
        return cls(flow_error_px=2.,surviving_fraction=.3,inlier_fraction=.55,
                   ransac_error_px=3.,max_gap_ms=800,grace_ms=350,flow_window=41,pyramid_levels=4)


@dataclass
class Target:
    object_id: str
    gray: np.ndarray
    mask: np.ndarray
    points: np.ndarray
    ids: list[str]
    state: str = "tracked"
    last_good_ms: int = 0
    reference_gray: np.ndarray | None = None
    reference_mask: np.ndarray | None = None
    reference_keypoints: object = None
    reference_descriptors: np.ndarray | None = None
    recovery_box: object = None
    recovery_hits: int = 0
    recovery_generation: int = 0
    velocity: np.ndarray | None = None   # px per ms of the object's centre, from recent tracked frames
    last_update_ms: int = 0
    last_recover_ms: int = -10**9
    seed_count: int = 0


class Tracker:
    def __init__(self, tuning=None, *, normalize_illumination=False):
        from tracking2d.illumination import IlluminationNormalizer
        self.illumination=IlluminationNormalizer() if normalize_illumination else None
        self.tuning=tuning or TrackingTuning()
        self.targets = {}
        self.last_timestamp = {}
        self.detector = cv2.SIFT_create(nfeatures=1800)

    def select(self, frame, camera_id, pixel_x, pixel_y, timestamp_ms,
               calibration_version, mask=None, *, allow_textureless=False):
        """Select a connected color region, or accept an externally prompted mask.

        Flood fill is a restricted fallback: it can reject textured objects or
        leak onto similar backgrounds. Caller must show mask for confirmation.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.illumination is not None:gray=self.illumination.apply(gray)
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
            if not allow_textureless:
                raise ValueError("target lacks enough trackable texture")
            points=np.empty((0,1,2),dtype=np.float32)
        object_id = 'obj_' + uuid4().hex[:12]
        target = Target(object_id, gray, mask.copy(), points,
                        [f'{object_id}:f_{i}' for i in range(len(points))])
        target.last_good_ms=timestamp_ms
        target.reference_gray = gray.copy()
        target.reference_mask = mask.copy()
        target.reference_keypoints, target.reference_descriptors = self.detector.detectAndCompute(gray, mask)
        self.targets[(camera_id, object_id)] = target
        self.last_timestamp[(camera_id, object_id)] = timestamp_ms
        return self._observation(target, camera_id, timestamp_ms, calibration_version)

    def deselect(self, camera_id, object_id):
        self.last_timestamp.pop((camera_id, object_id), None)
        return self.targets.pop((camera_id, object_id), None) is not None

    def update(self, frame, camera_id, timestamp_ms, calibration_version, *, recover_lost=True, recover_ids=()):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.illumination is not None:gray=self.illumination.apply(gray)
        observations = []
        for (cam, oid), target in self.targets.items():
            if cam != camera_id:
                continue
            key = (cam, oid)
            if timestamp_ms <= self.last_timestamp[key]:
                raise ValueError("timestamps must increase per camera and object")
            gap = timestamp_ms - target.last_good_ms
            self.last_timestamp[key] = timestamp_ms
            if target.state == 'lost':
                # Full-frame SIFT recovery can cost tens of ms on a 640+ px frame. Only when it was
                # actually slow, skip it for ~3x its cost so it cannot starve tracking of other objects.
                if (recover_lost or oid in recover_ids) and timestamp_ms >= target.last_recover_ms:
                    started = time.perf_counter()
                    self._recover(target, gray)
                    cost_ms = (time.perf_counter() - started) * 1000
                    target.last_recover_ms = timestamp_ms + (int(3 * cost_ms) if cost_ms > 25 else 0)
                if target.state=='tracked':target.last_good_ms=timestamp_ms
                observations.append(self._observation(target, cam, timestamp_ms, calibration_version))
                continue
            if len(target.points)<6:
                target.state='lost'
                observations.append(self._observation(target,cam,timestamp_ms,calibration_version))
                continue
            valid = None
            # Flow anchors remain on the last measured frame through a dropout.
            dt = max(1, timestamp_ms - target.last_good_ms)
            if gray.shape == target.gray.shape and gap <= self.tuning.max_gap_ms:
                nxt, status = self._flow(target, gray, dt)
                if nxt is not None:
                    back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, target.gray, nxt, None,
                            winSize=(self.tuning.flow_window,self.tuning.flow_window),maxLevel=self.tuning.pyramid_levels)
                    if back is not None:
                        valid = (status.ravel() == 1) & (back_status.ravel() == 1)
                        valid &= np.linalg.norm(back-target.points, axis=2).ravel() < self.tuning.flow_error_px
            if valid is None or valid.sum() < max(6, len(target.points)*self.tuning.surviving_fraction):
                target.state = 'predicted' if gap <= self.tuning.grace_ms else 'lost'
            else:
                old = target.points[valid]
                new = nxt[valid]
                transform, inliers = cv2.estimateAffinePartial2D(old, new, method=cv2.RANSAC,
                                                               ransacReprojThreshold=self.tuning.ransac_error_px)
                if transform is None or inliers.sum() < max(6, len(old)*self.tuning.inlier_fraction):
                    target.state = 'predicted' if gap <= self.tuning.grace_ms else 'lost'
                else:
                    keep = inliers.ravel().astype(bool)
                    mask = cv2.warpAffine(target.mask, transform, (gray.shape[1], gray.shape[0]),
                                          flags=cv2.INTER_NEAREST)
                    if np.count_nonzero(mask) < 40:
                        target.state = 'predicted' if gap <= self.tuning.grace_ms else 'lost'
                    else:
                        target.ids = [fid for fid, ok in zip(target.ids, valid) if ok]
                        target.ids = [fid for fid, ok in zip(target.ids, keep) if ok]
                        moved = np.median(new[keep] - old[keep], axis=0).ravel()
                        v = moved / dt
                        target.velocity = v if target.velocity is None else .7 * v + .3 * target.velocity
                        target.points = new[keep]
                        target.mask = mask
                        target.gray = gray
                        target.state='tracked'
                        target.last_good_ms=timestamp_ms
                        self._replenish(target, gray)
            target.last_update_ms = timestamp_ms
            observations.append(self._observation(target, cam, timestamp_ms, calibration_version))
        return observations

    def _flow(self, target, gray, dt):
        """Forward LK seeded with the constant-velocity guess; plain LK as fallback."""
        win = (self.tuning.flow_window, self.tuning.flow_window)
        guess = None
        if target.velocity is not None:
            shift = np.clip(target.velocity * min(dt, 120), -120, 120).astype(np.float32)
            if np.hypot(*shift) > 1:
                guess = target.points + shift.reshape(1, 1, 2)
        attempts = ([guess] if guess is not None else []) + [None]
        best = None
        for g in attempts:
            if g is None:
                nxt, status, _ = cv2.calcOpticalFlowPyrLK(target.gray, gray, target.points, None,
                                                          winSize=win, maxLevel=self.tuning.pyramid_levels)
            else:
                nxt, status, _ = cv2.calcOpticalFlowPyrLK(target.gray, gray, target.points, g.copy(), winSize=win,
                                                          maxLevel=self.tuning.pyramid_levels,
                                                          flags=cv2.OPTFLOW_USE_INITIAL_FLOW)
            if nxt is None:
                continue
            ok = int((status.ravel() == 1).sum())
            if best is None or ok > best[2]:
                best = (nxt, status, ok)
            if ok >= .6 * len(target.points):
                break
        return (best[0], best[1]) if best else (None, None)

    def _replenish(self, target, gray, wanted=120):
        """Top features back up inside the current mask: points die every frame on fast/blurred motion."""
        if len(target.points) >= .7 * wanted:
            return
        seed = cv2.erode(target.mask, np.ones((5, 5), np.uint8))
        for pt in target.points:
            cv2.circle(seed, tuple(map(round, pt[0])), 6, 0, -1)
        new = cv2.goodFeaturesToTrack(gray, wanted - len(target.points), .01, 5, mask=seed)
        if new is None:
            return
        target.seed_count += 1
        target.ids = list(target.ids) + [f'{target.object_id}:s{target.seed_count}:f_{i}' for i in range(len(new))]
        target.points = np.concatenate([target.points, new.astype(np.float32)])

    def _recover(self, target, gray):
        """Match immutable selected appearance; require two consistent detections.

        Object identity persists, but new feature IDs prevent downstream geometry
        from treating newly seeded points as the previous physical anchors.
        Repeated identical objects can still be ambiguous; this is not identity proof.
        """
        def reject():
            target.recovery_hits = 0
            target.recovery_box = None

        reference = target.reference_descriptors
        keys, descriptors = self.detector.detectAndCompute(gray, None)
        if reference is None or descriptors is None or len(descriptors) < 2:
            reject()
            return
        matcher = cv2.BFMatcher()
        pairs = matcher.knnMatch(reference, descriptors, k=2)
        reverse = {m.queryIdx: m.trainIdx for m in matcher.match(descriptors, reference)}
        matches = [pair[0] for pair in pairs if len(pair) == 2
                   and pair[0].distance < .65*pair[1].distance
                   and reverse.get(pair[0].trainIdx) == pair[0].queryIdx]
        if len(matches) < 10:
            reject()
            return
        src = np.float32([target.reference_keypoints[m.queryIdx].pt for m in matches])
        dst = np.float32([keys[m.trainIdx].pt for m in matches])
        H, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 3.)
        if H is None or not np.isfinite(H).all() or inliers.sum() < max(10, .55*len(matches)):
            reject()
            return
        x,y,w,h = cv2.boundingRect(target.reference_mask)
        corners = np.float32([[x,y],[x+w,y],[x+w,y+h],[x,y+h]]).reshape(-1,1,2)
        warped = cv2.perspectiveTransform(corners,H)
        area = abs(cv2.contourArea(warped))
        if not cv2.isContourConvex(warped) or not .2*w*h < area < 5*w*h:
            reject()
            return
        selected = src[inliers.ravel().astype(bool)]
        if cv2.contourArea(cv2.convexHull(selected)) < .08*w*h:
            reject()
            return
        mask = cv2.warpPerspective(target.reference_mask,H,(gray.shape[1],gray.shape[0]),
                                   flags=cv2.INTER_NEAREST)
        if np.count_nonzero(mask) < .6*area:
            reject()
            return
        box = cv2.boundingRect(mask)
        previous = target.recovery_box
        consistent = False
        if previous:
            a,b,c,d = previous
            e,f,g,j = box
            intersection = max(0,min(a+c,e+g)-max(a,e))*max(0,min(b+d,f+j)-max(b,f))
            consistent = intersection/max(1,c*d+g*j-intersection) > .4
        target.recovery_hits = target.recovery_hits+1 if consistent else 1
        target.recovery_box = box
        if target.recovery_hits < 2:
            return
        points = cv2.goodFeaturesToTrack(gray,150,.01,5,mask=mask)
        if points is None or len(points) < 6:
            reject()
            return
        target.recovery_generation += 1
        target.gray, target.mask, target.points = gray,mask,points
        target.ids = [f'{target.object_id}:r{target.recovery_generation}:f_{i}' for i in range(len(points))]
        target.state = 'tracked'
        reject()

    @staticmethod
    def _observation(target, camera, timestamp, calibration):
        visible = target.state in ('tracked','predicted')
        measured = target.state == 'tracked'
        x, y, w, h = cv2.boundingRect(target.mask) if visible else (0, 0, 0, 0)
        return dict(type='object_observation', schema_version='vision.proposal.v1',
                    timestamp_ms=timestamp, camera_id=camera, object_id=target.object_id,
                    calibration_version=calibration, bbox_xyxy=[x,y,x+w,y+h] if visible else None,
                    mask_ref=None, confidence=None, tracking_state=target.state,
                    features=[dict(track_id=fid, pixel_xy=p[0].tolist())
                              for fid,p in zip(target.ids,target.points)] if measured else [],
                    quality={'feature_count': len(target.points) if measured else 0})
