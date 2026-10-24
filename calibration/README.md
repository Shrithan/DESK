# calibration/: intrinsics, extrinsics and geometry utilities (Agent 1)

## Conventions
These are also written into every calibration file.

| item | convention |
|---|---|
| World frame | Right-handed, **metres**, +X right, +Y away from the viewer, +Z up. Origin is the centre of the checkerboard's inner-corner grid lying face-up on the table during extrinsics. |
| Camera frame | OpenCV: +X image right, +Y image down, +Z forward (optical axis). |
| Extrinsics | `x_cam = R_world_to_camera @ x_world + t_world_to_camera_m`; `camera_center_world_m = -Rᵀ t` |
| Pixels | OpenCV: (0, 0) is the centre of the top-left pixel |
| Distortion | OpenCV radial-tangential `[k1, k2, p1, p2, k3]` (k3 fixed to 0 for the C270) |
| Metric scale | The **measured** square size of the printed checkerboard |
| Versioning | `calibration_id` = UTC time + content hash; every `CameraFrame.calibration_version` carries it |

Files:
- `calibration/data/intrinsics_<cam>.json`, one per camera ([`phantom.camera_intrinsics`](models.py))
- `calibration/data/rig_calibration.json` ([schema](schema/rig_calibration.schema.json))
- `calibration/data/history/<calibration_id>.json`, a copy of every past calibration

Loading validates the shapes, that rotations are proper, that the principal point is inside the image, that the stored camera centre is consistent, and the major schema version.

## Procedure (about 15 minutes)
1. **Print the board:**
   - Run `python -m calibration board --out board.png` and print it at **100 % / actual size**.
   - Tape it to stiff, flat card.
   - Measure 9 squares with a ruler and divide by 9. Printers rescale pages, and every distance scales with this number.
2. **Lock the cameras:**
   - The C270 is fixed-focus, so focus can't drift.
   - Keep 1280×720 MJPEG, and use no digital zoom or "RightLight" auto-adjustment.
   - Keep the lighting steady.
3. **Start ingest:** run `python -m camera serve` (diagnostics on http://127.0.0.1:8100).
4. **Intrinsics, once per camera:**
   - Run `python -m calibration intrinsics --camera cam_1 --square-mm 20.0`.
   - Hold the board 0.3–0.8 m away, tilted, and move it through every part of the image, especially the corners.
   - Views are auto-captured when they're sharp and new. You want RMS < 0.5 px and image coverage > 60 %.
   - Repeat for `cam_2` and `cam_3`.
5. **Extrinsics:**
   - Lay the board face-up in the middle of the table, readable from where you stand: the "BACK edge" label is away from you and corner 0 is at the back-left.
   - Check that the diagnostics page shows "fully visible ✓" for all three cameras.
   - Run `python -m calibration extrinsics --square-mm 20.0`, then restart `camera serve`.
6. **Verify:**
   - Put the board on a block of known height, e.g. 50 mm.
   - Run `python -m calibration verify --square-mm 20.0 --board-height-mm 50`.
   - This reports per-camera reprojection error and the triangulated height error. Re-run it any time a camera may have been bumped; `status: recalibrate` means do step 5 again.
7. **Remove the board.** It's an environment-only calibration aid and must never be attached to a tracked object.

## Using it (agent 3)
```python
from calibration.models import RigCalibration
from calibration.geometry import project_points, undistort_pixels, pixel_ray_world, triangulate_point

cal = RigCalibration.load("calibration/data/rig_calibration.json")
cam = cal.cameras["cam_2"]
cam.K, cam.dist, cam.extrinsics.R_world_to_camera, cam.extrinsics.t_world_to_camera_m
cam.projection_matrix()                    # 3x4, world (m) -> UNDISTORTED pixels
project_points(X_world, cam)               # world -> raw (distorted) pixels, as in CameraFrame.image
undistort_pixels(px, cam, normalized=True) # raw pixels -> normalised camera coordinates
pixel_ray_world(px, cam)                   # (origin, direction) of the viewing ray
triangulate_point({"cam_1": px1, "cam_3": px3}, cal.cameras)   # verification-grade DLT + refinement
```
- `cam.intrinsics.scaled(w, h)` gives intrinsics for downscaled images.
- `/api/frameset?max_width=` downscales frames, so scale the intrinsics to match.
- Camera pose metadata for the 3D viewer (agent 3/4) is `camera_center_world_m`, `R_camera_to_world` and `optical_axis_world` in the JSON. The C270's field of view follows from `K` and the image size.

## Accuracy
| check | result | conditions |
|---|---|---|
| intrinsics recovered from rendered views | fx within 0.5 %, principal point within 3 px, RMS < 0.3 px (typically 0.06 px) | synthetic, no noise |
| extrinsics vs ground truth | angled cameras ≈ 0.1 mm / 0.01°; **overhead ≈ 1 mm / 0.1°** | synthetic, one board placement |
| board corners triangulated from 3 views | RMSE < 1 mm | synthetic |
| raised-board height check | error < 1 mm at 50 mm | synthetic |
| 1° bump of one camera | flagged `recalibrate`, more than 10 px reprojection error | synthetic |
| **real C270 rig** | **not measured yet** | needs the printed frame + cameras |

**Weakest part:** the overhead camera sees the small flat board almost head-on through a narrow lens, where a slight tilt and a slight shift look alike. Real-world error will be higher than the synthetic numbers because of sensor noise, MJPEG artefacts, paper that isn't flat, and a square size that's only measured approximately. The `verify` step exists to measure this on the real rig. The next improvement is multi-placement refinement (several board poses solved jointly).

## Synthetic fixtures
Run `python -m calibration synth-fixtures`. It writes `camera/fixtures/synthetic_rig/`:
- 640×360 clips of a ball moving in X, Y and Z, seen by all three cameras;
- per-clip simulated timestamp offsets (cam_2 +7 ms, cam_3 −11 ms);
- ground-truth calibrations at 1280×720 and 640×360;
- board views for extrinsics;
- ground-truth intrinsics;
- the ball trajectory.

Everything there is labelled SYNTHETIC. It validates the pipeline, not real-world accuracy.
