# Phantom control studio — phase handoff

## Current result

One local dashboard presents all configured sliders, XY joysticks, relative yaw
and paired spatial objects. Cards retain their identity when visibility is lost,
show active/offline state, and offer per-control assignment, centering, slider
endpoints and removal. Filters show sliders, joysticks or spatial objects alone.
Every card includes a generic 3D proxy; the spatial viewer also shows object
proxies, axes and trails. These are not reconstructed meshes.

Camera feeds and diagnostics collapse to keep controls prominent. Preview layout
provides explicitly simulated controls without opening cameras or loading a model.
The previous camera-stop request is preserved: development/QA used a static
server only; the model server on port 8765 and camera streams remain stopped.

## Run when ready

From /Users/shrithan/DESK:

```sh
.venv/bin/python -m vision.live
```

Open http://localhost:8765/. Start both cameras explicitly. Assign portrait iPhone
to SIDE and Logitech to OVERHEAD. Move new objects briefly in both views. For
similar objects, move individually or use explicit cross-view pairing.
Flat disks are overhead-only XY inputs automatically; any overhead object can
be assigned as a slider or joystick. Physical orientation/scale calibration is
still required before exporting accurate world-space coordinates.

## Vision decision and smoothing

Retained the existing local YOLOE-26X detector (Extra Large) rather than claiming
an unmeasured universal best model. It has the desk/overhead/disk prompt profile,
MPS acceleration, sparse pyramidal optical flow between recognition updates,
short-term same-camera appearance memory and ambiguous-match rejection.

Reviewed alternative approaches:

- Ultralytics BoT-SORT/ByteTrack: useful motion/appearance association components,
  but replacing current camera-local IDs would require new occlusion/cross-view
  validation; detector tracking alone does not establish cross-camera identity.
- SAM 2: promptable streaming video masks are relevant, but automatic acquisition,
  stable control IDs, cross-view matching and rotation remain separate tasks. No
  SAM 2 performance comparison was run on this Mac, so no superiority is claimed.
- Adaptive One Euro filtering: added to spatial/control measurements and yaw to
  reduce low-speed jitter while opening bandwidth during deliberate movement.

Sources: https://docs.ultralytics.com/modes/track/,
https://ai.meta.com/research/sam2/,
https://gery.casiez.net/1euro/.

The deterministic filter test reduced RMS stationary noise from 0.354 to 0.073
(about 79%) and reached 19.74 of a 20-unit step by 64 ms. This is a synthetic
signal test, not a measured live accuracy or latency improvement. Tuning will
still depend on the object, lighting and camera noise.

Prediction remains optional, marked, capped to 80 ms look-ahead, and expires
when real data gets stale. It does not create camera frames. Relative yaw is
image-plane rotation from persistent feature correspondences; plain round disks
need a visible mark/texture. Lost orientation requires re-zero.

## Validation

```sh
.venv/bin/python -m pytest -q
node tests/test_motion_filter.cjs
node tests/test_flat_input.cjs
node tests/test_fusion.cjs
node tests/test_prediction.cjs
node tests/test_smoothing.cjs
node tests/test_video.cjs
```

30 Python tests pass. JavaScript suites cover adaptive filtering, control
normalization, slider travel, yaw availability, pairing ambiguity, identity
retention, independent source cadence and bounded prediction. Browser QA used
simulated cards: counters, type filters, slider-to-joystick conversion, yaw/proxy
rendering, responsive layout, and cameras-off state. New filtering was not tested
on live cameras in this final pass because cameras were explicitly left stopped.

## Main implementation files

- vision/live.py — camera-local sessions, tracking API and control observations
- vision/objects.py — YOLOE segmentation and appearance memory
- tracking2d/tracker.py — sparse optical flow and quality checks
- vision/orientation.py — relative image-plane rotation
- vision/web/fusion.js — source processing, pairing and spatial viewer
- vision/web/motion-filter.js — adaptive filters and generic object proxy drawing
- vision/web/prediction.js — bounded display prediction
- vision/web/flat-input.js — overhead controls and yaw
- vision/web/dashboard.js — keyed control-card registry, filters and layout preview

## Remaining next-phase work

Calibrate camera intrinsics/extrinsics and the tabletop plane; define the desired
control output protocol (app events, OSC, MIDI, HID, or another consumer); record
representative evaluation clips; validate identity across lookalike objects and
occlusion. Current normalized coordinates are suitable for a control prototype,
not a calibrated full-scene reconstruction or guaranteed object re-identification.

## Final local handoff — 2026-10-24

Publication branch: `codex/phantom-spatial-controls`.

The live implementation includes overhead Logitech + portrait iPhone inputs, multi-object tracking and association, the spatial/control dashboard, short-travel can joystick with corrected virtual WASD axes, estimated silhouette tilt, bounded dropout continuity, sliders and surface rotation where visible. Tracking coordinates in this dashboard remain relative image-axis measurements, not calibrated metric 3D reconstruction. Key states are dashboard-only.

Cartesia status speech is integrated behind an opt-in voice toggle and test button. Configure `CARTESIA_API_KEY` in ignored `.env` as described in `docs/cartesia-voice.md`. Authenticated generated speech has not been verified; provider tests use explicit fixtures.

Final verification before publication: `.venv/bin/python -m pytest -q` → **40 passed**; all `tests/*.cjs` checks passed. `git diff --check` passed. Credential scan found no matching tokens/private keys in publishable source files. `.env`, recordings and model weights remain excluded.

Launch: install the project with AI dependencies and prepare model weights per README, then run `.venv/bin/python -m vision.live` and open http://localhost:8765.
