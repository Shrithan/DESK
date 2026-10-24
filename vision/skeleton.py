"""Estimated can centerline from a segmented side silhouette, in image pixels."""
import numpy as np


def can_skeleton(mask):
    ys,xs=np.nonzero(mask)
    if len(xs)<80:return None
    points=np.column_stack((xs,ys)).astype(float);center=np.mean(points,axis=0)
    values,vectors=np.linalg.eigh(np.cov((points-center).T))
    if values[-1]/max(values[0],1)<1.7:return None  # Round overhead masks have no base/top axis.
    axis=vectors[:,-1]
    if axis[1]<0:axis=-axis
    projection=(points-center)@axis
    low,high=np.quantile(projection,[.07,.93])
    top=np.median(points[projection<=low],axis=0)
    base=np.median(points[projection>=high],axis=0)
    if base[1]-top[1]<8:return None
    lean=float(np.degrees(np.arctan2(top[0]-base[0],base[1]-top[1])))
    return dict(base_px=base.tolist(),top_px=top.tolist(),center_px=center.tolist(),
                projected_lean_degrees=lean,kind='estimated_silhouette_centerline',units='image_pixels')
