"""Deterministic synthetic fixture and optional recorded-video runner."""
import argparse
import json
import time
import cv2
import numpy as np
from tracking2d import Tracker


def fixture(dx=0):
    frame = np.zeros((240,320,3), np.uint8)
    rng = np.random.default_rng(42)
    frame[70:150,80+dx:160+dx] = rng.integers(40,255,(80,80,3),dtype=np.uint8)
    mask = np.zeros(frame.shape[:2],np.uint8)
    mask[70:150,80+dx:160+dx] = 255
    return frame,mask


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--video')
    parser.add_argument('--click',nargs=2,type=int,default=[110,100])
    parser.add_argument('--mask',help='confirmed first-frame mask PNG for recorded video')
    parser.add_argument('--preview',default='/tmp/phantom-preview.jpg')
    args = parser.parse_args()
    capture = cv2.VideoCapture(args.video) if args.video else None
    if capture:
        ok,frame = capture.read()
        if not ok:
            raise ValueError('cannot read recording')
        mask = cv2.imread(args.mask,0) if args.mask else None
    else:
        frame,mask = fixture()
    tracker = Tracker()
    base = int(time.time()*1000)
    obs = tracker.select(frame,'cam_1',*args.click,base,'fixture-v1',mask)
    start = time.perf_counter()
    count = 0
    for i in range(1,31):
        if capture:
            ok,frame = capture.read()
            if not ok:
                break
        else:
            frame,_ = fixture(i)
        obs = tracker.update(frame,'cam_1',base+i*33,'fixture-v1')[0]
        count += 1
        print(json.dumps(obs))
    elapsed = time.perf_counter()-start
    if capture:
        capture.release()
    for feature in obs['features']:
        cv2.circle(frame,tuple(map(round,feature['pixel_xy'])),2,(0,255,0),-1)
    cv2.imwrite(args.preview,frame)
    print(json.dumps({'fixture':'recorded' if args.video else 'synthetic',
                      'frames':count,'processing_fps':count/elapsed,
                      'final_state':obs['tracking_state'],'preview':args.preview}))

if __name__ == '__main__':
    main()
