"""Local-only live camera adapter. Run: python -m vision.live.

The browser supplies JPEGs from an explicitly permitted camera. Frames stay in
memory. This adapter owns no camera/calibration interfaces in shared/contracts.
"""
import argparse
import json
import logging
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

import cv2
import numpy as np

from tracking2d import Tracker
from tracking2d.tracker import TrackingTuning
from vision.commands import parse_command
from vision.speech_input import CartesiaSpeechInput
from vision.keyboard import KeyboardOutput, request_accessibility_permission
from vision.usb_guard import USBPhoneGuard
from vision.voice import CartesiaVoice, VoiceError
from tilt_joystick.features import mask_features
from vision.skeleton import can_skeleton
from vision.motion import MotionSelector
from vision.orientation import rotation_delta, surface_patch, surface_rotation
from vision.objects import ObjectSegmenter, DEFAULT_WEIGHTS, overlap, foreground_containers, appearance_signature, appearance_similarity, align_detection

LOG = logging.getLogger("phantom.live")
WEB = Path(__file__).with_name("web")
MAX_BODY = 2_000_000
SYNC_DETECTION = False  # --sync-detection restores the old in-request detection
REACQUIRE_S = 5.0  # a lost object keeps its ID if re-detected near its predicted position within this time
REENTRY_S = 120.0  # keep enrolled appearance available across an exit, independent of position


def colour_similarity(a, b):
    """Hue/saturation histogram correlation in [0, 1] of two appearance signatures (blur-robust)."""
    if a is None or b is None:
        return 0.
    return max(0., float(cv2.compareHist(a[0], b[0], cv2.HISTCMP_CORREL)))


class LiveSession:
    """One camera with independent object identities and sequential frame operations."""
    def __init__(self, camera_id='front', engine=None, async_detection=False, temporal_model=None):
        self.camera_id, self.engine = camera_id, engine
        # async_detection: run the segmentation model on a background thread so per-frame optical-flow
        # tracking (~3 ms) never waits for it. Off by default (deterministic tests); the server turns it on.
        self.async_detection = async_detection and engine is not None
        self._job = None          # (thread, frame_id) of the running detection
        self._job_result = None   # (detections, frame_id, centers_at_submit)
        self._job_lock = threading.Lock()
        self.detector_error = None
        self.temporal_model = temporal_model
        self.tuning=TrackingTuning.responsive() if engine is not None else TrackingTuning()
        self.lock = threading.Lock()
        self.table_plane = None  # vision.table_plane.TablePlane for a calibrated overhead camera
        self.reset()

    def reset(self):
        self.generation = getattr(self, 'generation', 0) + 1
        self.temporal = self.temporal_model.camera(self.engine) if self.temporal_model else None
        self.tracker = Tracker(self.tuning,normalize_illumination=True)
        self.frame = None
        self.frame_id = 0
        self.observation = None
        self.origin = None
        self.previous = None
        self.last_timestamp = 0
        self.auto_enabled = True
        self.single_target = False
        self.workspace_multi = False
        self.motion_required = False
        self.overhead = False
        self.detector = MotionSelector()
        self.selection_source = None
        self.object_label = None
        self.detections = []
        self.last_detection = 0
        self.last_received = 0
        self.capture_sample_ms = None
        self.focus_score = None
        self.seed_counter = 0
        self.pending_detection = None
        self.pending_hits = 0
        self.last_semantic_support = 0
        self.objects = {}
        self.pending_objects = []
        self.reentry_candidates = {}

    def timestamp(self):
        # Receipt time in server Unix epoch milliseconds, NOT camera capture time.
        self.last_timestamp = max(int(time.time()*1000), self.last_timestamp+1)
        return self.last_timestamp

    def receive(self, jpeg, capture_sample_ms=None):
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Frame is not a readable JPEG")
        h,w = frame.shape[:2]
        if h*w > 2_000_000 or min(h,w) < 16:
            raise ValueError("Use a camera frame under 2 megapixels")
        started = time.perf_counter()
        self.capture_sample_ms = capture_sample_ms
        self.last_received = time.monotonic()
        # Sharpness is a relative image statistic, not a calibrated focus score.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.focus_score = round(float(cv2.Laplacian(gray,cv2.CV_64F).var()),1)
        # Keep expensive recognition off most frames while optical flow is healthy.
        healthy=bool(self.objects) and all(m['observation']['tracking_state']=='tracked' for m in self.objects.values())
        moving=any(m.get('velocity') is not None and np.linalg.norm(m['velocity'])>150 for m in self.objects.values())
        interval=.35 if self.workspace_multi and healthy and not moving else .12
        if self.temporal:
            interval = .05  # single worker samples latest frames; never enqueue a backlog
        due = self.engine is not None and time.monotonic()-self.last_detection > interval
        if self.async_detection:
            fresh_detection = self._collect_detection(frame)
        else:
            fresh_detection = due
            if fresh_detection:
                self.detections = self.engine.detect(frame)
                self.last_detection = time.monotonic()
        resized = self.frame is not None and frame.shape != self.frame.shape
        if resized:
            self.generation += 1
            self.temporal = self.temporal_model.camera(self.engine) if self.temporal_model else None
            self.tracker = Tracker(self.tuning,normalize_illumination=True)
            self.observation = self.origin = self.previous = None
            self.detector = MotionSelector()
            self.selection_source = None
            self.object_label = None
            self.detections = []
            self.last_detection = 0
            fresh_detection = False
        self.frame = frame
        self.frame_id += 1
        observations = self.tracker.update(frame, self.camera_id, self.timestamp(), "uncalibrated-live",
                                           recover_lost=not ((self.single_target or self.workspace_multi) and self.engine is not None),
                                           recover_ids={oid for oid,m in self.objects.items() if m.get('source')=='registered_region'},
                                           skip_ids={oid for oid,m in self.objects.items() if m.get('source')=='cover_region'})
        if resized:
            self.objects = {}
            self.pending_objects = []
        by_id = {o['object_id']: o for o in observations}
        for oid,meta in self.objects.items():
            if meta.get('source')=='cover_region':
                target=self.tracker.targets[(self.camera_id,oid)]
                obs=self.tracker._observation(target,self.camera_id,self.last_timestamp,'uncalibrated-live')
                obs['tracking_basis']='fixed_registered_region'
                by_id[oid]=obs
        if self.engine is not None and fresh_detection:
            # One-to-one association: detection order cannot assign one mask to two IDs.
            detections = []
            for d in sorted(self.detections, key=lambda d:d['score'], reverse=True):
                if not any(self._compatible(d['label'], x['label']) and overlap(d['bbox'], x['bbox'])>.65 for x in detections):
                    detections.append(d)
            if self.single_target:
                previous=next(iter(self.objects.values()),None)
                detections=foreground_containers(detections,frame.shape,previous['bbox'] if previous else None,overhead=self.overhead)
            elif self.workspace_multi:
                # Motion-gated workspace mode accepts all supported movable classes.
                # Top view must admit small round silhouettes without a side-height prior.
                minimum=.0015 if self.overhead else .006
                detections=[d for d in detections if np.count_nonzero(d['mask'])/(h*w)>=minimum]
            signatures={i:appearance_signature(frame,d['mask']) for i,d in enumerate(detections)} if self.workspace_multi else {}
            # From above a can lid flickers between disk/cup/bottle. Preserve
            # identity only for one spatially and visually supported local match;
            # do not declare every disk equivalent to every container.
            if self.overhead:
                for i,d in enumerate(detections):
                    if d.get('track_id') is not None:
                        continue
                    signature=signatures.get(i) if signatures else appearance_signature(frame,d['mask'])
                    candidates=[]
                    for oid,meta in self.objects.items():
                        labels={d['label'],meta['label']}
                        if 'disk' not in labels or not labels.issubset({'disk','can','bottle','cup'}):
                            continue
                        box=(by_id.get(oid) or {}).get('bbox_xyxy') or meta['bbox']
                        similarity=max(appearance_similarity(meta.get('appearance'),signature),
                                       appearance_similarity(meta.get('reference_appearance'),signature))
                        if overlap(d['bbox'],box)>.45 and similarity>.6:
                            candidates.append(oid)
                    if len(candidates)==1:
                        oid=candidates[0]
                        detections[i]=dict(d,semantic_label=d['label'],label=self.objects[oid]['label'],track_id=oid)
            edges = []
            reserved=set()
            reentries, waiting = self._reentries(frame,detections,by_id,signatures)
            reserved.update(waiting)
            for i,oid in reentries.items():
                d=detections[i]
                detections[i]=dict(d,track_id=oid,semantic_label=d.get('semantic_label',d['label']),label=self.objects[oid]['label'])

            def unique_match(oid,i):
                label=self.objects[oid]['label']
                same_objects=[o for o,m in self.objects.items() if self._compatible(m['label'],label)
                              and (by_id.get(o) or {}).get('tracking_state') in ('tracked','predicted','lost')]
                same_detections=[j for j,d in enumerate(detections) if self._compatible(d['label'],label)]
                return same_objects==[oid] and same_detections==[i]
            for oid, meta in self.objects.items():
                if meta.get('source')=='cover_region':continue
                obs = by_id.get(oid)
                lost_recently = obs is not None and obs['tracking_state']=='lost' and time.monotonic()-meta['support']<=REACQUIRE_S
                if not obs or (obs['tracking_state'] not in ('tracked','predicted') and not (self.single_target or self.workspace_multi or lost_recently)):
                    continue
                predicted = self._predicted_center(meta)
                for i,d in enumerate(detections):
                    if d.get('track_id') is not None and d['track_id'] != oid:
                        continue
                    if reentries.get(i)==oid:
                        edges.append((.98,oid,i));reserved.add(i)
                        continue
                    score = overlap(d['bbox'],obs['bbox_xyxy'] or meta['bbox'])
                    if self._compatible(d['label'],meta['label']) and unique_match(oid,i):
                        # A unique class is not identity proof: require similar appearance and a
                        # bounded displacement before recovering a fast-moving target.
                        old=meta['bbox'];new=d['bbox']
                        old_area=max(1,(old[2]-old[0])*(old[3]-old[1]))
                        ratio=(new[2]-new[0])*(new[3]-new[1])/old_area
                        distance=np.hypot((old[0]+old[2]-new[0]-new[2])/2,(old[1]+old[3]-new[1]-new[3])/2)
                        signature=signatures.get(i) if signatures else appearance_signature(frame,d['mask'])
                        colour=max(colour_similarity(meta.get('appearance'),signature),colour_similarity(meta.get('reference_appearance'),signature))
                        if .3<=ratio<=3.3 and distance<=max(old[2]-old[0],old[3]-old[1])*2.5 and colour>=.65:
                            score=max(score,.5)
                    if predicted is not None and self._compatible(d['label'],meta['label']):
                        # Motion-predicted gating: bridges fast moves where boxes no longer overlap.
                        gate = self._gate_score(meta, predicted, d, signatures.get(i) if signatures else appearance_signature(frame,d['mask']), w, h)
                        if gate > score:
                            score = gate
                            if obs['tracking_state']=='lost':reserved.add(i)
                    if self.single_target and len(detections)==1 and self._compatible(d['label'],meta['label']):
                        # One foreground container in the asserted single-object scene.
                        # This also bridges fast moves that break optical-flow overlap.
                        score=max(score,.25)
                    lost=obs['tracking_state']=='lost'
                    threshold=.45 if self.workspace_multi and lost else .2
                    compatible=self._compatible(d['label'],meta['label'])
                    if self.workspace_multi and lost and compatible and time.monotonic()-meta['support']<=8:
                        similarity=max(appearance_similarity(meta.get('appearance'),signatures[i]),
                                       appearance_similarity(meta.get('reference_appearance'),signatures[i]))
                        old=meta['bbox']; new=d['bbox']
                        old_area=max(1,(old[2]-old[0])*(old[3]-old[1]))
                        ratio=(new[2]-new[0])*(new[3]-new[1])/old_area
                        distance=np.hypot((old[0]+old[2]-new[0]-new[2])/2,(old[1]+old[3]-new[1]-new[3])/2)
                        radius=min(.5*np.hypot(w,h),max(old[2]-old[0],old[3]-old[1])*2+25)
                        if .3<=ratio<=3.3 and distance<=radius and similarity>=.72:
                            score=max(score,.55+.45*similarity)
                            reserved.add(i)
                        elif score>threshold and similarity<.45:
                            # A high-overlap replacement with different appearance is not the old object.
                            score=0
                    if compatible and score>threshold:
                        edges.append((score,oid,i))
                        if lost:reserved.add(i)
            used_ids, used_detections = set(), set()
            for score,oid,i in sorted(edges,reverse=True):
                if oid in used_ids or i in used_detections:
                    continue
                # Ambiguous crossings wait for optical flow / appearance recovery.
                if any(((other_oid!=oid and j==i) or (other_oid==oid and j!=i)) and abs(score-other_score)<.15
                       for other_score,other_oid,j in edges):
                    continue
                used_ids.add(oid); used_detections.add(i)
                d=detections[i]; meta=self.objects[oid]
                target=self.tracker.targets[(self.camera_id,oid)]
                if target.state in ('predicted','lost'):
                    target.points=np.empty((0,1,2),dtype=np.float32); target.ids=[]
                # Class flicker is metadata, not a change of the track's identity/name.
                meta['detector_label']=d.get('semantic_label',d['label']); meta['support']=time.monotonic()
                if self.workspace_multi:meta['appearance']=signatures[i]
                target.mask=d['mask'].copy()
                keep=[]
                for point in target.points:
                    px,py=map(round,point[0])
                    keep.append(0<=px<w and 0<=py<h and bool(target.mask[py,px]))
                target.ids=[fid for fid,ok in zip(target.ids,keep) if ok]
                target.points=target.points[np.asarray(keep,dtype=bool)]
                seed=target.mask.copy()
                for point in target.points:
                    cv2.circle(seed,tuple(map(round,point[0])),7,0,-1)
                new=cv2.goodFeaturesToTrack(gray,max(1,150-len(target.points)),.01,6,mask=seed)
                if new is not None and len(target.points)<150:
                    new=new[:150-len(target.points)]; self.seed_counter+=1
                    target.ids.extend(f'{oid}:n{self.seed_counter}:f_{i}' for i in range(len(new)))
                    target.points=np.concatenate([target.points,new])
                target.state='tracked' if len(target.points)>=6 or self.overhead and meta['label']=='disk' else 'lost'
                if target.state=='tracked':
                    target.gray=self.tracker.illumination.apply(gray) if self.tracker.illumination else gray
                    target.last_good_ms=self.last_timestamp
                    target.last_update_ms=self.last_timestamp
                    # The correction is a new measured anchor; old coast velocity
                    # must not immediately fling it away again on the next frame.
                    target.velocity=None
                by_id[oid]=self.tracker._observation(target,self.camera_id,self.last_timestamp,'uncalibrated-live')
            pending=[]
            if self.auto_enabled:
                for i,d in enumerate(detections):
                    if d.get('track_id') is not None:
                        continue  # temporal masks only correct an existing enrolled identity
                    if self.single_target and self.objects:
                        break
                    if i in used_detections or i in reserved or d['score'] < (.24 if self.single_target else .3):
                        continue
                    # Also reserve uncertain/temporarily lost tracks' last regions.
                    if any(overlap(d['bbox'],m['bbox'])>.2 and (m['observation']['tracking_state']!='lost' or time.monotonic()-m['support']<2) for m in self.objects.values()):
                        continue
                    def near(q):
                        # Same candidate across two detections: overlapping, or (for a quick first move)
                        # its centre within ~1.5 box sizes of the previous one.
                        a,c=q['d']['bbox'],d['bbox']
                        size=max(a[2]-a[0],a[3]-a[1],c[2]-c[0],c[3]-c[1])
                        dist=np.hypot((a[0]+a[2]-c[0]-c[2])/2,(a[1]+a[3]-c[1]-c[3])/2)
                        return overlap(a,c)>.35 or dist<=1.5*size
                    prior=next((q for q in self.pending_objects if self._compatible(q['d']['label'],d['label']) and near(q)),None)
                    hits=prior['hits']+1 if prior else 1
                    if prior:
                        self.pending_objects.remove(prior)
                    moved=bool(prior and prior.get('moved'))
                    if prior:
                        old=prior.get('anchor',prior['d']['bbox']); new=d['bbox']
                        distance=np.hypot((old[0]+old[2]-new[0]-new[2])/2,(old[1]+old[3]-new[1]-new[3])/2)
                        moved=moved or distance>=max(3,.008*max(w,h))
                    if hits>=2 and (not self.motion_required or moved):
                        try:
                            obs=self._add_object(d['mask'],d['label'],'semantic_object')
                            by_id[obs['object_id']]=obs
                        except ValueError:
                            self.detector.status='need_more_texture'
                    else:
                        pending.append(dict(d=d,hits=hits,moved=moved,anchor=prior.get('anchor',prior['d']['bbox']) if prior else d['bbox']))
            self.pending_objects=pending
            self.detector.status='confirming_object' if pending else 'waiting_for_object'
        elif self.engine is None and self.auto_enabled and not self.objects:
            mask=self.detector.detect(frame)
            if mask is not None:
                try:
                    obs=self._add_object(mask,'moving region','automatic_motion')
                    by_id[obs['object_id']]=obs
                except ValueError:
                    self.detector.status='need_more_texture'
        for oid,meta in self.objects.items():
            obs=by_id.get(oid)
            if obs is None:
                continue
            if self.engine is not None and meta.get('source') not in ('registered_region','cover_region') and obs['tracking_state'] in ('tracked','predicted') and time.monotonic()-meta['support']>1.8:
                target=self.tracker.targets[(self.camera_id,oid)]; target.state='lost'
                obs=self.tracker._observation(target,self.camera_id,self.last_timestamp,'uncalibrated-live')
            if obs['bbox_xyxy'] is not None:
                meta['bbox']=obs['bbox_xyxy']
                hist=meta.setdefault('history',[]);hist.append((self.frame_id,list(obs['bbox_xyxy'])))
                del hist[:-90]
                if obs['tracking_state']=='tracked':
                    x,y,x2,y2=obs['bbox_xyxy']; c=np.array([(x+x2)/2,(y+y2)/2]); now=time.monotonic()
                    last=meta.get('last_center')
                    if last is not None and now>last[1]:
                        v=(c-last[0])/(now-last[1])
                        meta['velocity']=v if meta.get('velocity') is None else .6*v+.4*meta['velocity']
                    meta['last_center']=(c,now)
            meta['observation']=obs
        self._primary()
        if self.async_detection and due and self._job is None:
            # Seed from this frame's updated masks, never the preceding frame.
            self._submit_detection(frame)
        response = self.result()
        response['processing_ms'] = round((time.perf_counter()-started)*1000, 2)
        response['selection_reset'] = resized
        return response

    def _centers(self):
        return {oid: np.array([(m['bbox'][0]+m['bbox'][2])/2, (m['bbox'][1]+m['bbox'][3])/2])
                for oid, m in self.objects.items() if m.get('bbox') is not None}

    def _submit_detection(self, frame):
        snapshot, frame_id = frame.copy(), self.frame_id
        generation, temporal = self.generation, self.temporal
        submitted_at = time.monotonic()
        seeds = [dict(track_id=oid, label=meta['label'], mask=target.mask.copy(), tracked=target.state=='tracked')
                 for oid, meta in self.objects.items()
                 if (target := self.tracker.targets.get((self.camera_id, oid))) is not None
                 and meta.get('source')!='cover_region' and np.count_nonzero(target.mask) > 48]
        boxes = None  # looked up from each object's box history at collect time
        self.last_detection = time.monotonic()

        def run():
            try:
                detections = temporal.detect(snapshot, seeds) if temporal else self.engine.detect(snapshot)
            except Exception as exc:  # noqa: BLE001
                if temporal:
                    logging.getLogger('vision.live').exception('EdgeTAM correction failed on %s; keeping asynchronous YOLOE', self.camera_id)
                    self.detector_error = f'EdgeTAM: {type(exc).__name__}: {exc}'
                    if generation == self.generation:
                        self.temporal = None
                    detections = []
                else:
                    # Preserve the existing fallback for a failed discovery model.
                    logging.getLogger('vision.live').exception('background detection failed on %s; falling back to synchronous detection', self.camera_id)
                    self.detector_error = f'{type(exc).__name__}: {exc}'
                    self.async_detection = False
                    detections = []
            with self._job_lock:
                self._job_result = (detections, frame_id, boxes, generation, submitted_at, snapshot)
                self._job = None
        with self._job_lock:
            self._job = threading.Thread(target=run, daemon=True, name=f'detect-{self.camera_id}')
            self._job.start()

    def _collect_detection(self, frame):
        """Align delayed model masks to observed current pixels, rejecting occlusions.

        Historical results without source frames retain the legacy translation
        path for callers that inject detection fixtures.
        """
        with self._job_lock:
            result, self._job_result = self._job_result, None
        if result is None:
            return False
        detections, job_frame, *_ = result
        if len(result) >= 5 and (result[3] != self.generation or time.monotonic()-result[4] > .6):
            return False
        if self.frame is not None and frame.shape != self.frame.shape:
            return False
        if len(result)>=6:
            self.detections=[aligned for d in detections
                             if (aligned:=align_detection(d,result[5],frame)) is not None]
            return True
        now = self._centers()
        # Each object's box on the frame the model saw (or its first box, if it was created later).
        then = {}
        for oid, m in self.objects.items():
            hist = m.get('history')
            if hist:
                then[oid] = next((b for f, b in reversed(hist) if f <= job_frame), hist[0][1])
        h, w = frame.shape[:2]
        shifted = []
        for d in detections:
            best, best_overlap = None, .2
            for oid, box in then.items():
                if d.get('track_id') is not None and d['track_id'] != oid:
                    continue
                o = overlap(d['bbox'], box)
                if oid in now and o > best_overlap:
                    best, best_overlap = oid, o
            if best is not None:
                old = then[best]
                dx, dy = now[best] - np.array([(old[0]+old[2])/2, (old[1]+old[3])/2])
                if abs(dx) > .5 or abs(dy) > .5:
                    M = np.float32([[1, 0, dx], [0, 1, dy]])
                    d = dict(d, mask=cv2.warpAffine(d['mask'], M, (w, h), flags=cv2.INTER_NEAREST),
                             bbox=[d['bbox'][0]+dx, d['bbox'][1]+dy, d['bbox'][2]+dx, d['bbox'][3]+dy],
                             center=[d['center'][0]+dx, d['center'][1]+dy] if d.get('center') is not None else None)
            shifted.append(d)
        self.detections = shifted
        return True

    def _predicted_center(self, meta):
        """Constant-velocity guess of where the object is now (pixels), from its last tracked centre."""
        last=meta.get('last_center')
        if last is None:
            return None
        dt=min(time.monotonic()-last[1],1.0)
        v=meta.get('velocity')
        return last[0]+(v*dt if v is not None else 0)

    def _reentries(self, frame, detections, observations, signatures):
        """Two consistent appearance matches recover an exited object's original ID.

        Position gates are useful during motion, but an object can re-enter at
        any edge. Never steal a detection already covering a visible neighbour.
        Ambiguous lookalikes wait; class names alone are insufficient evidence.
        """
        previous=self.reentry_candidates;pending={};confirmed={};reserved=set()
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        for i,d in enumerate(detections):
            if d.get('track_id') is not None:
                continue
            if any(o.get('tracking_state')=='tracked' and o.get('bbox_xyxy') and overlap(d['bbox'],o['bbox_xyxy'])>.2
                   for o in observations.values()):
                continue
            signature=signatures.get(i) if signatures else appearance_signature(frame,d['mask'])
            choices=[]
            keys=descriptors=None
            for oid,meta in self.objects.items():
                obs=observations.get(oid)
                if not obs or obs['tracking_state']!='lost' or time.monotonic()-meta['support']>REENTRY_S:
                    continue
                compatible=self._compatible(d['label'],meta['label'])
                lid=self.overhead and {d['label'],meta['label']}.issubset({'disk','can','cup','bottle'})
                if not (compatible or lid):
                    continue
                old=meta['bbox'];new=d['bbox'];ratio=(new[2]-new[0])*(new[3]-new[1])/max(1,(old[2]-old[0])*(old[3]-old[1]))
                if not .3<=ratio<=3.3:
                    continue
                similarity=max(appearance_similarity(meta.get('appearance'),signature),appearance_similarity(meta.get('reference_appearance'),signature))
                if similarity<.65:
                    continue
                target=self.tracker.targets.get((self.camera_id,oid))
                reference=target.reference_descriptors if target else None
                proven=False
                if reference is not None and len(reference)>=6:
                    if keys is None:keys,descriptors=self.tracker.detector.detectAndCompute(gray,d['mask'])
                    if descriptors is not None and len(descriptors)>=6:
                        pairs=cv2.BFMatcher().knnMatch(reference,descriptors,k=2)
                        matches=[a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance<.65*b.distance]
                        if len(matches)>=6:
                            src=np.float32([target.reference_keypoints[m.queryIdx].pt for m in matches])
                            dst=np.float32([keys[m.trainIdx].pt for m in matches])
                            transform,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=3.)
                            proven=transform is not None and inliers.sum()>=max(6,.65*len(matches)) and cv2.contourArea(cv2.convexHull(dst[inliers.ravel().astype(bool)]))>.08*np.count_nonzero(d['mask'])
                # Texture-poor sliders can use a very strong appearance match,
                # but only if no other object has a compatible enrolled class.
                isolated=not any(other!=oid and (self._compatible(m['label'],meta['label']) or self.overhead and {m['label'],meta['label']}.issubset({'disk','can','cup','bottle'})) for other,m in self.objects.items())
                if proven or compatible and isolated and similarity>=.92:
                    choices.append(oid)
            if len(choices)!=1:
                if choices:reserved.add(i)  # ambiguous remembered items must not mint a replacement ID
                continue
            oid=choices[0];center=np.asarray(d.get('center') or [(d['bbox'][0]+d['bbox'][2])/2,(d['bbox'][1]+d['bbox'][3])/2])
            prior=previous.get(oid);size=max(d['bbox'][2]-d['bbox'][0],d['bbox'][3]-d['bbox'][1])
            hits=prior['hits']+1 if prior and np.linalg.norm(center-prior['center'])<2*size else 1
            pending[oid]=dict(center=center,hits=hits)
            reserved.add(i)
            if hits>=2:confirmed[i]=oid
        # Competing detections for the same remembered ID are ambiguous.
        confirmed={i:oid for i,oid in confirmed.items() if list(confirmed.values()).count(oid)==1}
        self.reentry_candidates=pending
        return confirmed,reserved

    def _gate_score(self, meta, predicted, d, signature, w, h):
        """Score in [0, .9] for re-attaching detection d to an existing track near its predicted position."""
        old=meta['bbox']; new=d['bbox']
        ow,oh=max(1,old[2]-old[0]),max(1,old[3]-old[1])
        ratio=((new[2]-new[0])*(new[3]-new[1]))/(ow*oh)
        if not .35<=ratio<=2.8:
            return 0.
        center=np.array([(new[0]+new[2])/2,(new[1]+new[3])/2])
        speed=float(np.linalg.norm(meta.get('velocity'))) if meta.get('velocity') is not None else 0.
        dt=min(time.monotonic()-meta['last_center'][1],1.0)
        radius=min(.45*np.hypot(w,h), max(ow,oh)*1.5+.06*np.hypot(w,h)+.6*speed*dt)
        distance=float(np.linalg.norm(center-predicted))
        if distance>radius:
            return 0.
        # Appearance is a tie-breaker, not a veto: motion blur during a fast move changes both the
        # texture and the colour histogram. Only a clear mismatch on both is rejected; ambiguous
        # candidates are still held back by the crossing rule in receive().
        colour=max(colour_similarity(meta.get('appearance'),signature),
                   colour_similarity(meta.get('reference_appearance'),signature))
        full=max(appearance_similarity(meta.get('appearance'),signature),
                 appearance_similarity(meta.get('reference_appearance'),signature))
        if colour<.15 and full<.25:
            return 0.  # something else of the same class
        return .3+.4*(1-distance/radius)+.2*max(colour,full)

    def _add_object(self, mask, label, source):
        ys,xs=np.nonzero(mask)
        if not len(xs):
            raise ValueError('Empty object mask')
        middle=len(xs)//2
        obs=self.tracker.select(self.frame,self.camera_id,int(xs[middle]),int(ys[middle]),
                                self.timestamp(),'uncalibrated-live',mask,allow_textureless=self.overhead and (label=='disk' or source in ('registered_region','cover_region')))
        if source=='cover_region':
            target=self.tracker.targets[(self.camera_id,obs['object_id'])]
            target.points=np.empty((0,1,2),dtype=np.float32);target.ids=[]
            obs=self.tracker._observation(target,self.camera_id,self.last_timestamp,'uncalibrated-live')
            obs['tracking_basis']='fixed_registered_region'
        x,y,x2,y2=obs['bbox_xyxy']
        self.objects[obs['object_id']]=dict(label=label,source=source,number=len(self.objects)+1,
            origin=[(x+x2)/2,(y+y2)/2],previous=None,bbox=obs['bbox_xyxy'],
            support=time.monotonic(),observation=obs,rotation=0.,rotation_valid=True,
            appearance=appearance_signature(self.frame,mask),reference_appearance=appearance_signature(self.frame,mask))
        return obs

    def _primary(self):
        meta=next(iter(self.objects.values()),None)
        self.observation=meta['observation'] if meta else None
        self.origin=meta['origin'] if meta else None
        self.object_label=meta['label'] if meta else None
        self.selection_source=meta['source'] if meta else None

    @staticmethod
    def _compatible(a,b):
        return a==b or {a,b}.issubset({'can','bottle','cup'})

    def select(self, frame_id, bbox):
        if self.frame is None or frame_id != self.frame_id:
            raise ValueError("Preview changed; pause and select again")
        h,w = self.frame.shape[:2]
        if (not isinstance(bbox,list) or len(bbox)!=4
                or any(not isinstance(v,(int,float)) or not np.isfinite(v) for v in bbox)):
            raise ValueError("Selection must contain four finite pixel coordinates")
        x,y,x2,y2 = map(int,bbox)
        if not (0 <= x < x2 <= w and 0 <= y < y2 <= h) or min(x2-x,y2-y) < 12:
            raise ValueError("Draw a larger box inside the picture")
        mask = np.zeros((h,w),np.uint8)
        mask[y:y2,x:x2] = 255
        # Build a replacement first: invalid selection must not erase the old one.
        candidate = Tracker(self.tuning,normalize_illumination=True)
        observation = candidate.select(self.frame,self.camera_id,(x+x2)/2,(y+y2)/2,
                                        self.timestamp(),"uncalibrated-live",mask)
        self.tracker, self.observation = candidate, observation
        self.origin = [(x+x2)/2,(y+y2)/2]
        self.previous = None
        self.selection_source = 'manual'
        self.object_label = 'selected object'
        self.objects = {observation['object_id']:dict(label=self.object_label,source='manual',number=1,origin=self.origin,previous=None,bbox=observation['bbox_xyxy'],support=time.monotonic(),observation=observation)}
        self.pending_objects=[]
        return self.result()

    def clear(self):
        self.objects = {}
        self.pending_objects = []
        self.tracker = Tracker(self.tuning,normalize_illumination=True)
        self.observation = self.origin = self.previous = None
        self.selection_source = None
        self.detector = MotionSelector()
        self.object_label = None
        self.detections = []
        self.last_detection = 0
        self.pending_detection = None
        self.pending_hits = 0
        self.last_semantic_support = 0
        return self.result()

    def set_auto(self, enabled):
        if not isinstance(enabled,bool):
            raise ValueError("enabled must be true or false")
        if enabled != self.auto_enabled:
            self.auto_enabled = enabled
            return self.clear()
        return self.result()

    def result(self):
        objects=[]
        for oid,meta in self.objects.items():
            obs=meta['observation']; motion=None
            orientation=None
            skeleton=None
            if obs['tracking_state']=='tracked':
                x,y,x2,y2=obs['bbox_xyxy']; center=[(x+x2)/2,(y+y2)/2]
                if not self.overhead and meta['label'] in {'can','bottle','cup'}:
                    skeleton=can_skeleton(self.tracker.targets[(self.camera_id,oid)].mask)
                features={p['track_id']:p['pixel_xy'] for p in obs['features']}
                speed=None
                if self.overhead and meta.get('source')!='cover_region':
                    target=self.tracker.targets[(self.camera_id,oid)]
                    patch=surface_patch(self.frame,target.mask)
                    if meta.get('rotation_reference') is None and patch is not None:
                        meta['rotation_reference']=patch.copy();meta['rotation']=0.
                    angle=surface_rotation(meta.get('rotation_reference'),patch,meta.get('rotation',0.))
                    if angle is not None:
                        meta['rotation']=angle
                        orientation=dict(rotation_degrees=angle,reference='relative_overhead_surface',clockwise=True)
                elif len(features)>=6:
                    if meta['previous']:
                        before,stamp=meta['previous']
                        delta=rotation_delta(before,features) if obs['timestamp_ms']!=stamp else 0.
                        if delta is not None:meta['rotation']=meta.get('rotation',0.)+delta
                        meta['rotation_valid']=delta is not None
                    if meta.get('rotation_valid',True):orientation=dict(rotation_degrees=meta.get('rotation',0.),reference='relative_image_plane',clockwise=True)
                if meta['previous']:
                    before,stamp=meta['previous']; shared=features.keys() & before.keys()
                    dt=(obs['timestamp_ms']-stamp)/1000
                    if len(shared)>=4 and dt>0:
                        delta=np.median([np.subtract(features[k],before[k]) for k in shared],axis=0)
                        speed=float(np.linalg.norm(delta)/dt)
                meta['previous']=(features,obs['timestamp_ms'])
                motion=dict(center_px=center,displacement_px=[center[i]-meta['origin'][i] for i in range(2)],speed_px_s=speed)
            else:
                meta['previous']=None
                meta['rotation_valid']=False
            table_xy=None
            if obs['tracking_state']=='tracked' and self.table_plane is not None and self.frame is not None:
                table_xy=self.table_xy(oid)
            control_features=None
            if self.overhead and obs['tracking_state']=='tracked' and meta['label'] in {'can','bottle','cup'}:
                measured=mask_features(self.tracker.targets[(self.camera_id,oid)].mask)
                if measured is not None:
                    control_features=measured.to_dict()
            objects.append(dict(observation=obs,motion=motion,orientation=orientation,skeleton=skeleton,object_label=meta['label'],number=meta['number'],selection_source=meta['source'],table_xy_m=table_xy,control_features=control_features))
        primary=objects[0] if objects else {}
        return dict(frame_id=self.frame_id, observation=primary.get('observation'), motion=primary.get('motion'),objects=objects,
                    timestamp_domain="server_receipt_unix_ms", coordinate_units="image_pixels",
                    auto_enabled=self.auto_enabled, selection_source=self.selection_source,
                    auto_status=self.detector.status, camera_id=self.camera_id,object_label=self.object_label,
                    detector=(f'{getattr(self.engine,"model_name","YOLOE")} + EdgeTAM corrections + optical flow' if self.temporal else
                              f'{getattr(self.engine,"model_name","YOLOE")} segmentation + optical flow') if self.engine else 'motion fallback',
                    temporal_tracking=dict(enabled=self.temporal is not None,
                        status=self.temporal.status if self.temporal else 'disabled',
                        correction_ms=self.temporal.last_ms if self.temporal else None),
                    detections=ObjectSegmenter.public(self.detections) if self.engine else [],
                    focus_sharpness=self.focus_score, capture_sample_ms=self.capture_sample_ms,
                    table_plane=self.table_plane.describe() if self.table_plane is not None else None,
                    detector_error=self.detector_error, async_detection=self.async_detection)

    def table_xy(self, oid):
        """Metric X/Y (m) of a tracked object's mask centroid on the calibrated table plane, or None."""
        target=self.tracker.targets.get((self.camera_id,oid))
        if target is None or target.mask is None:return None
        m=cv2.moments(target.mask)
        if not m['m00']:return None
        try:
            xy=self.table_plane.to_table([[m['m10']/m['m00'],m['m01']/m['m00']]],self.frame.shape)[0]
        except ValueError:
            return None
        return None if not np.isfinite(xy).all() else [round(float(xy[0]),4),round(float(xy[1]),4)]


class LiveServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, engine=None, temporal_model=None):
        super().__init__(address, Handler)
        self.sessions = {name:LiveSession(name,engine,async_detection=not SYNC_DETECTION,temporal_model=temporal_model) for name in ('front','top')}
        self.session = self.sessions['front']
        from vision.stereo import WorkspaceMapper
        self.mapper = WorkspaceMapper()
        self.voice = CartesiaVoice()
        self.usb_guard = USBPhoneGuard()
        from vision.exposure import WebcamExposure
        self.exposure=WebcamExposure()
        self.speech_input = CartesiaSpeechInput()
        from vision.reply_speech import ReplySpeech
        self.reply_speech=ReplySpeech()
        self.agent_replies={};self.reply_lock=threading.Lock()
        from vision.morph import MorphPlanner
        from vision.action_runtime import ActionRuntime
        from vision.morph import catalog
        from vision.cover import HandDetector
        self.actions=ActionRuntime(self.action_snapshot)
        from vision.button_inputs import ObjectButtons
        self.object_buttons=ObjectButtons(self.action_snapshot)
        self._action_snapshots={}
        self.morph = MorphPlanner(catalog_provider=lambda:catalog(self.actions.registry.catalog(),HandDetector.available()))
        self.keyboard = KeyboardOutput(visible=self.key_object_visible)

    def action_snapshot(self,oid,include_frame=False):
        session=self.sessions['top']
        acquired=session.lock.acquire(timeout=.03)
        if not acquired:
            # A busy tracking request is not camera loss. Reuse the last coherent
            # snapshot with its ORIGINAL age/frame ID; consumers still enforce
            # the 350 ms freshness limit and never invent a new measurement.
            cached=self._action_snapshots.get(oid)
            if cached is None or time.monotonic()-cached['stamp']>.35:return None
            return dict(cached,frame=cached['frame'].copy() if include_frame else None)
        try:
            meta=session.objects.get(oid)
            if meta is None or session.frame is None:
                self._action_snapshots.pop(oid,None)
                return None
            bbox=meta['observation'].get('bbox_xyxy') or meta['bbox']
            h,w=session.frame.shape[:2]
            snapshot=dict(tracked=meta['observation']['tracking_state']=='tracked',bbox=list(bbox),
                        position=[(bbox[0]+bbox[2])/(2*w),(bbox[1]+bbox[3])/(2*h)],
                        stamp=session.last_received,frame_id=session.frame_id,
                        frame=session.frame)
            if oid not in self._action_snapshots and len(self._action_snapshots)>=16:
                self._action_snapshots.pop(next(iter(self._action_snapshots)))
            self._action_snapshots[oid]=snapshot
            return dict(snapshot,frame=snapshot['frame'].copy() if include_frame else None)
        finally:session.lock.release()

    def mapping_objects(self):
        from vision.cover import HandDetector
        session=self.sessions['top']
        buttons=getattr(self,'object_buttons',None)
        assigned=buttons.assigned_ids() if buttons else set()
        with session.lock:
            objects=[]
            if time.monotonic()-session.last_received<.4:
                for item in session.result()['objects']:
                    if item['observation']['tracking_state']!='tracked':continue
                    controllers=[] if item.get('selection_source')=='cover_region' else ['joystick','slider_x','slider_y']
                    if HandDetector.available():controllers.append('cover_button')
                    objects.append(dict(object_id=item['observation']['object_id'],label=item['object_label'],number=item['number'],controllers=controllers))
                    if item['observation']['object_id'] in assigned:objects[-1]['assigned_controller']='cover_button'
            return objects

    def key_object_visible(self, oid):
        session=self.sessions['top']
        if not session.lock.acquire(timeout=.02):
            return False
        try:
            meta=session.objects.get(oid)
            return bool(meta and meta['observation']['tracking_state']=='tracked' and time.monotonic()-session.last_received<.4)
        finally:
            session.lock.release()

    def server_close(self):
        if hasattr(self,'object_buttons'):self.object_buttons.close()
        if hasattr(self,'keyboard'):self.keyboard.close()
        if hasattr(self,'actions'):self.actions.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True

    def log_message(self, message, *args):
        # No per-frame logs, image bytes, camera names or request bodies.
        if self.path not in ('/api/frame','/api/keys/update','/api/keys/status'):
            LOG.info("%s", message % args)

    def send(self, status, body, content_type="application/json"):
        if isinstance(body,dict):
            body = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed(self):
        host = self.headers.get('Host','')
        # Loopback only, including against DNS-rebinding and cross-origin POSTs.
        if host not in {f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'}:
            return False
        origin = self.headers.get('Origin')
        return origin is None or origin == f'http://{host}'

    def do_GET(self):
        if not self.allowed():
            self.send(403,dict(error="Open this app on localhost"))
            return
        path = urlsplit(self.path).path
        assets = {'/':('fusion.html','text/html; charset=utf-8'),
                  '/single':('index.html','text/html; charset=utf-8'),
                  '/commands.js':('commands.js','text/javascript; charset=utf-8'),
                  '/mic-worklet.js':('mic-worklet.js','text/javascript; charset=utf-8'),
                  '/voice.js':('voice.js','text/javascript; charset=utf-8'),
                  '/neutral-stick.js':('neutral-stick.js','text/javascript; charset=utf-8'),
                  '/stick.js':('stick.js','text/javascript; charset=utf-8'),
                  '/motion-filter.js':('motion-filter.js','text/javascript; charset=utf-8'),
                  '/dashboard.js':('dashboard.js','text/javascript; charset=utf-8'),
                  '/object-buttons.js':('object-buttons.js','text/javascript; charset=utf-8'),
                  '/flat-input.js':('flat-input.js','text/javascript; charset=utf-8'),
                  '/prediction.js':('prediction.js','text/javascript; charset=utf-8'),
                  '/fusion.js':('fusion.js','text/javascript; charset=utf-8'),
                  '/fusion.css':('fusion.css','text/css; charset=utf-8'),
                  '/mascot.css':('mascot.css','text/css; charset=utf-8'),
                  '/mascot.js':('mascot.js','text/javascript; charset=utf-8'),
                  '/cal-bear.webp':('cal-bear.webp','image/webp'),
                  '/cal-bear-3d.png':('cal-bear-3d.png','image/png'),
                  '/app.js':('app.js','text/javascript; charset=utf-8'),
                  '/webcam.css':('webcam.css','text/css; charset=utf-8'),
                  '/style.css':('style.css','text/css; charset=utf-8')}
        if path == '/api/health':
            self.send(200,dict(status="ready",mode="dual-camera-live",stores_frames=False))
        elif path == '/api/morph/status':
            self.send(200,self.server.morph.status())
        elif path == '/api/actions/status':
            self.send(200,self.server.actions.status())
        elif path == '/api/buttons/status':
            self.send(200,self.server.object_buttons.status())
        elif path == '/api/keys/status':
            self.send(200,self.server.keyboard.status())
        elif path == '/api/camera/exposure':
            self.send(200,self.server.exposure.status())
        elif path == '/api/iphone/usb':
            self.send(200,self.server.usb_guard.status())
        elif path == '/api/voice/status':
            self.send(200,self.server.voice.status())
        elif path == '/api/world':
            with self.server.sessions['front'].lock, self.server.sessions['top'].lock:
                self.send(200,self.server.mapper.snapshot(self.server.sessions))
        elif path in assets:
            filename,kind = assets[path]
            self.send(200,(WEB/filename).read_bytes(),kind)
        else:
            self.send(404,dict(error="Not found"))

    def do_POST(self):
        if not self.allowed():
            self.close_connection = True
            self.send(403,dict(error="Cross-origin requests are disabled"))
            return
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= MAX_BODY:
                self.close_connection = True
                self.send(413,dict(error="Request too large or empty"))
                return
            self.connection.settimeout(10)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete request")
            path = urlsplit(self.path).path
            if path == '/api/camera/exposure':
                if self.headers.get_content_type()!='application/json' or length>1024:raise ValueError('Expected a small exposure command.')
                payload=json.loads(body)
                if not isinstance(payload,dict):raise ValueError('Expected an exposure object.')
                try:self.send(200,self.server.exposure.configure(payload.get('label'),payload.get('locked')))
                except (RuntimeError,OSError) as exc:self.send(503,dict(error=str(exc)))
                return
            if path == '/api/morph/plan':
                if self.headers.get_content_type()!='application/json' or length>16384:raise ValueError('Expected a small mapping request.')
                payload=json.loads(body)
                if not isinstance(payload,dict):raise ValueError('Expected a mapping object.')
                objects=self.server.mapping_objects()
                moved=payload.get('moved',[])
                if not isinstance(moved,list) or len(moved)>100:raise ValueError('Invalid movement context.')
                for item in objects:item['recently_moved']=item['object_id'] in moved
                try:
                    result=self.server.morph.plan(payload.get('transcript'),objects,payload.get('selected'),payload.get('current'))
                    reply_id=secrets.token_urlsafe(18)
                    with self.server.reply_lock:
                        if len(self.server.agent_replies)>=8:self.server.agent_replies.pop(next(iter(self.server.agent_replies)))
                        self.server.agent_replies[reply_id]=result['plan']['message']
                    self.send(200,dict(result,reply_id=reply_id))
                except VoiceError as exc:self.send(exc.status,dict(error=str(exc)))
                return
            if path=='/api/voice/reply':
                if self.headers.get_content_type()!='application/json' or length>2048:raise ValueError('Expected a small reply request.')
                payload=json.loads(body)
                if not isinstance(payload,dict) or not isinstance(payload.get('reply_id'),str):raise ValueError('Choose a current agent reply.')
                with self.server.reply_lock:text=self.server.agent_replies.get(payload['reply_id'])
                if text is None:raise ValueError('Agent reply expired. Make a new mapping request.')
                try:self.send(200,self.server.reply_speech.speak(text),'audio/wav')
                except VoiceError as exc:self.send(exc.status,dict(error=str(exc)))
                return
            if path.startswith('/api/buttons/'):
                if self.headers.get_content_type()!='application/json' or length>8192:raise ValueError('Expected a small button request.')
                payload=json.loads(body)
                if not isinstance(payload,dict):raise ValueError('Invalid button request.')
                try:
                    if path=='/api/buttons/add':result=self.server.object_buttons.add(payload.get('object_id'))
                    elif path=='/api/buttons/update':result=self.server.object_buttons.update(payload.get('object_ids'))
                    elif path=='/api/buttons/remove':result=self.server.object_buttons.remove(payload.get('object_id'))
                    else:self.send(404,dict(error='Not found'));return
                    self.send(200,result)
                except (RuntimeError,OSError) as exc:self.send(503,dict(error=str(exc)))
                return
            if path.startswith('/api/actions/'):
                if self.headers.get_content_type()!='application/json' or length>8192:raise ValueError('Expected a small action request.')
                payload=json.loads(body)
                if not isinstance(payload,dict):raise ValueError('Expected an action object.')
                try:
                    if path=='/api/actions/arm':
                        from vision.morph import validate_plan
                        mapping=payload.get('mapping')
                        validate_plan(dict(status='ready',message='Activate mapping',mapping=mapping),self.server.mapping_objects(),self.server.morph.catalog_provider())
                        self.server.keyboard.disarm('New desktop action')
                        result=self.server.actions.arm(mapping)
                    elif path=='/api/actions/update':result=self.server.actions.update(payload.get('token'),payload.get('sequence'),payload.get('enabled'))
                    elif path=='/api/actions/stop':result=self.server.actions.stop('Stopped from dashboard')
                    else:self.send(404,dict(error='Not found'));return
                    self.send(200,result)
                except PermissionError as exc:self.send(403,dict(error=str(exc)))
                except (RuntimeError,OSError) as exc:self.send(503,dict(error=str(exc)))
                return
            if path == '/api/voice/transcribe':
                if self.headers.get_content_type() not in ('audio/wav','audio/x-wav'):
                    raise ValueError('Expected microphone WAV audio')
                try:self.send(200,self.server.speech_input.transcribe(body))
                except VoiceError as exc:self.send(exc.status,dict(error=str(exc)))
                return
            if path.startswith('/api/keys/'):
                if self.headers.get_content_type()!='application/json' or length>4096:
                    raise ValueError('Expected a small JSON key command')
                payload=json.loads(body)
                if not isinstance(payload,dict):raise ValueError('Expected a JSON object')
                try:
                    if path=='/api/keys/arm':
                        self.server.actions.stop('Keyboard controller armed')
                        result=self.server.keyboard.arm(payload.get('object_id'),payload.get('mode','game'),payload.get('allowed_keys'))
                    elif path=='/api/keys/update':result=self.server.keyboard.update(payload.get('token'),payload.get('keys'),payload.get('sequence'))
                    elif path=='/api/keys/test':result=self.server.keyboard.test_taps()
                    elif path=='/api/keys/request-permission':result=dict(accessibility=request_accessibility_permission())
                    elif path=='/api/keys/stop':result=self.server.keyboard.disarm('Stopped from dashboard')
                    else:self.send(404,dict(error='Not found'));return
                    self.send(200,result)
                except PermissionError as exc:self.send(403,dict(error=str(exc)))
                except RuntimeError as exc:self.send(503,dict(error=str(exc)))
                return
            if path == '/api/voice/utterance':
                if self.headers.get_content_type() != 'application/json' or length > 512:
                    raise ValueError('Expected a short spoken reply.')
                payload = json.loads(body)
                if not isinstance(payload,dict) or not isinstance(payload.get('text'),str) or not 1 <= len(payload['text'].strip()) <= 300:
                    raise ValueError('Expected a short spoken reply.')
                try:self.send(200,self.server.reply_speech.speak(payload['text']),'audio/wav')
                except VoiceError as exc:self.send(exc.status,dict(error=str(exc)))
                return
            if path == '/api/voice/speak':
                if self.headers.get_content_type() != 'application/json' or length > 256:
                    raise ValueError('Expected a small JSON voice event')
                payload = json.loads(body)
                if not isinstance(payload,dict):
                    raise ValueError('Expected a JSON object')
                try:
                    self.send(200,self.server.voice.speak(payload.get('event')),'audio/wav')
                except VoiceError as exc:
                    self.send(exc.status,dict(error=str(exc)))
                return
            camera_id=self.headers.get('X-Camera-Id','front')
            if camera_id not in self.server.sessions:
                raise ValueError('camera must be front or top')
            session=self.server.sessions[camera_id]
            with session.lock:
                if path == '/api/frame' and self.headers.get_content_type() == 'image/jpeg':
                    sample=self.headers.get('X-Capture-Sample-Ms')
                    sample=float(sample) if sample is not None else None
                    if sample is not None and not np.isfinite(sample):
                        raise ValueError('capture sample must be finite')
                    result = session.receive(body,sample)
                elif self.headers.get_content_type() == 'application/json':
                    payload = json.loads(body)
                    if not isinstance(payload,dict):
                        raise ValueError("Expected a JSON object")
                    if path == '/api/calibration':
                        if payload.get('schema')=='phantom.rig_calibration' or 'front' not in payload.get('cameras',{}):
                            result = configure_calibration(self.server,payload,payload.get('top_camera','cam_1'),payload.get('front_camera'),payload.get('plane_height_m',0.0))
                        else:
                            result = configure_calibration(self.server,payload)
                    elif path == '/api/map/reset':
                        self.server.mapper.reset_anchor()
                        result = dict(status='reference_reset')
                    elif path == '/api/register-region':
                        stationary=payload.get('stationary',False)
                        if type(stationary) is not bool:raise ValueError('Invalid region mode.')
                        if stationary and (session.camera_id!='top' or time.monotonic()-session.last_received>.5):raise ValueError('Start the overhead webcam and show the sticker first.')
                        box=payload.get('bbox')
                        if session.frame is None or not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=1 for v in box):raise ValueError('Draw a finite region within the camera image.')
                        h,w=session.frame.shape[:2];x,y,x2,y2=[round(v*(w if i%2==0 else h)) for i,v in enumerate(box)]
                        if min(x2-x,y2-y)<12:raise ValueError('Select a larger sticker/region.')
                        if stationary and (x<8 or y<8 or x2>w-8 or y2>h-8):raise ValueError('Select a sticker at least 8 pixels inside the image edges.')
                        mask=np.zeros((h,w),np.uint8);mask[y:y2,x:x2]=1
                        added=session._add_object(mask,'sticker','cover_region' if stationary else 'registered_region')
                        result=session.result()
                        result['registered_object_id']=added['object_id']
                    elif path == '/api/select':
                        result = session.select(payload.get('frame_id'),payload.get('bbox'))
                    elif path == '/api/rotation/reset':
                        oid=payload.get('object_id')
                        if oid not in session.objects:raise ValueError('Unknown object')
                        meta=session.objects[oid]
                        meta['rotation']=0.;meta['rotation_valid']=True;meta['previous']=None;meta['rotation_reference']=None
                        result=session.result()
                    elif path == '/api/workspace-multi':
                        session.clear()
                        session.single_target=False
                        session.workspace_multi=True
                        session.motion_required=True
                        session.overhead=camera_id=='top'
                        result=session.result()
                    elif path == '/api/single-target':
                        enabled=payload.get('enabled')
                        if not isinstance(enabled,bool):
                            raise ValueError('enabled must be true or false')
                        session.clear()
                        session.single_target=enabled
                        for name in ('motion_required','overhead'):
                            value=payload.get(name,False)
                            if not isinstance(value,bool):
                                raise ValueError(f'{name} must be true or false')
                            setattr(session,name,value)
                        result=session.result()
                    elif path == '/api/auto':
                        result = session.set_auto(payload.get('enabled'))
                    elif path == '/api/clear':
                        result = session.clear()
                    elif path == '/api/reset':
                        session.reset()
                        result = session.result()
                    else:
                        self.send(404,dict(error="Not found"))
                        return
                else:
                    self.send(415,dict(error="Expected image/jpeg or application/json"))
                    return
            self.send(200,result)
        except (ValueError, TypeError, cv2.error) as exc:
            self.send(400,dict(error=str(exc)))
        except TimeoutError:
            self.close_connection = True
            self.send(408,dict(error="Request timed out"))


def configure_calibration(server,payload,top_camera='cam_1',front_camera=None,plane_height_m=0.0):
    """Load agent-1 or stereo-format calibration: metric table X/Y for 'top', optional calibrated 3D."""
    from vision.table_plane import TablePlane, to_stereo_payload
    agent1=payload.get('schema')=='phantom.rig_calibration'
    top=top_camera if agent1 else 'top'
    server.sessions['top'].table_plane=TablePlane(payload,top,plane_height_m)
    result=dict(status='table_plane_calibrated',**server.sessions['top'].table_plane.describe())
    stereo=None
    if agent1 and front_camera:
        stereo=to_stereo_payload(payload,top_camera,front_camera)
    elif not agent1 and 'front' in payload.get('cameras',{}):
        stereo=payload
    if stereo is not None:
        result['stereo']=server.mapper.configure(stereo)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--detector',choices=['yolo','motion'],default='yolo')
    parser.add_argument('--device',choices=['auto','cpu','mps'],default='auto')
    parser.add_argument('--sync-detection',action='store_true',help='run the model inside each frame request (old behaviour)')
    parser.add_argument('--temporal', choices=['flow', 'edgetam'], default='flow', help='optional background EdgeTAM corrections')
    parser.add_argument('--edgetam-source', default='outputs/research/EdgeTAM')
    parser.add_argument('--edgetam-checkpoint', default='outputs/research/EdgeTAM/checkpoints/edgetam.pt')
    parser.add_argument('--model-size',choices=['s','m','l','x'],default='x',
                        help='YOLOE size: s is several times faster than x (run `python -m vision.prepare_model --size s` once)')
    parser.add_argument('--calibration',help='calibration JSON (calibration/data/rig_calibration.json or stereo format)')
    parser.add_argument('--top-camera',default='cam_1',help='calibration id of the overhead camera (default cam_1)')
    parser.add_argument('--front-camera',help='calibration id of the side camera, enables calibrated 3D (e.g. cam_2)')
    parser.add_argument('--plane-height-m',type=float,default=0.0,help='height of the tracking plane above the calibrated table')
    args = parser.parse_args()
    if args.temporal == 'edgetam' and (args.sync_detection or args.detector != 'yolo'):
        parser.error('EdgeTAM requires asynchronous YOLOE discovery; remove --sync-detection and use --detector yolo')
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s %(message)s')
    cv2.setNumThreads(2)
    engine=None
    if args.detector=='yolo':
        try:
            engine=ObjectSegmenter(DEFAULT_WEIGHTS.with_name(f'desk-yoloe-{args.model_size}.pt'),device=args.device)
            print(f'Object segmentation ready ({engine.device}); frames stay local.',flush=True)
        except (ImportError,FileNotFoundError,RuntimeError) as exc:
            print(f'Segmentation unavailable: {exc}. Using explicitly labelled motion fallback.',flush=True)
    global SYNC_DETECTION
    SYNC_DETECTION = args.sync_detection
    if engine is None:
        print('NOTE: no segmentation model loaded: only MOVING regions are tracked (motion fallback).',flush=True)
    temporal_model = None
    if args.temporal == 'edgetam':
        if engine is None:
            raise RuntimeError('EdgeTAM requires a working YOLOE discovery model')
        from vision.temporal import EdgeTAMModel
        temporal_model = EdgeTAMModel(args.edgetam_source, args.edgetam_checkpoint, engine.device, engine.lock)
        print('EdgeTAM corrections enabled; optical flow remains the per-frame tracker.', flush=True)
    server = LiveServer(('127.0.0.1', args.port),engine,temporal_model=temporal_model)
    if args.calibration:
        configure_calibration(server,json.loads(Path(args.calibration).read_text()),args.top_camera,args.front_camera,args.plane_height_m)
    print(f'Phantom live camera: http://localhost:{server.server_port}',flush=True)
    print('Use Safari or Chrome on this Mac. Start the connected USB webcam and move an object after the scene settles.',flush=True)
    import atexit
    import signal
    atexit.register(server.keyboard.close)
    def release_on_signal(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,release_on_signal)
    if hasattr(signal,'SIGHUP'):signal.signal(signal.SIGHUP,release_on_signal)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
