# Local dual-camera calibration and mapping

The top-down assumption helps interpret an image map. It does not determine
camera intrinsics, distance to the table, rotation relative to the other camera,
metric scale, or capture timing. No height is fabricated from that assumption.

Load an externally measured calibration JSON with this structure (values below
are descriptions, not usable calibration data):

```text
{
  "version": "unique calibration identifier",
  "units": "meters",
  "axes": "x-right_y-forward_z-up",
  "cameras": {
    "front": {
      "K": 3x3 intrinsic matrix in original image pixels,
      "distortion": OpenCV distortion coefficients (4,5,8,12 or 14),
      "image_size": [original_width, original_height],
      "R_world_to_camera": 3x3 proper rotation,
      "t_world_to_camera_m": [tx, ty, tz]
    },
    "top": {same fields, independently calibrated camera}
  }
}
```

World axes are meters, X right, Y forward on the table, Z up. Camera coordinates
are OpenCV camera coordinates (+x image-right, +y image-down, +z optical-forward).
`point_camera = R_world_to_camera @ point_world + t_world_to_camera_m`.
K is scaled for full-frame resizing; aspect-ratio/crop changes require recalibration.
Origin and metric scale must come from measured workspace calibration. Front/top
are roles; the geometry accepts any properly calibrated camera poses.

`GET /api/world` returns independent view measurements and a nullable `world`.
Without calibration only the overhead silhouette/centroid is plotted in normalized
image coordinates. With calibration, the mapper uses SIFT descriptors at persistent
track points, mutual/ratio matching, triangulation, cheirality, >1 degree ray angle,
and <=2 pixel reprojection checks. At least six accepted matches and two matching
rounds establish a reference. The same paired feature IDs are followed thereafter.
An anchor that disappears is not silently changed; reset the 3D reference to reseed.

Classes/appearance and geometry reduce mismatch risk but do not prove identity in
repetitive scenes. Front and overhead views can see entirely different surfaces,
in which case matching must remain unresolved. Class scores are raw model scores,
not calibrated tracking confidence; metric confidence stays null.

Both streams supply browser sampling timestamps from the same page's clock; samples
more than 60 ms apart are rejected for reconstruction. These timestamps are not
hardware exposure timestamps, and unequal device capture latency remains unknown.
The UI labels reconstruction as an estimate with unverified camera timing. This
local adapter does not publish high-confidence synchronized world state to the
shared backend.

Camera roles are assigned with `X-Camera-Id: front|top` on local analysis requests.
Each has isolated tracker, frame counter and lock; sharing a model serializes neural
inference but does not block either native camera preview. No frames are persisted.
