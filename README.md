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

## Fetch.ai: five agents that set up, tune and fix the can joystick

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Chat with **DESK Coach** in ASI:One ("set up DESK for a racing game", "the steering is too twitchy",
"it keeps stopping"). The Coach speaks the Agent Chat Protocol and hands work to four specialist uAgents.
They read live telemetry from the can joystick and change its settings through a local control API.
They are never in the frame→key path, so they add no latency.

| Agent | Role |
| --- | --- |
| DESK Coach | ASI:One chat (Chat Protocol + cards), intent routing via the ASI:One LLM with a keyword fallback; pause/resume/undo/recalibrate itself |
| Setup | Game profiles (racing, Subway Surfers, Minecraft, Pac-Man, custom), key remaps, inversion; plans first, applies only on approval |
| Tuner | Reads the last 60 s of real tilt data, moves the triggers clear of your wobble, and measures before vs after |
| Doctor | Diagnoses lost tracking, slow frames, failed calibration and flicker, with concrete fixes |
| Validator | Watches 20 s of play after every change; keeps it or rolls back only that revision |

Addresses come from `agents/.seed` (gitignored), or from `DESK_AGENT_SEED`. Reuse the team's seed file to keep
the Agentverse addresses already published from `agent/fetch-five-agent-integration`.

```bash
pip install -e '.[ai,joystick,fetch]'
# Terminal 1: the real key path plus the agent control API on ws://127.0.0.1:8766/ws/control
python -m tilt_joystick --camera 0 --control              # add --dry-run to log keys instead of pressing
# Terminal 2: the four specialists (Bureau, port 8000) and the Coach (port 8001)
python -m agents.run
```

Open the Inspector link that the Coach prints, click **Connect → Mailbox**, then talk to **DESK Coach** in ASI:One.
`ASI_ONE_API_KEY` in `.env` turns on LLM intent parsing.
No camera? Run `DESK_DEMO_MODE=1 python -m agents.run`; it uses a simulated player on the same API.

How the agents' degrees map onto the joystick (`tilt_joystick/agent_control.py`):
- A full push is about 22° × `tilt.full_scale`.
- The forward/back trigger becomes `keys.press`/`keys.release`.
- A separate left/right trigger and inversion are applied as a per-axis gain before the 8-way sector mapper.
- A trigger above the measurable range raises `full_scale` so it stays reachable.

Every change is checked against safe limits, releases held keys first, is recorded, and can be undone.
Tests: `python -m pytest -q tests/agents tests/tilt_keys tests/can_joystick`.

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
