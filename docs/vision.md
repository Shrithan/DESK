# Vision integration proposal v1

## Scope and implementation

`Tracker.select(BGR_frame, camera_id, pixel_x, pixel_y, timestamp_ms,
calibration_version, mask=None)` returns a serializable observation and new object ID.
The default selector uses connected fixed-range color flood-fill. It rejects overly
large, small, or featureless regions. A caller can supply a prompted segmentation
mask (uint8, image-sized, nonzero inside). Preview and human confirmation are
required before accepting fallback masks. It does not segment all arbitrary objects.
SAM is not installed or benchmarked; no model license, size, memory, or MPS claim
is made. No weights are downloaded. OpenCV CPU processing is the runnable fallback.

`Tracker.update(frame, camera_id, timestamp_ms, calibration_version)` emits all
objects selected for that camera. Forward/backward optical flow and affine RANSAC
retain local feature IDs; mask propagation assumes approximate planar/rigid image
motion. Rotation, deformation, large occlusion, lighting shifts and repeated texture
can break this assumption. There is no probabilistic confidence score.
Lost targets emit no features or box and require explicit reselection. This avoids
automatic reacquisition onto a nearby target, but cannot guarantee no identity swaps.
No replenishment means long tracks eventually exhaust features.
`deselect(camera_id, object_id)` removes the target. Multiple selections are supported.

`vision.association.associate` matches SIFT descriptors from the selected source
mask against the other image, applies ratio and mutual checks, and rejects matches
using the supplied fundamental matrix (Sampson error <= 2.25 pixel squared).
Results remain `needs_confirmation` or `unresolved`. A descriptor match plus an
epipolar check is insufficient to prove object identity for repeated textures.
Candidate indices are not persistent cross-camera feature IDs. Agent 3 must not
interpret independent per-camera track IDs as shared 3D anchor IDs. A later
confirmation/anchor-binding layer must bind these candidates to temporal tracks;
it is not implemented. No independent bbox center is exposed as a triangulation point.

## Proposed adapter contract (not a shared contract change)

Observations use `schema_version=vision.proposal.v1`, Unix epoch `timestamp_ms`,
`camera_id`, `object_id`, `calibration_version`, nullable `bbox_xyxy`, `mask_ref=null`,
`confidence=null`, `tracking_state`, `features[{track_id,pixel_xy}]`, and heuristic
`quality.feature_count`. Pixels are in the supplied image coordinate system. Masks
are available locally via `tracker.targets[(camera_id,object_id)].mask`; never put
raw images in Convex. Camera adapters must supply aligned/undistorted frames and
matching calibration. Keep resolution and calibration fixed during a selection.
This library does not synchronize clocks: association timestamp skew checks are
valid only after camera clock offsets are estimated/bounded by Agent 1.
The demo uses a local synthetic timestamp sequence, not camera clock evidence.

Frontend integration should wrap selection/deselection with backend endpoints,
show low-rate mask/feature previews, and ask the user to correct ambiguous cross-view
matches. This branch provides Python callables and a preview JPEG; HTTP routes,
preview scheduling and selection UI belong to Agents 3/4 and are not implemented.
No shared/contracts files existed on inspection; Agent 3 must approve/finalize schemas.

## Smallest path to physical XYZ

1. Agent 1 delivers two calibrated undistorted streams, projection matrices,
   calibration version, image dimensions and bounded timestamp skew. A third is optional.
2. Agent 2 confirms masks/cross-view candidates on actual recordings and implements
   persistent anchor binding after selection confirmation.
3. Agent 3 triangulates matching surface points with cheirality/reprojection rejection,
   retains a stable reference anchor, and publishes tracked/lost metric world state.
4. Agent 4 maps Z-up coordinates to the renderer, wires selection and displays uncertainty.

Do not average changing visible surface points and call it a stable object center.
Metric scale must come from workspace calibration. No sponsor code runs in vision.
