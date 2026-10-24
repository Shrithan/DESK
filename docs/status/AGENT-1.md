# Agent 1 status: camera ingest, time sync, calibration

**Branch:** `agent/camera-calibration` · **Checkpoint:** H3–H5 (independent subsystem, tested against mocks and fixtures) · **Commit:** `a2be637`

## Runnable now (no cameras needed)
```bash
pip install -r camera/requirements.txt
python -m camera serve --video-dir camera/fixtures/synthetic_rig     # http://127.0.0.1:8100/
python -m pytest -q camera calibration                                # 35 passed (~40 s, Linux, OpenCV 5.0.0)
python -m calibration extrinsics --square-mm 20 \
  --images-dir camera/fixtures/synthetic_rig/extrinsics_board \
  --intrinsics-dir camera/fixtures/synthetic_rig/intrinsics_1280x720 --out /tmp/cal.json --no-history
```

## Working
- **Hardware:** a self-standing 1.0 × 0.6 × 0.7 m PVC frame with three printed C270 clamp mounts that have their aim built in (side cameras in portrait). All three cameras share about 43 × 23 cm up to 15 cm tall, where the old 0.5 m layout shared 5 × 9 cm (`tools/coverage.py`). Includes the parts list, cut list, renders, and print files that fit the Cal Hacks queue (each mount about 2–2h40m).
- **Ingest:**
  - USB, recorded-clip and synthetic sources.
  - Exact camera identity on macOS: AVFoundation uniqueID → OpenCV index, verified against OpenCV 4.x and 5.x source.
  - Newest-frame delivery, reconnect that keeps the id, health and stall detection.
  - Diagnostics page, HTTP API, CLI.
- **Sync:**
  - Pairing by nearest timestamp with a tolerance; missing cameras are reported.
  - Spread and completeness metrics.
  - Motion-based estimation of constant per-camera offsets.
- **Calibration:**
  - Printable board with a canonical corner order.
  - Automatic intrinsics capture with view selection and outlier rejection.
  - Board-on-table extrinsics with a triangulation cross-check.
  - Raised-board height check and bump detection.
  - Versioned, validated JSON with explicit conventions.
- **Fixtures:** synthetic clips plus ground-truth calibration and trajectory, for agents 2 and 3.

## Tests (35)
| area | what the tests cover |
|---|---|
| sync | pairing, missing cameras, offset estimation |
| ingest | bounded frame age, reconnect, degraded mode, unknown camera id |
| device mapping | fails loudly instead of guessing |
| rig geometry | nominal poses and aim |
| calibration models | round-trip and validation |
| geometry | projection, undistortion and triangulation round-trip |
| calibration pipeline (synthetic) | intrinsics, extrinsics, missing camera, height check, bump detection |
| integration | clips → ingest → HTTP → frameset → triangulated ball < 10 mm median |
| schemas | live outputs validated |
| hardware | mount fit, keep-outs, print size |

## Measured vs target
Numbers so far are synthetic only. See `camera/README.md` and `calibration/README.md`.

| metric | measured | status |
|---|---|---|
| intrinsics RMS | typically 0.06 px | synthetic |
| extrinsics error | ≈ 0.1 mm / 0.01° angled; ≈ 1 mm / 0.1° overhead | synthetic |
| fixture frameset spread | 18 ms (= the simulated offsets) | synthetic |
| real USB latency, jitter, dropped frames | not measured | **pending hardware** |
| real reprojection error | not measured | **pending hardware** |
| real tracking loss | not measured | **pending hardware** |

## Blockers
1. **Push refused (HTTP 403):**
   - The Claude GitHub App isn't installed on `Shrithan/desk`, so commits are local only and no draft PR exists yet.
   - The repo owner needs to install the app.
2. **No cameras in this environment:** every hardware number above is pending until the C270s and frame are built.
3. **Contracts:** the schemas proposed in `docs/interfaces/agent1_camera_calibration.md` need agent 3's ack. `main` and `shared/` don't exist yet.

## Next
1. Once the hardware is assembled:
   - Pin the device `unique_id`s.
   - Run intrinsics, extrinsics and verify.
   - Measure latency with a screen clock and record fps and dropped frames.
2. Multi-placement extrinsic refinement, to tighten the overhead camera's pose.
3. Add a binary frame stream if agents 2 and 3 run in a separate process.

## Evidence
- `docs/evidence/diagnostics_fixture_rig.png`: diagnostics page, 3/3 streaming on fixture clips.
- `camera/hardware/c270_frame/renders/*.png`: rig and mount renders.
- `camera/fixtures/synthetic_rig/`: clips and ground truth.
