"""Optional local YOLO instance segmentation, never a cloud camera service."""
from pathlib import Path
import os
import threading
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEIGHTS = ROOT/'outputs/models/desk-yoloe-x.pt'
MOVABLE = {'disk','can','box','phone','pen','ball','bottle','cup','wine glass','bowl','cell phone','book','mouse','keyboard',
           'remote','scissors','sports ball','apple','orange','banana','clock',
           'vase','toothbrush','fork','knife','spoon','teddy bear'}


def overlap(a,b):
    x,y,x2,y2=a; u,v,u2,v2=b
    intersection=max(0,min(x2,u2)-max(x,u))*max(0,min(y2,v2)-max(y,v))
    return intersection/max(1,(x2-x)*(y2-y)+(u2-u)*(v2-v)-intersection)


def align_detection(detection, source, current):
    """Move a delayed model mask using observed pixels, never predicted track drift.

    Return None if the original object cannot be located confidently in the new
    frame. Reversals must not inherit a stale constant-velocity displacement.
    """
    if source.shape != current.shape:
        return None
    old = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    new = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    mask = detection['mask']
    points = cv2.goodFeaturesToTrack(old, 80, .01, 4, mask=mask)
    if points is None or len(points) < 6:
        # A stationary, textureless silhouette can still be a valid observation.
        selected = mask > 0
        delta = new.astype(float)-old.astype(float)
        if selected.any() and np.median(np.abs(delta[selected])) < 4:
            return detection
        return None
    moved, status, _ = cv2.calcOpticalFlowPyrLK(old,new,points,None,winSize=(31,31),maxLevel=4)
    if moved is None:
        return None
    back, reverse, _ = cv2.calcOpticalFlowPyrLK(new,old,moved,None,winSize=(31,31),maxLevel=4)
    if back is None:
        return None
    valid = (status.ravel()==1)&(reverse.ravel()==1)&(np.linalg.norm(back-points,axis=2).ravel()<2)
    if valid.sum() < max(6,.4*len(points)):
        return None
    transform, inliers = cv2.estimateAffinePartial2D(points[valid],moved[valid],method=cv2.RANSAC,ransacReprojThreshold=2.5)
    if transform is None or inliers.sum() < max(6,.6*valid.sum()):
        return None
    scale = np.hypot(transform[0,0],transform[1,0])
    if not .7 <= scale <= 1.4:
        return None
    h,w = current.shape[:2]
    aligned = cv2.warpAffine(mask,transform,(w,h),flags=cv2.INTER_NEAREST)
    ys,xs = np.nonzero(aligned)
    if len(xs)<48:
        return None
    contours,_=cv2.findContours(aligned.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contour=cv2.approxPolyDP(max(contours,key=cv2.contourArea),2.,True).reshape(-1,2)
    return dict(detection,mask=aligned,bbox=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)],
                center=[float(xs.mean()),float(ys.mean())],contour=contour.tolist())


def foreground_containers(detections, shape, previous_bbox=None, *, overhead=False):
    """Single-can/bottle experiment: foreground size is a selection prior, not depth.

    Keep confidence separate from intended-target relevance. A tiny distant bottle
    can have higher model confidence than the large can the user is moving.
    """
    h,w=shape[:2]
    candidates=[]
    for d in detections:
        if d['label'] not in {'can','bottle','cup'}:
            continue
        x,y,x2,y2=d['bbox']
        area=np.count_nonzero(d['mask'])/(w*h)
        if area<(.0015 if overhead else .008) or min(x2-x,y2-y)<(.025*min(w,h) if overhead else 0) or (not overhead and y2-y<.12*h):
            continue
        if previous_bbox is not None:
            a,b,c,e=previous_bbox
            ratio=(x2-x)*(y2-y)/max(1,(c-a)*(e-b))
            if not .35<=ratio<=3.:
                continue
        candidates.append(d)
    return sorted(candidates,key=lambda d:np.count_nonzero(d['mask']),reverse=True)


class ObjectSegmenter:
    def __init__(self, weights=DEFAULT_WEIGHTS, device='auto', confidence=.12, image_size=640):
        if not 0 < confidence < 1 or image_size < 32:
            raise ValueError('Invalid detector confidence or image size')
        self.model_name='YOLOE-26'+Path(weights).stem.rsplit('-',1)[-1].upper()
        self.confidence=confidence
        self.image_size=image_size
        if not Path(weights).is_file():
            raise FileNotFoundError(f'Model missing: {weights}; see README setup')
        config=ROOT/'outputs/.ultralytics'
        config.mkdir(parents=True,exist_ok=True)
        os.environ.setdefault('YOLO_CONFIG_DIR',str(config))
        os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'outputs/.matplotlib'))
        from ultralytics import YOLOE, settings
        import torch
        settings.update({'sync':False})
        torch.set_num_threads(4)
        self.model=YOLOE(str(weights))
        self.device=('mps' if torch.backends.mps.is_available() else 'cpu') if device=='auto' else device
        self.lock=threading.Lock()
        self.last_ms=None
        self.detect(np.zeros((384,640,3),np.uint8))

    def detect(self, frame):
        start=time.perf_counter()
        with self.lock:
            result=self.model.predict(frame,imgsz=self.image_size,conf=self.confidence,iou=.5,device=self.device,
                                      verbose=False,retina_masks=True,max_det=20)[0]
        self.last_ms=round((time.perf_counter()-start)*1000,1)
        detections=[]
        if result.boxes is None or result.masks is None:
            return detections
        h,w=frame.shape[:2]
        for box, polygon in zip(result.boxes,result.masks.xy):
            label=result.names[int(box.cls.item())]
            label={'soda can':'can','cardboard box':'box','cell phone':'phone','computer mouse':'mouse','remote control':'remote','top of a soda can':'can','bottle viewed from above':'bottle','cup viewed from above':'cup','flat circular disk':'disk','hockey puck':'disk','coin':'disk','flat circular lid':'disk'}.get(label,label)
            if label not in MOVABLE or len(polygon)<3:
                continue
            mask=np.zeros((h,w),np.uint8)
            points=np.round(polygon).astype(np.int32)
            points[:,0]=np.clip(points[:,0],0,w-1);points[:,1]=np.clip(points[:,1],0,h-1)
            cv2.fillPoly(mask,[points],255)
            if not 48 < np.count_nonzero(mask) < .9*w*h:
                continue
            moments=cv2.moments(mask)
            center=[moments['m10']/moments['m00'],moments['m01']/moments['m00']]
            contour=cv2.approxPolyDP(points.reshape(-1,1,2),2.,True).reshape(-1,2)
            detections.append(dict(label=label,score=float(box.conf.item()),
                bbox=box.xyxy[0].cpu().tolist(),mask=mask,center=center,
                contour=contour.tolist()))
        return detections

    @staticmethod
    def public(detections):
        return [{k:v for k,v in detection.items() if k!='mask'} for detection in detections]


def appearance_signature(frame, mask):
    """Compact same-camera appearance memory; never compared between camera views."""
    ys,xs=np.nonzero(mask)
    if not len(xs):
        return None
    x,y,x2,y2=int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    hist=cv2.calcHist([hsv],[0,1],mask,[24,16],[0,180,0,256])
    cv2.normalize(hist,hist,alpha=1,norm_type=cv2.NORM_L1)
    crop=cv2.cvtColor(frame[y:y2,x:x2],cv2.COLOR_BGR2GRAY)
    texture=cv2.resize(crop,(24,24),interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    texture-=texture.mean();texture/=max(float(np.linalg.norm(texture)),1e-6)
    return hist,texture


def appearance_similarity(a,b):
    if a is None or b is None:
        return 0.
    color=1-float(cv2.compareHist(a[0],b[0],cv2.HISTCMP_BHATTACHARYYA))
    texture=max(0.,float(np.dot(a[1],b[1])))
    return .45*color+.55*texture
