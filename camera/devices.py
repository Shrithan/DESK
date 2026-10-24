"""Find USB cameras and map configured camera ids to OpenCV devices without silent reordering.

Three identical C270s have identical names, so a name alone cannot tell them apart.

* macOS: AVFoundation gives every device a uniqueID that encodes its USB location, so it
  stays the same as long as each camera stays in the same port/hub slot. OpenCV (4.x and
  5.x, cap_avfoundation_mac.mm) opens index N = the N-th device of
  devicesWithMediaType(video) + devicesWithMediaType(muxed) sorted by uniqueID, so we can
  compute the index for a uniqueID exactly. Requires pyobjc-framework-AVFoundation; without
  it we fall back to `system_profiler`, which may miss virtual cameras (then indexes can
  shift and we say so).
* Linux: /dev/v4l/by-path/... symlinks are stable per USB port.
* Anything else: plain OpenCV index, flagged as unstable.

Run `python -m camera devices` to print what is attached and the ids to put in the rig config.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import platform
import subprocess
from dataclasses import asdict, dataclass

from .rig import SourceSpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceInfo:
    index: int | None  # OpenCV index (None if not openable by index, e.g. a by-path device)
    name: str
    unique_id: str | None = None
    path: str | None = None  # Linux device path / by-path symlink
    enumeration: str = "unknown"  # avfoundation | system_profiler | v4l_by_path | probe

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedDevice:
    open_arg: int | str
    stable: bool  # False when the mapping could change after replugging/reboot
    info: DeviceInfo | None
    reason: str


class DeviceResolutionError(RuntimeError):
    pass


def list_devices() -> list[DeviceInfo]:
    system = platform.system()
    if system == "Darwin":
        devs = _macos_avfoundation()
        return devs if devs is not None else _macos_system_profiler()
    if system == "Linux":
        return _linux_v4l()
    return _probe_indices()


def _macos_avfoundation() -> list[DeviceInfo] | None:
    try:
        import AVFoundation  # type: ignore[import-not-found]
    except ImportError:
        return None
    devices = list(AVFoundation.AVCaptureDevice.devicesWithMediaType_(AVFoundation.AVMediaTypeVideo))
    devices += list(AVFoundation.AVCaptureDevice.devicesWithMediaType_(AVFoundation.AVMediaTypeMuxed))
    devices.sort(key=lambda d: str(d.uniqueID()))  # same order OpenCV uses
    return [
        DeviceInfo(index=i, name=str(d.localizedName()), unique_id=str(d.uniqueID()), enumeration="avfoundation")
        for i, d in enumerate(devices)
    ]


def _macos_system_profiler() -> list[DeviceInfo]:
    try:
        out = subprocess.run(["system_profiler", "SPCameraDataType", "-json"], capture_output=True, text=True, timeout=20)
        cams = json.loads(out.stdout).get("SPCameraDataType", [])
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        log.warning("system_profiler failed: %s", e)
        return []
    entries = sorted(((c.get("spcamera_unique-id", ""), c.get("_name", "?")) for c in cams), key=lambda t: t[0])
    return [DeviceInfo(index=i, name=n, unique_id=u or None, enumeration="system_profiler") for i, (u, n) in enumerate(entries)]


def _linux_v4l() -> list[DeviceInfo]:
    devs = []
    for link in sorted(glob.glob("/dev/v4l/by-path/*-video-index0")):
        target = os.path.realpath(link)
        name = "?"
        sysname = os.path.join("/sys/class/video4linux", os.path.basename(target), "name")
        if os.path.exists(sysname):
            with open(sysname) as f:
                name = f.read().strip()
        index = int(target.replace("/dev/video", "")) if target.startswith("/dev/video") else None
        devs.append(DeviceInfo(index=index, name=name, unique_id=None, path=link, enumeration="v4l_by_path"))
    return devs


def _probe_indices(max_index: int = 6) -> list[DeviceInfo]:
    import cv2

    devs = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            devs.append(DeviceInfo(index=i, name=f"camera {i}", enumeration="probe"))
        cap.release()
    return devs


def resolve(spec: SourceSpec, devices: list[DeviceInfo] | None = None) -> ResolvedDevice:
    """Turn a configured uvc source into something cv2.VideoCapture can open.

    Raises DeviceResolutionError instead of guessing when an explicit identifier is missing,
    so a camera can never silently swap ids with another one.
    """
    if spec.linux_by_path:
        if not os.path.exists(spec.linux_by_path):
            raise DeviceResolutionError(f"{spec.linux_by_path} not present (camera unplugged or moved to another port?)")
        return ResolvedDevice(spec.linux_by_path, True, None, "linux by-path")

    devices = list_devices() if devices is None else devices
    if spec.unique_id:
        matches = [d for d in devices if d.unique_id == spec.unique_id]
        if len(matches) != 1:
            raise DeviceResolutionError(
                f"unique_id {spec.unique_id!r} matched {len(matches)} devices "
                f"(attached: {[d.unique_id for d in devices]}). Same USB port? Run `python -m camera devices`."
            )
        d = matches[0]
        exact = d.enumeration == "avfoundation"
        reason = "uniqueID -> OpenCV index" + ("" if exact else " (system_profiler: index assumes no virtual cameras)")
        return ResolvedDevice(d.index, exact, d, reason)

    if spec.index is None:
        raise DeviceResolutionError("uvc source needs unique_id, linux_by_path or index")
    d = next((x for x in devices if x.index == spec.index), None)
    if spec.name_contains and d is not None and spec.name_contains.lower() not in d.name.lower():
        raise DeviceResolutionError(f"index {spec.index} is {d.name!r}, expected a name containing {spec.name_contains!r}")
    return ResolvedDevice(spec.index, False, d, "plain OpenCV index: may reorder after replugging; set unique_id")
