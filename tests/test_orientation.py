import numpy as np
import pytest
from vision.orientation import rotation_delta


def test_rotation_uses_shared_features_not_motion_direction():
    rng=np.random.default_rng(24);points=rng.uniform(30,160,(30,2))
    angle=np.deg2rad(25);matrix=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    before={str(i):p.tolist() for i,p in enumerate(points)}
    translated={str(i):(p+[30,-20]).tolist() for i,p in enumerate(points)}
    rotated={str(i):(matrix@p+[40,10]).tolist() for i,p in enumerate(points)}
    assert rotation_delta(before,translated)==pytest.approx(0,abs=.1)
    assert rotation_delta(before,rotated)==pytest.approx(25,abs=.1)
    assert rotation_delta(before,{'new'+k:v for k,v in rotated.items()}) is None


def test_rotation_rejects_too_few_points_and_large_scale_change():
    before={str(i):[i*10,(i%3)*15] for i in range(12)}
    assert rotation_delta(dict(list(before.items())[:4]),before) is None
    enlarged={k:[x*2,y*2] for k,(x,y) in before.items()}
    assert rotation_delta(before,enlarged) is None


def test_surface_rotation_survives_feature_id_changes_and_translation():
    import cv2
    from vision.orientation import surface_patch,surface_rotation
    frame=np.zeros((240,320,3),np.uint8);mask=np.zeros(frame.shape[:2],np.uint8)
    cv2.circle(mask,(130,120),46,255,-1);frame[mask>0]=150
    cv2.ellipse(frame,(125,105),(8,18),20,0,360,(30,30,30),-1)
    cv2.circle(frame,(146,129),6,(240,240,240),-1)
    reference=surface_patch(frame,mask)
    transform=cv2.getRotationMatrix2D((130,120),-25,1);transform[:,2]+=[30,10]
    moved=cv2.warpAffine(frame,transform,(320,240));moved_mask=cv2.warpAffine(mask,transform,(320,240))
    angle=surface_rotation(reference,surface_patch(moved,moved_mask),15)
    assert angle==pytest.approx(25,abs=2)
    assert surface_rotation(reference,surface_patch(frame,mask),angle)==pytest.approx(0,abs=2)


def test_plain_circular_surface_has_no_observable_rotation():
    import cv2
    from vision.orientation import surface_patch,surface_rotation
    frame=np.zeros((240,320,3),np.uint8);mask=np.zeros(frame.shape[:2],np.uint8)
    cv2.circle(mask,(130,120),46,255,-1);frame[mask>0]=150
    assert surface_patch(frame,mask) is None
    assert surface_rotation(None,None) is None
