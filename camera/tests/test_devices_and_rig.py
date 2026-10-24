import numpy as np
import pytest

from camera.devices import DeviceInfo, DeviceResolutionError, resolve
from camera.rig import SourceSpec, load_rig, look_rotation

DEVS = [
    DeviceInfo(0, "FaceTime HD Camera", "0x1100000aaa", enumeration="avfoundation"),
    DeviceInfo(1, "C270 HD WEBCAM", "0x1410000046d0825", enumeration="avfoundation"),
    DeviceInfo(2, "C270 HD WEBCAM", "0x1420000046d0825", enumeration="avfoundation"),
]


def test_unique_id_maps_to_exact_index():
    r = resolve(SourceSpec(kind="uvc", unique_id="0x1420000046d0825"), DEVS)
    assert r.open_arg == 2 and r.stable


def test_missing_unique_id_fails_loudly_instead_of_guessing():
    with pytest.raises(DeviceResolutionError):
        resolve(SourceSpec(kind="uvc", unique_id="0x1430000046d0825", index=1), DEVS)


def test_index_fallback_is_flagged_unstable_and_name_checked():
    r = resolve(SourceSpec(kind="uvc", index=1, name_contains="C270"), DEVS)
    assert r.open_arg == 1 and not r.stable
    with pytest.raises(DeviceResolutionError):
        resolve(SourceSpec(kind="uvc", index=0, name_contains="C270"), DEVS)


def test_look_rotation_is_a_proper_rotation_without_roll():
    R = look_rotation(np.array([0.5, -0.3, -0.45]))
    assert np.allclose(R @ R.T, np.eye(3)) and np.isclose(np.linalg.det(R), 1)
    assert abs(R[0, 2]) < 1e-12  # image x stays horizontal
    down = look_rotation(np.array([0, 0, -1.0]))
    assert np.allclose(down[0], [1, 0, 0]) and np.allclose(down[1], [0, -1, 0])


def test_rig_config_cameras_look_at_the_work_area():
    rig = load_rig()
    assert rig.camera_ids == ["cam_1", "cam_2", "cam_3"]
    for c in rig.cameras:
        # the table centre projects inside the nominal image
        p = c.R_world_to_camera @ (np.zeros(3) - c.lens_position_m)
        K = c.nominal_K
        u, v = K[0, 0] * p[0] / p[2] + K[0, 2], K[1, 1] * p[1] / p[2] + K[1, 2]
        assert p[2] > 0 and 0 < u < c.width and 0 < v < c.height, c.id
