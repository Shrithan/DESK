"""Class-free motion proposals for a fixed camera; not semantic segmentation."""
import cv2
import numpy as np


class MotionSelector:
    WARMUP_FRAMES = 15
    CONFIRM_FRAMES = 3

    def __init__(self):
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=24, detectShadows=False)
        self.frames = 0
        self.candidate_box = None
        self.hits = 0
        self.previous_gray = None
        self.status = 'learning_background'

    def detect(self, frame):
        h,w = frame.shape[:2]
        small = cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),
                           (320,max(16,round(h*320/w))))
        shifted = False
        if self.previous_gray is not None and small.shape == self.previous_gray.shape:
            shift,response = cv2.phaseCorrelate(np.float32(self.previous_gray),np.float32(small))
            shifted = response > .25 and np.hypot(*shift) > 3
        self.previous_gray = small
        self.frames += 1
        mask = self.background.apply(frame, learningRate=.15 if self.frames<=self.WARMUP_FRAMES else .005)
        if shifted:
            self.candidate_box = None
            self.hits = 0
            self.status = 'hold_camera_still'
            return None
        if self.frames <= self.WARMUP_FRAMES:
            self.status = 'learning_background'
            return None
        fraction = np.count_nonzero(mask)/mask.size
        if fraction > .45:
            self.candidate_box = None
            self.hits = 0
            self.status = 'hold_camera_still'
            return None
        mask = cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        viable = [i for i in range(1,count) if max(100,.002*w*h) <= stats[i,4] <= .4*w*h
                  and min(stats[i,2:4]) >= 12
                  and stats[i,2]*stats[i,3] < .45*w*h
                  and stats[i,4]/max(1,stats[i,2]*stats[i,3]) > .2]
        if not viable:
            self.candidate_box = None
            self.hits = 0
            self.status = 'waiting_for_motion'
            return None
        candidate = max(viable,key=lambda i:stats[i,4])
        x,y,bw,bh,_ = map(int,stats[candidate])
        box = (x,y,bw,bh)
        consistent = False
        if self.candidate_box:
            a,b,c,d = self.candidate_box
            intersection = max(0,min(a+c,x+bw)-max(a,x))*max(0,min(b+d,y+bh)-max(b,y))
            consistent = intersection/max(1,c*d+bw*bh-intersection) > .25
        self.hits = self.hits+1 if consistent else 1
        self.candidate_box = box
        self.status = 'confirming_motion'
        if self.hits < self.CONFIRM_FRAMES:
            return None
        region = np.uint8(labels==candidate)*255
        # Use a connected foreground mask, rather than a box containing background.
        return region
