# Phantom vision — local webcam tracker

Current demo: `.venv/bin/python -m vision.live`, then open
http://localhost:8765 in Safari/Chrome and press **Start webcam**. The connected
USB webcam is preferred automatically. Keep it still, let the scene settle, then
move an object to see a green tracking region, details and motion trail.
No iPhone or OBS setup is needed for this mode. **Find another object** resets
the target. This is real live 2D tracking, with automatic loss/recovery.

The multi-camera backend remains available for later work; the current default
page is intentionally one webcam. Earlier dual-camera setup below is historical.

Agent 2's selection, detection, tracking, correspondence and local demonstration
adapter. No shared backend or calibration contracts are replaced by this prototype.

## Can-tilt joystick → held W/A/S/D

Tilt a soda can like a joystick. Tilting presses a key, holding the tilt holds it, and returning upright releases it. It uses the overhead camera.

Full guide: [`docs/can_joystick.md`](docs/can_joystick.md).

```bash
pip install -e '.[ai,joystick]'
python -m vision.prepare_model --size s                    # once: outputs/models/desk-yoloe-s.pt
python -m tilt_joystick --camera 0 --dry-run --calibrate-direction   # logs key events, presses nothing
python -m tilt_joystick --camera 0                         # real keys; macOS needs Accessibility permission
```

## Calibrated overhead mapping (metres)

Calibrate the overhead webcam with agent 1's tools, then start with
`--calibration calibration/data/<file>.json --top-camera cam_1`. Overhead objects then
report metric table X/Y (`table_xy_m`) and the cards and map show centimetres.
See [calibrated mapping](docs/calibrated-mapping.md), [camera ingest](camera/README.md),
[calibration](calibration/README.md) and the [printable stands](camera/hardware/).

## Two live cameras and a separate object map

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[ai,test]'
.venv/bin/python -m vision.prepare_model
.venv/bin/python -m vision.live
```

Open **http://localhost:8765** in Safari/Chrome on the Mac. Find cameras, assign one
physical camera as **front** and a distinct phone as **top**, then connect each.
The overhead phone should point straight down. Previews are clean native video;
the separate map shows the overhead target's silhouette/path. Keep cameras still,
let the background settle, then move an object. No manual box is required.

For Apple Continuity Camera, connect with data cables, enable Continuity Camera,
trust the Mac if prompted, then lock and mount each phone. Both must be exposed
as separate camera sources; a second cable does not guarantee this. Desk View is
excluded because it is not a second physical camera. See Apple's setup guide:
https://support.apple.com/en-us/102546

If only one iPhone appears, see [camera app alternatives](docs/camera-input-options.md).
External apps often expose their feeds only inside OBS or as one composite webcam;
a transport adapter is required before those sources can enter this browser UI.

## Detection and focus

Default: local YOLOE-26 small instance segmentation with a saved 12-category desk
profile, periodic mask correction, sparse optical flow and reference-based recovery.
AI mode waits for two consistent current-frame object masks and never silently
falls back to arbitrary motion regions. Motion-only mode is an explicit CLI option.
The model can misclassify objects and does not guarantee arbitrary-object tracking.
It is configured for: can, bottle, cup, box, phone, book, pen, ball, mouse, keyboard,
scissors and remote. One target per camera; identities are independent until matched.

`vision.prepare_model` downloads official public model assets into ignored
`outputs/models`, including a one-time ~242 MiB text encoder and ~9 MiB source
weights. The saved profile is kept in ignored outputs/models. The optional Ultralytics code and model
are distributed under upstream AGPL-3.0 terms (see https://www.ultralytics.com/license).
Runtime inference is local; frames/audio are not recorded or uploaded. Microphones
are never requested. CPU/MPS selection is automatic; `--device cpu` forces CPU.
Offline/no-model mode: `.venv/bin/python -m vision.live --detector motion`.

Each camera requests continuous autofocus/exposure only if its capabilities expose
those controls. Manual focus is available only when supported. Otherwise focus is
managed by the iPhone; the UI says so. The detail score is relative Laplacian image
variance, not a calibrated measure of focus. It cannot fix motion blur or poor light.

## Mapping limits

The default overhead map uses normalized image coordinates with unknown height.
It is **not metric 3D**, even if the overhead phone is perfectly vertical.

The 3D tab accepts externally measured intrinsics/distortion and world-to-camera
poses. See [calibration format and geometry limits](docs/live-dual.md). It matches
surface feature descriptors across views, rejects bad reprojections/negative depth,
and retains a shared feature anchor. Independent box centers are never triangulated.
It leaves XYZ unresolved when calibration, shared details or close samples are missing.
Browser sample times do not verify camera exposure synchronization; any reconstructed
point is labelled as an estimate with unverified timing.

## Verification and recorded fixtures

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m vision.demo --preview /tmp/phantom-preview.jpg
.venv/bin/python -m vision.demo --video /path/input.mp4 --click 110 100 --mask /path/first-mask.png
```

Python 3.10+ with compatible OpenCV/NumPy wheels is supported. The recorded runner
uses selection rather than the live AI pipeline. The synthetic demo produces
image-derived 2D observations and never pretends to validate physical XYZ.

The live server is loopback-only, single-user and keeps latest frames in memory.
Analysis uses at most 800 pixels on the longest edge, one pending request per
camera, up to 24 analysis updates/second, with lower-rate segmentation. Native
video does not wait for inference. These are scheduling limits, not performance
promises. See [vision integration](docs/vision.md) and [status](docs/status/AGENT-2.md).

### Voice mapping and real WASD

The live studio now supports **Talk to map**: show an item and say “Map this can to a joystick.” Cartesia Ink transcribes the command, Sonic confirms it, and the mapped joystick can drive real W/A/S/D in the focused Mac app after Accessibility permission is granted. Choose Game mode for held keys or Document mode for repeated letters. Overhead-only mode works without an iPhone. See [voice mapping setup](docs/voice-joystick.md) for calibration, stopping, permissions and background-capture limits.

Voice commands can also use the ASI:One mapping agent: add `ASI1_API_KEY` locally, start the overhead camera, then click **Talk to map**. See [Morph voice mapping](docs/morph-mapping.md) for the input catalog, supported outputs and examples.

Physical inputs now bind to a discoverable desktop action registry: joystick keyboard input, movement-to-scroll, cover-to-press buttons, volume and built-in display brightness. Continuous action adapters reuse the same slider runtime. See [desktop action setup and limits](docs/desktop-actions.md).

Optional **EdgeTAM + optical flow** hybrid tracking is available with `--temporal edgetam`. See [setup, launch command and measured limitations](docs/temporal-tracking.md).
