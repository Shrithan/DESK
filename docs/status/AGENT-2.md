# Agent 2 checkpoint — 2026-10-24

## Initial inspection

Repository was empty: no commits, README, contracts, implementation or remote refs
returned by successful fetch. Branch: `agent/markerless-vision` (initially unborn).
System Python 3.15 had none of NumPy/OpenCV/pytest. A local Python 3.12 virtual
environment now supplies CPU vision dependencies. No AGENTS.md was found.
The general coordinator brief and the specific assignment differ: this work follows
the specific Agent 2 scope, with integration readiness documented here.

## Working

Callable selection from a click or supplied mask; sparse temporal feature tracking;
affine mask propagation; stable per-camera feature/object IDs; conservative lost
state; multiple selections; calibrated cross-view candidate filtering; synthetic
fixture/demo, recorded-video runner and annotated JPEG output.

## Incomplete / blockers

No real-camera footage, calibration, or hardware validation. No SAM/model integration,
automatic cross-camera identity, persistent multiview anchor binding, server routes,
or physical XYZ demo. Frontend/backend/camera workstreams are absent in this checkout.
Synthetic timing is not end-to-end latency. Cross-view SIFT uses only pairwise local
appearance and calibration; temporal association and repeated-texture resolution remain.

## Next deliveries

- Agent 1: paired recordings plus intrinsics, extrinsics, distortion, metric scale,
  timestamp clock domains/offset bounds, and versioned calibration payload.
- Agent 2: validate actual objects and implement confirmed cross-view temporal anchors.
- Agent 3: finalize observation/selection schemas, adapter and triangulation rejection;
  publish `/ws/world` with metric coordinates, source cameras and explicit lost state.
- Agent 4: selection/confirmation UI, low-rate annotated previews and digital twin.

## Reproduce

See README setup, then `.venv/bin/python -m pytest -q` and
`.venv/bin/python -m vision.demo --preview /tmp/phantom-preview.jpg`.
Validation results and commit evidence are recorded below after execution.

## Validation evidence

- `.venv/bin/python -m pytest -q`: **3 passed**, 10.79 seconds (includes library startup).
- Synthetic RGB demo: 30 frames, final state `tracked`, ~647 processing FPS.
- MJPEG video reader smoke test generated from the same fixture: 30 frames,
  final state `tracked`, ~555 processing FPS. This is synthetic recorded input,
  not a recording of a physical object. Annotated JPEG visually inspected.
- Timing excludes camera capture, networking, model inference and rendering;
  no real latency, metric jitter or reprojection accuracy measurement is available.
- OpenCV 4.14.0.94, NumPy 2.5.4, pytest 9.1.1; Python 3.12 on this Apple Silicon host.
- GitHub CLI reported invalid authentication in the restricted environment;
  publication is attempted separately. No upstream code has been merged.
