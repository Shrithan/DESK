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

## iPhone USB-presence requirement

The dashboard now requires exactly one iPhone in the Mac's USB inventory before opening an iPhone-labeled camera. It checks every two seconds while live and stops the session if USB presence is lost or verification fails. `/api/iphone/usb` returns only presence/count/status; no serial numbers or persistent USB identifiers are exposed.

Connect a data-capable cable, unlock the phone, tap Trust This Computer if prompted, then lock/mount it and reconnect cameras. Apple supports wired Continuity Camera: https://support.apple.com/102546. Keep the OS requirements for Continuity enabled.

This is a **USB-presence guard**, not proof of USB video transport or a native transport override. Safari's camera API does not expose a wired/wireless selection, and browser camera IDs cannot be matched to USB device IDs. macOS still controls the stream route. Use the same single connected iPhone selected in the camera picker. A dedicated USB camera driver would be needed for independently selectable USB-only video capture.

Wireless Continuity is allowed by default again. The optional **Require a USB cable for iPhone** checkbox enables the prior USB presence guard; when unchecked, camera startup and the running connection are not blocked by USB inventory. macOS selects the actual video transport. Two-camera preview is the default, with both full images side by side near the top of the dashboard.

Camo USB side-camera integration: Camo Studio's Camera Extension was installed and enabled in macOS, and its virtual device is now preferred for the side camera when available. Logitech remains the overhead source. Keep Camo Studio and the phone's Camo app running. Camo Studio reports the physical USB connection; the dashboard reads Camo's virtual video stream. Configure phone exposure/focus in Camo Studio; native UVC controls remain C270-only.

Recording review (IMG screen capture 16:07): automatic overhead disk assignment could consume an overhead track before dual-view association. Auto disk input creation now runs only without a side stream; explicit voice/manual mappings still work in dual mode. Predicted/lost boxes are no longer displayed as measured object boxes. Preview height increased while retaining the complete source image. Camo's output menu offers a free Vertical 720p 9:16 profile; portrait output still requires suitable physical phone orientation/framing and must not be confused with adding optical coverage by stretching or cropping.

Camo framing: capture constraints now omit width, height and aspect ratio for the Camo virtual camera, preserving its native output profile instead of requesting landscape. Other webcams keep their existing constraints. A regression test verifies Camo never receives a forced landscape aspect ratio.

Joystick controls automatically use overhead-only capture. Selecting “Use my can as joystick,” “Add joystick,” a 2D input, or a voice-mapped joystick stops and releases the side camera, cancels its frame/exposure timers and frame callbacks, and resets its server session. The overhead stream and its object IDs/mappings stay intact; side results already in flight are ignored. Overhead-only preference persists for the browser session. Uncheck the mode and reconnect cameras when returning to dual-camera spatial mapping. This removes side-camera inference load; actual latency depends on capture and tracking throughput.
