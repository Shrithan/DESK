import copy
import time
import cv2
import numpy as np
import pytest
from vision.stereo import StereoCalibration, WorkspaceMapper
from vision.live import LiveSession
def jpeg(frame):
    ok,data=cv2.imencode(".jpg",frame)
    assert ok
    return data.tobytes()
from vision.demo import fixture


def calibration():
    K=[[600,0,320],[0,600,240],[0,0,1]]
    return dict(units='meters',axes='x-right_y-forward_z-up',version='synthetic-only',cameras={
        'front':dict(K=K,R_world_to_camera=np.eye(3).tolist(),t_world_to_camera_m=[0,0,0],image_size=[640,480]),
        'top':dict(K=K,R_world_to_camera=np.eye(3).tolist(),t_world_to_camera_m=[-.2,0,0],image_size=[640,480])})


def project(point,camera):
    p=np.array(camera['K'])@(np.array(camera['R_world_to_camera'])@point+camera['t_world_to_camera_m'])
    return p[:2]/p[2]


def test_metric_triangulation_uses_same_projected_surface_point():
    payload=calibration();c=StereoCalibration(payload)
    point=np.array([.12,.08,1.5])
    a=project(point,payload['cameras']['front']);b=project(point,payload['cameras']['top'])
    result=c.triangulate(a,b,(480,640),(480,640))
    assert list(result['position_m'].values())==pytest.approx(point,abs=1e-8)
    # Scaling a full image scales the intrinsics, without changing metric depth.
    half=c.triangulate(a/2,b/2,(240,320),(240,320))
    assert list(half['position_m'].values())==pytest.approx(point,abs=1e-8)
    assert c.triangulate(a,b+[0,30],(480,640),(480,640)) is None
    behind=-point
    assert c.triangulate(project(behind,payload['cameras']['front']),project(behind,payload['cameras']['top']),(480,640),(480,640)) is None
    with pytest.raises(ValueError,match='aspect ratio'):
        c.triangulate(a,b,(640,480),(480,640))


def test_bad_calibration_rejected_and_no_uncalibrated_xyz():
    for changes in [dict(units='centimeters'),dict(axes='unknown')]:
        payload=calibration();payload.update(changes)
        with pytest.raises(ValueError):StereoCalibration(payload)
    payload=calibration();payload['cameras']['top']['t_world_to_camera_m']=[0,0,0]
    with pytest.raises(ValueError,match='baseline'):StereoCalibration(payload)
    sessions={name:LiveSession(name) for name in ('front','top')}
    mapper=WorkspaceMapper()
    result=mapper.snapshot(sessions)
    assert result['world'] is None
    top=sessions['top'];top.receive(jpeg(fixture()[0]));top.select(top.frame_id,[80,70,160,150])
    result=mapper.snapshot(sessions)
    assert result['views']['top']['tracked']
    assert result['views']['top']['center_uv'] is not None
    assert result['world'] is None
    top.last_received=time.monotonic()-2
    assert mapper.snapshot(sessions)['views']['top']['center_uv'] is None
