"""Relative image-plane rotation from persistent feature correspondences."""
import cv2
import numpy as np


def rotation_delta(before, after):
    shared=sorted(before.keys() & after.keys())
    if len(shared)<6:return None
    a=np.float32([before[k] for k in shared]);b=np.float32([after[k] for k in shared])
    matrix,inliers=cv2.estimateAffinePartial2D(a,b,method=cv2.RANSAC,ransacReprojThreshold=2.)
    if matrix is None or inliers is None or int(inliers.sum())<max(6,.65*len(shared)):return None
    scale=float(np.hypot(matrix[0,0],matrix[1,0]))
    angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0])))
    if not .8<=scale<=1.25 or abs(angle)>60:return None
    return angle


def surface_patch(frame,mask):
    """Translation/scale normalized interior texture; circular outline is excluded."""
    ys,xs=np.nonzero(mask)
    if len(xs)<80:return None
    crop=cv2.cvtColor(frame[int(ys.min()):int(ys.max()+1),int(xs.min()):int(xs.max()+1)],cv2.COLOR_BGR2GRAY)
    if min(crop.shape)<18:return None
    patch=cv2.resize(crop,(96,96),interpolation=cv2.INTER_AREA).astype(np.float32)
    yy,xx=np.mgrid[:96,:96];radius=np.hypot(xx-47.5,yy-47.5)
    inside=radius<38
    # Remove radial averages: a circular silhouette alone cannot reveal rotation.
    bins=np.minimum(radius.astype(int),67)
    means=np.bincount(bins.ravel(),weights=patch.ravel())/np.maximum(1,np.bincount(bins.ravel()))
    residual=patch-means[bins]
    if float(np.std(residual[inside]))<4:return None
    patch=(patch-patch[inside].mean())/max(5,float(patch[inside].std()))
    patch[~inside]=0
    return cv2.GaussianBlur(patch,(3,3),0).astype(np.float32)


def surface_rotation(reference,current,hint=0.):
    if reference is None or current is None:return None
    angle=np.deg2rad(hint);c,s=float(np.cos(angle)),float(np.sin(angle))
    center=np.array([47.5,47.5],np.float32)
    rotation=np.array([[c,-s],[s,c]],np.float32)
    warp=np.column_stack((rotation,center-rotation@center)).astype(np.float32)
    try:
        score,warp=cv2.findTransformECC(reference,current,warp,cv2.MOTION_EUCLIDEAN,
            (cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,45,1e-4),None,3)
    except cv2.error:return None
    if score<.85:return None
    theta=float(np.degrees(np.arctan2(warp[1,0],warp[0,0])))
    # Unwrap relative to the last verified angle rather than jumping at +/-180.
    return hint+(theta-hint+180)%360-180
