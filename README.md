# DESK — spatial tracking and Fetch.ai agents

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

DESK tracks objects on a table and can turn can tilt into keyboard input. Its
Fetch.ai workflow has five uAgents: an Agent Chat Protocol Coach in ASI:One,
plus Setup, Tuner, Doctor, and Validator specialists. The agents read telemetry
and change settings through a local control API; they do not run in the
latency-sensitive tilt-to-keys loop.

| Agent | Address | Role |
| --- | --- | --- |
| DESK Coach | `agent1qwtp9sexgrsgrsjqp8u39fhwyslnn7fs85lc7dxwj72zaa0jwnwujatn4vw` | ASI:One chat and orchestration |
| Setup | `agent1qtczmqkg8vgyk34fe4rkwn96rla0jlnwj70n6pn3vm7dkrgcy9t8xdwsl3u` | Game profiles, remaps, inversion |
| Tuner | `agent1q0lhr74qmn5f6pkgujd9qd7e56y2ns0kg5q8q5hm0w9sqhnrpeg2khg9x8y` | Telemetry-based sensitivity changes |
| Doctor | `agent1qd69tn2vkzhdee23seeyc5jhzt7zppudgtlsscrtvlh3wxt68syng6rg055` | Tracking and calibration diagnosis |
| Validator | `agent1qfmxzr0nq9nef4cx8e03f06tjmhp03qezqumm2syhzuf32cuclaegjymcx7` | 20-second check and conditional rollback |

These addresses come from a private `agents/.seed`. Keep that file local and
never commit it. A fresh seed produces different addresses; set
`DESK_AGENT_SEED` or reuse your existing `agents/.seed` to preserve them.

## Run the Fetch.ai workflow

Use Python 3.11 or newer. On the DESK Mac, install the agent dependencies and
start the shared simulated player plus all five agents:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[fetch,test]'
DESK_DEMO_MODE=1 .venv/bin/python -m agents.run
```

The launcher starts the demo control server on `127.0.0.1:8766`, the four
specialists in a Bureau on port 8000, and the standalone Coach on port 8001.
Keep the terminal running. Connect the Coach's mailbox through the Inspector
URL printed by the launcher, then address **DESK Coach** in ASI:One. Try “set
up DESK for a racing game,” review and apply the plan, then “the steering is
too twitchy.” The Tuner uses live telemetry; after a change, the Validator
checks the next 20 seconds of simulated play and reports whether it kept or
reverted the change. ASI:One card buttons are also accompanied by text so the
workflow remains usable if a card is not rendered.

For real tilt input, start the control and input server separately and run
the agents without `DESK_DEMO_MODE`:

```sh
.venv/bin/python -m backend.tilt_keys.run --input ws --backend log --control
.venv/bin/python -m agents.run
```

Send `tilt_update` messages to `ws://127.0.0.1:8766/ws/tilt`. The agent control
API uses `/ws/control` on the same port. Use `--backend pynput` (install
`'.[keys]'`) only when ready to send actual keyboard events. The spatial
tracking web app remains on port 8765. Its current calibrated overhead output
provides X/Y position and image-plane rotation; a camera-to-tilt adapter that
produces forward/right angles is still required for live can control. The
simulated player exercises the complete agent and settings workflow today.

Run the focused integration tests with
`.venv/bin/python -m pytest -q tests/agents tests/tilt_keys`.

## Spatial tracking

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
