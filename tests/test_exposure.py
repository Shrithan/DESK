from pathlib import Path
from types import SimpleNamespace
import numpy as np
import cv2
import pytest
from vision.exposure import WebcamExposure
from tracking2d.illumination import IlluminationNormalizer


def camera(tmp_path,ignore_lock=False):
    path=tmp_path/'uvc-util';path.write_text('fixture')
    values={'auto-exposure-mode':8,'exposure-time-abs':333,'gain':24,'auto-white-balance-temp':True,'white-balance-temp':4200};calls=[]
    def runner(args,**kwargs):
        calls.append(args)
        if args[1:]==['-d']:return SimpleNamespace(returncode=0,stdout='0 0x046d:0x0825 C270')
        if '-o' in args:
            value=values[args[-1]]
            return SimpleNamespace(returncode=0,stdout=str(value).lower())
        for i,arg in enumerate(args):
            if arg=='-s':
                k,v=args[i+1].split('=')
                if not(ignore_lock and k=='auto-exposure-mode'):values[k]=int(v) if k!='auto-white-balance-temp' else bool(int(v))
        return SimpleNamespace(returncode=0,stdout='')
    return WebcamExposure(runner,path),values,calls


def test_lock_preserves_exposure_and_gain_and_verifies_readback(tmp_path):
    c,v,calls=camera(tmp_path)
    state=c.configure('C270 HD WEBCAM',True)
    assert state['locked'] and state['exposure_ms']==33.3
    assert v['gain']==24 and v['white-balance-temp']==4200 and not v['auto-white-balance-temp']
    assert not c.configure('C270',False)['locked'] and v['auto-exposure-mode']==8
    with pytest.raises(ValueError):c.configure('iPhone',True)


def test_ignored_manual_write_is_rejected_and_restored(tmp_path):
    c,v,calls=camera(tmp_path,True)
    with pytest.raises(RuntimeError):c.configure('C270',True)
    assert v['auto-white-balance-temp'] is True


def test_brightness_compensation_ignores_hand_outlier_region():
    rng=np.random.default_rng(30)
    image=rng.integers(35,150,(240,320),dtype=np.uint8)
    norm=IlluminationNormalizer();assert np.array_equal(norm.apply(image),image)
    changed=np.clip(image.astype(float)*1.35+24,0,255).astype(np.uint8)
    changed[60:140,100:210]=230
    corrected=norm.apply(changed)
    background=np.ones(image.shape,bool);background[60:140,100:210]=False
    assert np.mean(np.abs(corrected.astype(float)[background]-image[background]))<2
    # Actual object/hand pixels remain different; compensation must not invent visibility.
    assert np.mean(np.abs(corrected.astype(float)[~background]-image[~background]))>30
