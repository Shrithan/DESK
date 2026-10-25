"""Target relevance must not be confused with neural class confidence."""
import cv2
import numpy as np
from vision.objects import foreground_containers


def detection(label,score,box):
    mask=np.zeros((480,640),np.uint8)
    x,y,x2,y2=box;mask[y:y2,x:x2]=255
    return dict(label=label,score=score,bbox=box,mask=mask)


def test_foreground_can_beats_confident_background_bottle_and_large_box():
    foreground=detection('cup',.27,[230,128,314,348])
    background=detection('bottle',.91,[411,139,434,191])
    box=detection('box',.98,[107,76,483,342])
    chosen=foreground_containers([background,box,foreground],(480,640,3))
    assert chosen==[foreground]
    assert foreground_containers([background],(480,640,3))==[]


def test_single_container_recovery_rejects_large_scale_switch():
    original=[230,128,314,348]
    foreground=detection('bottle',.31,[260,128,344,348])
    distant=detection('bottle',.8,[400,140,440,220])
    assert foreground_containers([distant,foreground],(480,640,3),original)==[foreground]


def test_overhead_profile_accepts_small_round_can_top():
    top=detection('can',.6,[280,200,310,230])
    assert foreground_containers([top],(480,640,3))==[]
    assert foreground_containers([top],(480,640,3),overhead=True)==[top]
