import cv2
import numpy as np
import pytest
from vision.skeleton import can_skeleton


def test_upright_and_leaning_can_centerline():
    mask=np.zeros((240,320),np.uint8);mask[45:205,110:150]=255
    upright=can_skeleton(mask)
    assert upright['base_px'][1]>upright['top_px'][1]
    assert upright['projected_lean_degrees']==pytest.approx(0,abs=.1)
    lean=np.zeros_like(mask)
    cv2.fillPoly(lean,[np.array([[150,40],[185,50],[135,210],[100,200]])],255)
    result=can_skeleton(lean)
    assert result['projected_lean_degrees']>10


def test_round_overhead_and_empty_masks_do_not_invent_base_top():
    mask=np.zeros((240,320),np.uint8)
    assert can_skeleton(mask) is None
    cv2.circle(mask,(130,120),40,255,-1)
    assert can_skeleton(mask) is None
