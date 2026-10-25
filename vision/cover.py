"""Hand-confirmed cover button for a stationary, registered object/region."""
from pathlib import Path
import cv2
import numpy as np

MODEL=Path(__file__).resolve().parent.parent/'outputs/models/hand_landmarker.task'


class HandDetector:
    def __init__(self):
        import mediapipe as mp
        self.mp=mp
        options=mp.tasks.vision.HandLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,num_hands=2,min_hand_detection_confidence=.6,min_hand_presence_confidence=.6,min_tracking_confidence=.6)
        self.model=mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.timestamp=0

    @staticmethod
    def available():
        import importlib.util
        return MODEL.is_file() and importlib.util.find_spec('mediapipe') is not None

    def coverage(self,frame,bbox,timestamp):
        self.timestamp=max(self.timestamp+1,int(timestamp*1000))
        h,w=frame.shape[:2];scale=min(1.,640/w)
        small=cv2.resize(frame,(int(w*scale),int(h*scale))) if scale<1 else frame
        result=self.model.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=cv2.cvtColor(small,cv2.COLOR_BGR2RGB)),self.timestamp)
        x,y,x2,y2=bbox;mask=np.zeros((max(1,y2-y),max(1,x2-x)),np.uint8)
        for landmarks in result.hand_landmarks:
            points=np.array([[round(p.x*w)-x,round(p.y*h)-y] for p in landmarks],np.int32)
            cv2.fillConvexPoly(mask,cv2.convexHull(points),1)
        return float(mask.mean())

    def close(self):self.model.close()


class CoverButton:
    def __init__(self,frame,bbox,now):
        h,w=frame.shape[:2];x,y,x2,y2=map(int,bbox)
        if min(x2-x,y2-y)<12 or x<8 or y<8 or x2>w-8 or y2>h-8:raise ValueError('Place the cover target away from the camera edges and select at least 12 pixels.')
        self.bbox=(x,y,x2,y2);self.shape=frame.shape
        self.reference=self.patch(frame);self.phase='learning';self.since=now;self.last=now;self.count=0

    def patch(self,frame):
        x,y,x2,y2=self.bbox
        return cv2.resize(frame[y:y2,x:x2],(40,40)).astype(np.float32)

    def step(self,frame,coverage,now):
        if frame.shape!=self.shape:raise RuntimeError('Camera view changed. Remap the cover button.')
        if now-self.last>.4:self.phase='missing';self.since=now
        self.last=now
        difference=float(np.mean(np.abs(self.patch(frame)-self.reference))/255.)
        clear=coverage<.08 and difference<.11
        covered=coverage>.55 and difference>.12
        fire=False
        if self.phase in ('learning','missing','pressed'):
            if clear:
                if self.since is None:self.since=now
                if now-self.since>=.35:self.phase='ready';self.since=None
            else:self.since=None
        elif self.phase=='ready':
            if covered:self.phase='covering';self.since=now
            elif coverage<.08 and difference>=.11:self.phase='missing';self.since=None
        elif self.phase=='covering':
            if covered and now-self.since>=.18:self.phase='pressed';self.since=None;self.count+=1;fire=True
            elif not covered:self.phase='ready';self.since=None
        return dict(phase=self.phase,coverage=round(coverage,3),appearance_change=round(difference,3),presses=self.count,fire=fire)


def download_model():
    import hashlib
    from urllib.request import urlopen
    url='https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
    with urlopen(url,timeout=30) as response:data=response.read(9_000_001)
    if hashlib.sha256(data).hexdigest()!='fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1':raise RuntimeError('Unexpected hand model checksum.')
    MODEL.parent.mkdir(parents=True,exist_ok=True);MODEL.write_bytes(data)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true');args=parser.parse_args()
    if args.download:download_model();print('Hand model ready:',MODEL)
    else:print('Hand model configured:',HandDetector.available())
