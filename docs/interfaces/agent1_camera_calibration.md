# Agent 1 → agents 2, 3, 4: camera and calibration interfaces

Status: **proposal**. Agent 3 owns `shared/contracts/`. These are proposed for adoption there, and nothing in `shared/contracts/` has been edited. The repo had no `main` branch or `shared/` folder when this was written.

## Proposed contract changes (please ack in the PR)
1. **Hardware:** cameras are 3× Logitech C270 (USB, 1280×720 MJPEG @ 30 fps) instead of iPhones. No field names change; the camera ids are still `cam_1`..`cam_3`.
2. **World origin:** the contract says "a fixed calibration reference on the table". Concretely, it is the centre of the inner-corner grid of a 9×6 checkerboard lying face-up on the table at calibration time.
   - The axes are unchanged: +X right, +Y away from the viewer, +Z up, metres.
   - The board is removed afterwards and never touches tracked objects.
3. **Schemas to move into `shared/contracts/`** (all versioned, `schema_version` 1.x):
   - [`camera/schema/camera_inventory.schema.json`](../../camera/schema/camera_inventory.schema.json): `GET /api/cameras`
   - [`camera/schema/camera_health.schema.json`](../../camera/schema/camera_health.schema.json): `GET /api/health`
   - [`calibration/schema/rig_calibration.schema.json`](../../calibration/schema/rig_calibration.schema.json): `calibration/data/rig_calibration.json`
4. **Port:** camera ingest HTTP on `127.0.0.1:8100`, so it doesn't collide with agent 3's backend that serves `/ws/world`.

## Agent 2 (selection, segmentation, tracking)
- **Frames:** `camera.frame.CameraFrame`:
  - `camera_id`, `frame_index`
  - `capture_time_monotonic_ns`, `receive_time_monotonic_ns`, `capture_time_unix_ms`
  - `frame_size` (w, h), `image` (BGR uint8)
  - `calibration_version`, `source_kind`
- **Same process, full rate:**
  - `CameraHub(load_rig()).start()`
  - `hub.subscribe(cam_id).get()` returns the newest frame only, so it never lags.
  - `hub.frameset()` returns time-matched frames from all cameras.
- **Other process:** `GET /api/frameset` or `/api/cameras/{id}/snapshot.jpg`. Timestamps are in the `X-*` headers.
- **No hardware:** `python -m camera serve --video-dir camera/fixtures/synthetic_rig`. These are 640×360 synthetic clips of a ball moving in X, Y and Z, with ground truth in `ball_trajectory.json`.

## Agent 3 (multiview geometry, world state, viewer)
- **Calibration file:** `calibration/data/rig_calibration.json`. Load it with `calibration.models.RigCalibration.load`.
- **Utilities in `calibration.geometry`:**
  - `projection_matrix()` (undistorted pixels)
  - `project_points` (raw pixels)
  - `undistort_pixels`
  - `pixel_ray_world`
  - `triangulate_point` (verification-grade)
- **Camera pose for the viewport:**
  - Per camera: `camera_center_world_m`, `R_camera_to_world`, `optical_axis_world`.
  - Field of view from `K` and `image_size`.
  - The nominal design pose is also in `GET /api/cameras` → `nominal_pose` (a prior only).
- **Synthetic ground truth:** `camera/fixtures/synthetic_rig/ground_truth_calibration_640x360.json` matches the clips.
  - Simulated timestamp offsets are in each `cam_N.json` sidecar (cam_2 +7 ms, cam_3 −11 ms).
  - Use them to test time-aware triangulation.
- **Sync:** the cameras free-run, so a frameset's `spread_ms` (up to ~17 ms plus latency differences) is real and is reported, not hidden. A moving object can move a few mm between paired frames, which is worth modelling or predicting.

## Agent 4 (Fetch.ai / Convex / Cartesia)
- **Polling:** read `GET /api/health` at ≤ 1 Hz. It reports:
  - `status`: `ok` / `degraded` / `unusable`
  - `streaming_cameras`, `multiview_available`, `calibration_version`
  - per-camera `state`, fps, frame age, reconnects, last error
  - sync spread
- **Thumbnails:** `GET /api/cameras/{id}/snapshot.jpg?max_width=320`, at low rate. Never send raw video to sponsor services.
- **Spoken status:** suggested phrases are "camera two disconnected", "running on two cameras" and "calibration out of date". All are derivable from `/api/health`. `verify` returns `status: recalibrate` when a camera has moved.

## Open questions
- Will agents 2 and 3 run in the same Python process as ingest (recommended for full-rate frames), or should I add a binary frame stream such as shared memory or a WebSocket?
- Who creates `main` and the `shared/` folder?
