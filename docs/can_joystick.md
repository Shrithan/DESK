# Can-tilt joystick → W/A/S/D

**Behaviour:** tilt a soda can to press a key. Hold the tilt to hold the key, and set the can upright to release it.
- Real key down/up events, never taps.
- 8 directions, including diagonals (W+D, …).

## How it fits the repo
| piece | where | reused or new |
|---|---|---|
| segmentation model | the prepared YOLOE weights from `vision/prepare_model.py` (`desk-yoloe-s.pt`, which contains `soda can`) | reused |
| tracking | ultralytics `model.track(persist=True, tracker=bytetrack.yaml)`, plus LK optical flow between model runs | new |
| One Euro filter | `backend/tilt_keys/one_euro.py` | reused (agent 3) |
| key safety | `backend/tilt_keys/output.py` `EdgeTriggeredOutput` (releases before presses) and `backends.py` (pynput, log, macOS Accessibility check) | reused (agent 3) |
| tilt estimator, 8-way sector keys, event bus, overlay, record/replay | `tilt_joystick/` | new |

The web joystick in `vision/web/flat-input.js` only displays keys and cannot press OS keys, so this runs as one low-latency Python process instead.

## Run
```bash
pip install -e '.[ai,joystick]'
python -m vision.prepare_model --size s
python -m tilt_joystick --camera 0 --dry-run --calibrate-direction
```
- **`--camera`:** the overhead C270 is usually index 0 (see `python -m camera devices`). A video file also works.
- **`--dry-run`:** prints `KEY DOWN w` / `KEY UP w` and presses nothing.
- **Real keys:** drop `--dry-run`.
  - **macOS:** System Settings → Privacy & Security → **Accessibility**: enable your terminal app, then restart it. The program warns at start if it's missing.
  - **Global pause key (F8):** also needs **Input Monitoring**.
- **Config:** every threshold is in `tilt_joystick/tilt_joystick.toml`. Pass another file with `--config`.

### Window keys
| key | action |
|---|---|
| `space` | pause/resume (releases all keys) |
| `c` | redo neutral calibration |
| `r` | redo neutral + W/D direction calibration |
| `q` / `Esc` | quit |

The global pause hotkey is F8 (`keys.pause_hotkey`).

None of these use W/A/S/D, so our own presses can't trigger them.

## Calibrate
1. **Neutral (~1 s):** stand the can upright under the camera and keep it still until 100 %.
   - The base anchor, apparent radius and silhouette shape are averaged.
   - Movement restarts the second.
2. **Direction** (with `--calibrate-direction` or `r`; saved to `outputs/tilt_joystick_direction.json`):
   - "Tilt toward W" fits the rotation between the camera image and your W.
   - "Tilt toward D" detects a mirrored image.
   - Then set the can upright: keys only start after that.
   - Without this step, image-up is W and image-right is D.

## How tilt is measured
Everything is in units of the upright apparent radius `r0`, so camera height doesn't matter.
1. **Centroid shift:** `(centroid − anchor) / r0`. Seen from above, the top swings out over the base.
2. **Shape change:** the positive eigenvector of `cov(now) − cov(neutral)`, divided by `r0²`. Tilting stretches the silhouette along the tilt axis. It takes its sign from the centroid shift.
3. **Combine and scale:** the two cues are fused, rotated by the direction calibration, and divided by `tilt.full_scale`.
   - The default of 1.0 gives a full push at about 22° and a press at about 7°.
   - Then One Euro (`filter.*`) is applied and the result is clamped to the unit circle.

**Robustness:**
| situation | rule |
|---|---|
| mask area outside `area_min_ratio`–`area_max_ratio` × neutral (hand over the can, merged blobs) | dropout |
| one-frame jump bigger than `max_jump` | dropout |
| dropout ≤ `hold_ms` (250) | keep the last value, status `holding` |
| dropout longer than that | release every key, show **LOST** |
| camera stall | counts as a dropout |
| can resting upright-shaped, still and reading < `recenter_max` for `recenter_after_s` | anchor drifts back to it (slid can, camera settle); a held tilt is never re-centred because its silhouette is elongated |

## Keys
- **Press and release:** a key is pressed when magnitude > `keys.press` (0.35). Everything is released when it drops below `keys.release` (0.25).
- **Sectors:** 45° each (90° with `diagonals = false`). The current sector holds until the angle is `sector_hysteresis_deg` (10°) past its edge.
- **Example:** going W → W+D only presses D, so W never flickers.
- **Ordering:** on a change, old keys go up before new ones go down.
- **Every key is released on:** loss, pause, recalibration, `q`, Ctrl+C, SIGTERM, an exception (try/finally), and interpreter exit (atexit). The pynput backend also releases anything it ever pressed when it closes.

**Event bus (`tilt_joystick/bus.py`):** `joystick {x, y, mag, status, valid, t_ms}`, `key_down {key}`, `key_up {key}`, `status {paused}`. `--events-log ev.jsonl` writes them all.

## Tune
| symptom | change |
|---|---|
| jitter at rest | lower `filter.min_cutoff_hz` |
| lag on fast tilts | raise `filter.beta` |
| needs too much tilt | lower `tilt.full_scale` |
| presses by accident | raise `keys.press` |
| diagonal chatter | raise `keys.sector_hysteresis_deg` |
| fps < 30 | `detector.image_size = 416` or `detector.detect_every = 2` (flow fills the gaps) |

For repeatable tuning, record once and replay with different configs. Replay needs no camera or model and is deterministic:
```bash
python -m tilt_joystick --camera 0 --dry-run --record runs/tilt1.jsonl
python -m tilt_joystick --replay runs/tilt1.jsonl --config my.toml --events-log ev.jsonl
```

## Measure
- **Console output:** once per second it prints fps, end-to-end latency (mean and p95) and per-stage ms/frame: wait, detect, model, estimate+keys and draw.
- **What end-to-end covers:** from frame arrival in the process to key events sent. Add the camera's own exposure/USB latency (typically 30–60 ms for a C270, not measurable in software) for a true glass-to-key figure.
- **Over budget:** prints `OVER BUDGET` when p95 > `latency_budget_ms` (90).

**Manual check:**
1. Open `tilt_joystick/keytest.html` in a browser and click it.
2. Run without `--dry-run` and hold each tilt for 3 s.
3. Expect one DOWN, the hold timer growing, one UP, and `flicker 0`.

## Tests
```bash
python -m pytest -q tests/can_joystick tests/tilt_keys
```
**Coverage:**
- Deadzone, magnitude hysteresis, all 8 sectors, the boundary at 22.5°, angle hysteresis, wrap-around, 4-way mode.
- Holding 3 s gives exactly one down and one up.
- W→S sends `up w` before `down s`.
- Dropout of 200 ms is held; 330 ms is released.
- Hand occlusion, a single glitch frame, pause and close.
- Rotated and mirrored camera calibration.
- Drift re-centring, deterministic replay, CLI replay with the event log.
- Detector lock-on and optical-flow logic (stubbed model).
- Synthetic overhead can silhouettes come from `tests/can_joystick/synth.py`.

## Limitations
- **Not yet measured on hardware:** fps and latency on your Mac. The cloud environment has no camera or GPU, and torch can't be installed there.
  - The detector API calls (YOLOE `set_classes`, `model.track`) follow ultralytics 8.3.x. If your version rejects the text prompts, it keeps the prepared prompt set and says so.
- **One overhead camera:**
  - Tilting straight toward or away from a side camera isn't covered here.
  - A very short can, or a tilt under about 5°, is hard to see.
- **No hand subtraction:** MediaPipe isn't in the repo. Hands are handled by the area check and the 250 ms hold. Hold the can low so your hand doesn't cover its top.
- **Seated in a holder:** a can whose base moves while tilting (no pivot) reads as tilt plus slide. The centroid shift then includes the slide, so press the base down or put the can in a shallow cup.
