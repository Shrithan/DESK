"""Robust fixed-camera brightness compensation for optical flow only."""
import cv2
import numpy as np


class IlluminationNormalizer:
    def __init__(self):self.reference=None

    def apply(self,gray):
        small=cv2.resize(gray,(64,48),interpolation=cv2.INTER_AREA).astype(np.float32)
        if self.reference is None or self.shape!=gray.shape:
            self.reference=small;self.shape=gray.shape
            return gray
        x,y=small.ravel(),self.reference.ravel()
        if np.median(np.abs(x-y))<3:return gray
        # Candidate affine intensity transforms from deterministic pixel pairs. A
        # majority of the fixed background must agree; a moving hand is an outlier.
        indexes=np.linspace(0,len(x)-1,64,dtype=int);other=(indexes+997)%len(x)
        delta=x[indexes]-x[other];valid=np.abs(delta)>25
        if not valid.any():return gray
        gain=(y[indexes][valid]-y[other][valid])/delta[valid]
        offset=y[indexes][valid]-gain*x[indexes][valid]
        usable=(gain>=.4)&(gain<=2.5)&(np.abs(offset)<=90)
        if not usable.any():return gray
        gain,offset=gain[usable],offset[usable]
        residual=np.abs(gain[:,None]*x+offset[:,None]-y)
        best=int(np.argmin(np.median(residual,axis=1)))
        good=residual[best]<10
        if good.mean()<.6:return gray
        a=np.column_stack((x[good],np.ones(int(good.sum()))))
        g,b=np.linalg.lstsq(a,y[good],rcond=None)[0]
        if not .4<=g<=2.5 or abs(b)>90:return gray
        return np.clip(gray.astype(np.float32)*g+b,0,255).astype(np.uint8)
