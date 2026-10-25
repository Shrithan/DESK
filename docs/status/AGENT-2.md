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

## Follow-up: automatic recovery

Implemented immutable-reference SIFT matching with geometric checks and two-frame
confirmation. Four tests pass. User clip recovered at 2.633 seconds after loss at
1.983 seconds; 402/441 frames report tracking. This is not measured ground-truth
accuracy; box propagation drifts/shrinks toward the end. See docs/vision.md.
This supersedes the earlier explicit-reselection-only behavior.

## Single-camera live mode and preview latency

Added `python -m vision.live`: loopback-only camera page with USB Continuity Camera
selection, paused-frame rectangle selection, motion readouts, feature overlays,
loss/recovery, clear and stop. Browser displays native camera video independently
of analysis. Removed the original 80 ms per-frame wait; analysis now targets up
to 30 updates/second with one in-flight request and an 800-pixel longest edge.
Old overlays expire after 250 ms. JPEGs are not recorded or uploaded externally.

Seven tests pass, including the HTTP JPEG → selection → movement pipeline, stale
selection rejection, loss/recovery, resolution resets and cross-origin rejection.
Safari was observed receiving the actual iPhone camera feed, then disconnecting.
The old page subsequently showed a Mac camera at 11 analysis FPS / 4 ms round trip,
consistent with preview pacing being the bottleneck. Updated preview architecture
requires reloading the page. No post-fix iPhone end-to-end latency is claimed.

Local CPU benchmark on 180 prerecorded frames at the new analysis resolution:
tracked-frame processing median 3.1 ms, p95 3.3 ms; searching median 14.9 ms.
These are server processing measurements, not live sensor-to-screen latency.

## Automatic live motion acquisition

Live mode now defaults to automatic acquisition without a manual box. A fixed
camera learns the background over 15 frames; a consistent moving foreground
region seeds the tracker after three detections. Manual selection is optional.
Hand/object separation is not solved; one moving region is followed at a time.
Nine tests pass, including no-click acquisition, ID retention after loss/return,
disabling acquisition and rejecting a large global image change. These tests
use synthetic JPEGs. Automatic acquisition has not been verified on physical
phone input in this checkpoint.

## Dual-camera workspace and capture alternatives

Implemented front/top role isolation, two native clean previews, separate overhead
silhouette/path map, optional externally calibrated metric reconstruction with
persistent matched surface anchors, and capability-checked autofocus/manual-focus
controls. Unknown height stays unknown. Camera timing is explicitly unverified.

Local detector: prompted YOLOE-26 nano with 12 desk categories, periodic neural
mask correction and feature replenishment. On the earlier user clip it segmented
the can as a bottle (raw class score .332); warm CPU inference 22.8–26.4 ms on one
sample. That is not a detection-accuracy benchmark or live two-camera latency.
The full tests now pass: 12 tests, including independent front/top HTTP state,
no XYZ without calibration, synthetic metric geometry, cheirality/reprojection
rejection, automatic motion acquisition and recovery. Browser JS syntax and
package dependencies pass checks.

Hardware blocker: native AVFoundation enumeration exposes one iPhone (14 Pro
Max), not two. Desk View entries are views of existing cameras, not another phone.
Neither simultaneous physical two-phone capture nor browser focus support has
been verified. Camera for OBS Studio explicitly documents multiple USB iPhones
and is the preferred capture-app trial; Camo and VDO.Ninja are alternatives.
These transports need adapters; installing them does not by itself provide two
independent browser webcam devices. See docs/camera-input-options.md.

## Webcam-only live demo

User replaced the phone approach with a single USB webcam. Default page now uses
one automatically preferred external webcam, native video plus tracking overlay,
image movement readouts and reset/recovery controls. The C270 HD WEBCAM was
observed live in Safari. Initial scene-wide motion was rejected with an added
bounding-area/fill filter; the target is reset so the user can move their object.
All 12 tests pass (1.38 s); JS syntax and diff whitespace checks pass. No physical
object tracking accuracy or 3D reconstruction is claimed for this single view.

## Recognition acquisition fix

Diagnosed actual live state: a lost moving-region target remained selected even
while the model detected a bottle-like object at raw score .593. Neural acquisition
was gated behind background subtraction and could lock onto unrelated motion.
AI mode now acquires two consecutive current-frame instance masks directly,
never silently selects background motion, and expires tracks without renewed
semantic support. Explicit motion-only mode remains for development.

Upgraded YOLOE-26 nano to small and improved text prompts (e.g. soda can instead
of ambiguous can). On the supplied earlier clip, the revised profile detected
soda can at raw score .664. That is a class score on one sample, not measured
accuracy. CPU inference with the larger model was about 43–46 ms in a prior
prompt run; physical webcam latency remains a separate measurement.
Fourteen tests pass, including stationary AI acquisition and motion-fallback
rejection in AI mode. The service is restarted for live verification.

Live verification after the fix: Safari showed the C270 feed with a tight box and
150 feature points on the actual drink can, rather than the background. Displayed
tracking rate was 23.3 updates/s. The live class was still bottle, so semantic
label accuracy remains imperfect even when the physical target is correctly
localized. The corrected live tracker is left running.

## Responsive movement thresholds

Live AI sessions now use forward/backward flow tolerance 2 px (was 1), surviving
feature fraction .30 (was .50), affine inlier fraction .55 (was .70), RANSAC error
3 px (was 2), and max image gap 800 ms (was 500). Conservative library/motion-test
defaults are retained. There is a bounded 350 ms predicted state on temporary flow
failure; it emits no measured feature points, and the UI uses an amber dashed
last-known box. An unambiguous nearby semantic mask can restore tracking during
that window with new feature IDs. Semantic support timeout is 1.8 s (was 1.0), and
mask refresh accepts IoU > .20 (was .30); ambiguous candidates remain rejected.

Sixteen tests pass (1.50 s), including partial feature dropout, recovery from a
brief blank frame, and expiry of stale/predicted measurements. This tuning improves
tolerance, not a guarantee against identity switches or all blur.

### Continuous multi-object webcam tracking

LiveSession now maintains multiple targets in one Tracker. Neural detections run
once per detection interval and are matched one-to-one against existing objects;
unmatched objects acquire after two consistent detections without clearing prior
tracks. Overlapping duplicate class detections are suppressed, and ambiguous
associations are withheld. Each object owns its origin, motion samples, semantic
support timeout and stable display number. The response includes `objects` while
retaining primary-object fields for existing clients/stereo compatibility.

The webcam UI shows separate colored boxes and movement cards, each with its own
recent 2D path chart, displacement and speed. Reset all tracks is optional when
adding objects. Seventeen tests pass, including two same-class objects entering
at different times, moving independently, and independent loss. Synthetic policy
tests do not establish real-world recognition or identity guarantees during full
occlusion or crossings of indistinguishable objects.

### Two orthogonal USB webcams: relative axis fusion

The default page now opens two distinct webcam devices (phones/virtual sources
excluded) and captures both views before awaiting encoding or inference. Each
camera retains its independent multi-object tracker. Combined pairs take X from
camera 1's horizontal center and Y from camera 2's horizontal center, subtract
per-pair origins, and display percent of each image width. Side views roughly
90 degrees apart are assumed; perspective and unequal scales remain uncalibrated.
This is approximate relative XY, not metric triangulation or measured XYZ.

Unique compatible object classes can auto-pair. Ambiguous same-class groups have
explicit cross-view pairing controls. Pair origins and paths remain independent;
missing/predicted observations or mismatched sampling times suppress the combined
position. Reverse-axis controls and zero-all are provided. Single webcam UI is
retained at /single. Frames remain local. Browser sampling is not sensor sync.

Validation: 17 Python tests pass; node tests/test_fusion.cjs exercises ambiguity,
independent axes, missing views, timing rejection, and zeroing. JavaScript syntax
check passes. Physical camera status is checked separately in Safari.

### Single shared object experiment (two webcams)

The default dual-camera page now assumes the user places one physical object in
the shared view. Each camera enables /api/single-target and holds one local track;
no further object identities are acquired until reset. Unambiguous semantic
recovery can restore that local identity after loss. The frontend pairs the two
local tracks regardless of class label, displays Object 1 in both feeds, and
retains one combined relative XY path through label changes/loss/return. Missing
views suppress the combined position. Manual multi-object pairing is removed
from this experiment. Single-target assumption is explicit; this does not prove
cross-view identity or provide calibrated world coordinates.

Validation: 18 Python tests pass plus node tests/test_fusion.cjs, including
single-target count, ID-preserving reacquisition, different labels between
cameras, class changes, independent axis sources, missing views and timing.

### Foreground selection and medium model (background-bottle regression)

The supplied screenshot exposed a selection error: the small model scored a
small distant bottle higher than the foreground can. A local in-memory comparison
on the screenshot found the small model's foreground score .270 in camera 1,
below the former .30 cutoff. YOLOE-26m detected it at .388; camera 2 foreground
score was .671 and background .544. These are model scores, not accuracy estimates.
The medium model is now default; prepare_model --size m downloads official assets.

Neural continuation threshold is .12, while new single-container acquisition
requires .24 on two detections (.30 for multi mode). The single-object test now
filters to can/bottle/cup, mask area >= .8% of frame, height >= 12%, and ranks by
foreground size rather than class confidence. Recovery rejects bbox area changes
outside .35–3x of the last box, and uses these same foreground filters. This is a
size prior, not measured depth, and small/far intended objects will be excluded.

AI refresh interval is .12 s rather than .22 s. Single-target neural recovery
skips redundant whole-frame SIFT searches while retaining object identity and
seeding new feature IDs. Conservative/default appearance recovery is unchanged.

21 Python tests pass plus JS fusion checks, including foreground-vs-background,
size-gated recovery and low-confidence continuation without low-confidence seeds.
A 12-frame sample of the earlier video gave median MPS detector time 27.2 ms for
medium vs 15.3 ms for small; this is a latency sample, not an accuracy benchmark.

### Mixed webcam/iPhone sources and full camera view

The dual-source picker now includes iPhone/Continuity Camera and virtual camera
sources, excluding Desk View. It prefers USB webcam + iPhone when available and
still requires distinct device IDs. Browser capture requests 1280x720, 30 fps,
with resizeMode none preferred; analysis still downsizes to 640 pixels. This
requests a native view, not a guaranteed larger optical field of view.

Each source requests its minimum exposed zoom on connect and provides Reset zoom.
The UI reports actual resolution and whether the driver exposes zoom. When no
zoom control exists, users must move the fixed-lens camera back/up to cover more
space. Full images use contain sizing rather than CSS cropping. Camera list can
be refreshed. USB iPhone setup uses Apple's Continuity Camera, existing trust
and same-account requirements; camera discovery/live opening is checked in UI.

21 Python tests, JS syntax check, and single-object fusion tests pass. This change
only enables mixed input sources; the current mapping remains relative XY and
does not implement calibrated overhead/side XYZ.

### Matched camera cadence and portrait iPhone processing

Both sources now request a common supported frame rate (up to 30 fps). Source
frames are counted with requestVideoFrameCallback where available. Both previews
are drawn together only after a new frame is available from each source; faster
input frames are skipped. Analysis also requires fresh frames from both sources,
so duplicate source frames are not counted as extra updates. Measured common
preview rate, incoming rates and paired tracking cadence are reported separately.
This matches display/processing cadence; it does not synchronize sensor exposures.

A shared canvas transform rotates the full iPhone image to portrait by default
when its native stream is landscape. Native portrait is not rotated again.
Original/CW/CCW modes are selectable. Preview, tracking image and overlays use
identical portrait geometry, with no crop or stretched image. The phone must be
mounted vertically to gain vertical scene coverage; rotation alone cannot reveal
scene outside the lens. Orientation changes reconnect/reset the tracking session.

Validation: 21 Python tests, fusion JS checks and test_video.cjs pass. Video tests
cover portrait dimensions, avoiding double rotation, webcam orientation, fresh
paired frames and matching both frame-rate constraints to the slower capability.

Portrait follow-up: live inspection showed Continuity Camera can send an already
upright scene in a landscape frame even with the phone upright. Auto mode now
requests 720x1280 / 9:16 with resizeMode none preferred for iPhone, and leaves the
native image orientation intact. Explicit CW/CCW modes remain available for
actually sideways buffers. This replaces the initial automatic-rotation approach;
rotation alone is not additional vertical coverage. Actual driver settings must
be checked after opening. Shared preview rate was observed around 21–25 fps with
both source streams around 30 fps; AI cadence is measured separately over a window.

Live verification succeeded: Safari reports Logitech 1280x720 and iPhone
720x1280. The iPhone preview is upright in the tall native format. Both inputs
measure approximately 30 fps; the shared previews were observed at 23–26 fps,
and both cameras share the paired AI update cadence (about 18 updates/s in one
sample). The user confirmed the phone is physically upright.

### Overhead Logitech + side iPhone / YOLOE-26X

User confirmed Logitech overhead, upright iPhone at the side. The default picker
now assigns front=side iPhone and top=overhead Logitech. Viewer inputs are top
horizontal X, top vertical Y, and side vertical Z, with independent direction
switches and a relative 3D box/path. Every coordinate is image-axis-relative and
uncalibrated; perspective, tilt and centroid changes can affect it. It is not a
metric XYZ measurement. Calibration remains necessary for physical mapping.

YOLOE-26X is now default, prepared from official weights with extra prompts for
the top of a soda can and overhead bottles/cups. Overhead candidate filtering
permits small round tops (area .15%, min dimension 2.5% of short image edge)
while side filtering retains foreground-size rejection. Actual model name is
shown in UI. A warm MPS test measured median inference 65 ms/frame (5 blank test
frames), which is not an accuracy or live throughput benchmark.

Both acquisition profiles now require observed target motion. Pending candidates
accumulate displacement from an initial anchor, allowing gradual moves. The
cross-view pair additionally requires two coordinated movement events within
350 ms before enabling the relative 3D point, and requires rechecking after more
than one second without both views. Camera-local IDs stay fixed and one shared
identity is retained. This is motion consistency under a one-object experiment,
not proof of cross-view identity among multiple moving lookalikes.

23 Python tests plus video and overhead/side JS tests pass. Checks cover small
round overhead masks, stationary-background rejection, XYZ axis sources,
coordinated movement, missing-view suppression, identity recheck, frame cadence
and portrait geometry. Live physical acquisition is verified separately.

### Smooth map presentation

The map redraws through the display animation loop independently of camera/AI
updates. A time-based exponential response follows measured XYZ targets (110 ms
for small movement, 55 ms for larger displacement), without velocity extrapolation.
The displayed trail samples this smoothed point. Missing observations hide the
point and break the trail rather than extrapolating across loss. Zeroing resets
all visual state. A fixed map extent prevents automatic box rescaling jumps.
Raw measurements/readouts and target matching remain unchanged; visual smoothing
adds a small response delay and does not increase measurement accuracy.

JS smoothing checks pass for convergence, no overshoot and consistent elapsed-
time response, alongside existing overhead/side fusion and video cadence checks.

### Multiple overhead/side objects with separate smoothed paths

Default dual-camera client now enables /api/workspace-multi for each source.
This accepts supported movable classes, requires motion for new acquisition,
uses smaller overhead silhouette thresholds, and retains per-camera multi-target
IDs. Lost tracks only accept compatible, high-overlap neural recovery and reject
near-tied row/column assignments. Whole-frame SIFT recovery is disabled in this
workspace profile to avoid independently recovering multiple tracks onto one item.

Cross-view candidates maintain independent coordinated-motion histories. Only
mutually unique compatible motion matches commit shared IDs; ambiguous moving
lookalikes wait. Manual side/overhead pairing is available for ambiguity. Each
pair owns origin, XYZ measurements, loss/recheck state, smoothed point and trail,
and color. One local track cannot be assigned to multiple pairs. Existing pairs
are not reset when new objects arrive. Movement should be demonstrated one object
at a time for reliable automatic matching among same-class objects. Motion
consistency remains heuristic, not identity proof, especially through crossings.

Relative XYZ remains uncalibrated. Twenty-four Python tests and JS fusion, video,
and smoothing checks pass, including two small overhead targets, independent loss,
ambiguous same-class motion, explicit pairing and duplicate-assignment rejection.

### Faster motion / bounded predicted map / independent camera rates

Sources now request up to 60 fps for iPhone and 30 for Logitech, each limited by
reported capabilities. Preview and frame submission run independently per source
with one in-flight frame each; the phone no longer waits for an overhead frame.
Actual source rates and per-source analysis rates are reported. Fusion only uses
accepted result timestamps, allows <=100 ms browser-sampling skew, and updates
XYZ with independent axis timestamps. Browser sampling is not exposure sync.

A new prediction.js provides bounded constant-velocity display estimates, capped
at 80 ms look-ahead and 180 image-axis-percent/sec. Predicted points have dashed
outlines and explicit labels; solid trails retain measured positions. Estimates
expire when any source axis is older than 220 ms, and new measurements correct
velocity, including reversals. A toggle disables extrapolation. Map animation
runs on display refresh rather than AI cadence (up to 60 Hz on a 60 Hz display);
this does not synthesize real webcam video. UI smoothing response is reduced to
22–55 ms for lower visual lag. No gesture classification is introduced.

Responsive LK now uses 41px windows and four pyramid levels for larger movement.
Workspace YOLOE refresh is 350 ms while all targets have healthy flow, and 120 ms
otherwise, reducing recognition stalls while retaining Extra Large detection.

25 Python tests pass including 22px/33ms fast translations with stable identity.
JS tests cover per-axis timing, prediction cutoff/clamping, corrections/opt-out,
independent 60/30 requests, ambiguity, multi-object identity, video and smoothing.
Live phone source maximum must be checked; recording capability does not imply
Continuity Camera will expose 60 fps.

Live check: two shared objects mapped simultaneously with YOLOE-26X. Continuity
Camera reports maximum 30 fps at current portrait format, so both requests are
30 rather than falsely reporting 60. Measured inputs approximately 30.1/29.5 fps;
analysis sample side 21 / overhead 28 updates per second. UI prediction toggle
is enabled and source vs predicted map cadence are separately labelled.

### Stable identity across brief camera dropouts

Workspace tracks now retain initial and recent same-camera masked HSV/normalized
grayscale signatures. A lost target can match an unambiguous compatible detection
within an 8-second memory window, plausible size and spatial bounds even when the
old/new boxes have low overlap. Ambiguous recovery detections are reserved rather
than spawned as duplicate IDs. One-to-one row/column ambiguity rejection remains.
Identity/class display names stay fixed; detector label flicker is kept separately.
Cross-view pairs now keep their confirmed ID association for up to 8 seconds of
missing visibility rather than invalidating it after one second. Measurement and
prediction expiry remains short; identity memory never means stale coordinates
are emitted. Initial origin, color and shared pair IDs survive confirmed recovery.

27 Python tests pass, including moved 2-second occlusion with can/bottle class
flicker, stable origin/ID/name, and ambiguous same-appearance returns remaining
lost without creating duplicates. Cross-view JS checks verify short-dropout
retention and long-gap revalidation. Appearance recovery is heuristic; lookalikes
and large viewpoint/scale changes can remain unresolved.

### Overhead-only flat input, joystick and relative rotation

Detector profile now includes disk/puck/coin/lid prompts normalized to disk.
Overhead disks automatically create separate 2D inputs without a side pairing;
users may assign any overhead track to XY joystick, X slider or Y slider. Sliders
support 0/100% travel endpoints. Inputs go inactive after lost/stale detections;
height is not inferred. Ordinary paired-object tracking continues independently.
Textureless disk masks may acquire with zero feature points; they only report
fresh semantic detections and never emit stale features as measurements.

XY controls render a centered joystick with circularly bounded travel and a reset
button. Rotation is relative image-plane yaw accumulated from robust affine fits
of persistent feature IDs, separate from direction of translation. The overlay
shows a rotation pointer and degrees clockwise when observable. Plain circular
objects without texture/marks show rotation unavailable. Feature loss invalidates
rotation until re-zero, while object identity remains retained. This is not
calibrated world yaw or full 3D orientation.

30 Python tests and JS flat-input, joystick, fusion checks pass, including
textureless overhead-only masks, independent slider endpoints, rotation versus
translation, insufficient points/invalid scale rejection and joystick bounds.

### Final control studio and adaptive smoothing pass

Control studio now presents a keyed registry of sliders, XY joysticks, available
overhead tracks and spatial objects. Summary counters and type filters expose
all configured controls. Cards show active/offline state, values, yaw, joystick
rotation arcs, generic 3D proxies, conversion/calibration/removal actions. Generic
object glyphs also appear in the spatial workspace. Camera setup/diagnostics are
collapsed. Stop is available in the header. Control actions retain DOM identity
across refreshes, avoiding buttons being replaced while the user clicks.

Added adaptive One Euro filtering to spatial measurements, flat inputs and yaw.
Synthetic check: stationary noise RMS .354 -> .073 (~79% reduction); 20-unit step
reaches 19.74 by 64ms. This is controlled signal validation, not a live-camera
accuracy benchmark. Retained YOLOE-26X rather than claiming a universal best model;
reviewed BoT-SORT/ByteTrack and SAM2 roles and limitations in PHASE1_HANDOFF.md.

A labelled simulated layout preview exercises cards without cameras/model access.
Static preview at port 8766 disables capture controls. Browser QA verified cards,
counts, filters, joystick-to-slider conversion, yaw/proxy rendering and no console
errors. Cameras and the inference server remain stopped per the earlier request.
30 Python tests and all JS suites pass. Final implementation/run instructions,
limitations and next-phase integration tasks are in docs/PHASE1_HANDOFF.md.

### Can joystick / recoverable overhead yaw

Investigated rotation unavailable: overhead yaw previously depended on persistent
feature IDs, and one failed fit invalidated rotation until manual reset. Overhead
rotation now aligns normalized interior surface texture against a saved reference
with Euclidean ECC. It excludes the circular boundary and rejects rotationally
symmetric texture, low correlation and unobservable plain circular surfaces.
Relative angle unwraps around the last verified value; matching can recover when
feature IDs are replaced. Reference remains through temporary track loss and
Center & zero yaw creates a new reference. Side-view relative rotation keeps
feature-based behavior; overhead yaw is not full 3D can tilt/orientation.

Added Use my can as joystick: arms acquisition of the unique/largest foreground
container track overhead, creates a Can joystick XY control and removes an
existing spatial pair for that track. Similar-size candidates require explicit
selection rather than arbitrary choice. This control uses slide for XY and twist
for relative yaw; a visible lid detail/mark is necessary to observe twist.

32 Python tests pass, including surface alignment after rotation/translation and
rejection of an untextured circular outline. Real physical lid rotation still
requires live validation; a synthetic rotation test is not physical accuracy proof.

### Can pivot skeleton and virtual WASD

User chose dashboard-only W/A/S/D display; no OS keyboard events or app control.
Added side-mask PCA centerline with estimated base/top endpoints and projected
lean angle, rejecting round masks without a reliable long axis. Both endpoints
are drawn in the live side view. Overhead can-joystick mode draws a saved neutral
pivot plus current control point; this is an approximate control reference, not
calibrated 3D base/top reconstruction. Moving relative to that pivot sets joystick
XY and heading. Actual surface twist stays separate from projected lean/heading.

Use my can as joystick enables pivot mode by default. Existing joystick cards
can opt in with Use pivot / WASD. Cards display W/A/S/D keycaps, including
simultaneous diagonals. Press threshold .18 and release threshold .12 provide
hysteresis; missing/stale data clears virtual keys. Centering resets the pivot.
Overhead Reverse X/Y controls invert the key directions when required.

34 Python tests pass plus JS pivot/key tests for forward/back/left/right,
diagonals, neutral, hysteresis, bounded travel and loss release. Skeleton tests
cover upright/leaning silhouettes and reject round/empty regions. No claim of
world yaw or physical 3D can orientation is made from the image centerline.

### 2026-10-24 — shorter-travel can joystick and dropout continuity
- Rotated virtual joystick axes for this mounting: previous D → W, A → S, W → A, S → D. Still dashboard-only key indicators.
- Full stick travel now takes 1/30 of the overhead frame dimension; adaptive input filtering opens faster during movement. Registry and input refresh now run about 30 Hz rather than 8/4 Hz.
- Hold last sampled control for 130 ms, then ease to neutral over 170 ms. Sample timestamps prevent repeated UI renders from extending stale input. No off-screen position extrapolation.
- Pivot mode adds side silhouette lean around a saved neutral at 12 degrees for full forward/back input. Only use a unique compatible side/overhead candidate and a stable base; ambiguous or moving-base silhouettes fall back to overhead translation. This is approximate image-plane tilt, not calibrated 3D orientation.
- Added setup advice: raise fixed-lens overhead camera physically for more coverage. Camera field of view cannot be expanded in software.
- Node checks passed for corrected axes, sensitivity, dead-zone hysteresis, dropout hold/decay/reacquisition, stale timestamps and tilt/base gating; existing flat input, fusion association and adaptive filter checks passed.

### 2026-10-24 — Cartesia voice feedback integration
- Added optional local-server Cartesia adapter, opt-in dashboard voice feedback and test button. Camera connection, joystick/slider readiness, sustained loss and recovery produce fixed spoken messages.
- Official current `/tts/bytes` contract verified: API 2026-08-14, Sonic 3.6, string voice ID and WAV output. Credentials reload from ignored `.env`; no frontend keys and no video/object data sent.
- Speech has independent locking, in-memory phrase caching, bounded network operations and quiet/debounced event handling; tracking does not wait for synthesis.
- No API key found in process environment or local `.env` when work began. Prepared `.env.example` and empty ignored `.env`; real Cartesia audio remains unverified until user configures credentials. No sponsor eligibility claim.
- Setup and implementation details: `docs/cartesia-voice.md`.

### 2026-10-24 — spatial-calibrated integration and oblique-camera neutral
- Integrated all of `origin/agent/spatial-calibrated` at `214f963` onto `codex/spatial-neutral-calibration` (base includes saved controls/Cartesia work).
- Web can joystick now learns a stable 1-second upright pose from measured overhead-mask features. Non-round/slanted neutral silhouettes are accepted, and centroid-noise dead zone suppresses rest bias.
- Added Learn W / Learn D: stable lean examples establish a local nonorthogonal image-to-control basis, supporting rotated/mirrored/oblique views. Keys are inactive during calibration and until the can returns upright. Recalibration releases immediately. Remains dashboard-only; no real OS key backend activated.
- Calibrated can controls use overhead relative centroid displacement; side projected lean is not blindly mixed into the learned axes. This is not metric 3D tilt; fixed base and repeat calibration after moving the camera are required. Instructions: `docs/tilted-camera-joystick.md`.
- Fixed reviewed identity regression: unique-class reassociation now requires bounded displacement, plausible size and appearance rather than assuming a sole detection is the same object. Added a deterministic background-can regression.
- Fixed visible studio/map units: calibrated tabletop X/Y in centimeters, side Z still relative image percent.
- Validation after integration: **215 Python tests passed, 2 skipped** (pynput optional tests), using isolated additional camera/hardware test dependencies; all **10 JavaScript test scripts passed**. `git diff --check` passed. Live server restarted with YOLOE X and asynchronous detection; physical upright/direction validation remains for the operator.
- Operator live confirmation: after upright calibration with the tilted overhead camera, the joystick stays centered and W/A/S/D are released. W/D direction examples remain operator-driven; no claim of metric tilt accuracy.

### 2026-10-24 — require USB-connected iPhone
- Added a bounded/cached macOS USB inventory check and local `/api/iphone/usb` endpoint, without returning serials or device IDs.
- iPhone-labeled browser sources require one verified USB-connected iPhone before start; live sessions stop if presence is lost/unknown on polling. Webcams are unaffected.
- Explicit limit: cable presence does not force or verify Continuity's video routing; macOS controls transport. UI/docs state this. No network settings changed.
- Verification: 21 relevant Python tests passed (live HTTP and USB guard), all 11 JS scripts passed. Mac inventory initially reported zero wired iPhones.

### 2026-10-24 — spoken mapping and real keyboard output
- Added click-to-talk Cartesia Ink STT and bounded in-memory mono WAV clips; Sonic confirms a recognized mapping. Deterministic joystick/stop grammar resolves a unique visible or recently moving object, with explicit Voice target selection on ambiguity.
- Added native macOS WASD output with opt-in arming, game hold/document repeat modes, owner tokens, ordered updates and independent 350 ms stale-input watchdog. Backend visibility checks release on tracking loss; recalibration/stop/removal/page close release output. Only W/A/S/D accepted. No real keys were used in automated tests.
- Added standard Accessibility permission request button and status. OS permission was false; the human must grant it before actual injection can be verified. No programmatic permission grant or network/security-setting change.
- Added overhead-only joystick mode so this path works without Continuity. Removed intentional hidden-tab capture pause and use video media time for frame progress; browser background throttling remains a documented limit.
- Real Cartesia round trip succeeded: Sonic example → Ink transcript “Map this can to a joystick.” → map_joystick intent, can label.
- Full suite: 230 Python tests passed, 2 optional pynput tests skipped. All 13 JS checks passed. Setup: `docs/voice-joystick.md`.

- Live permission/key validation: operator enabled the ChatGPT Accessibility entry. Server restart changed `/api/keys/status.accessibility` to true. Operator clicked the bounded native test and confirmed the local text field received `wasd`; all keys were released afterward. Actual microphone-to-object mapping is being tested by the operator.

- Physical voice validation succeeded: operator said “Yes, the voice mapped my can.” Dashboard displayed the real transcript “Map this can to a joystick.” and a Voice joystick card. Real key test field showed typed WASD. Current output is disarmed after the local test; operator can arm and focus the target app. Game-specific compatibility remains untested.

## Morph ASI:One mapping agent

Added `vision/morph.py`, `/api/morph/status` and `/api/morph/plan`. Cartesia transcripts now flow to an ASI:One planner with the actual tracked-object snapshot and a complete supported input/output catalog. Strict plans drive joystick, sliders or measurable surface rotation, with configurable supported key bindings and automatic activation. Missing API key is explicit. UI includes active plan, capability catalog and undo. Expanded native output beyond WASD while retaining per-controller key allowlists, ownership and watchdog releases. See `docs/morph-mapping.md` for exact limits and live-key setup.

## Generic desktop action registry and cover inputs

Separated physical source processing from output adapters in `vision/desktop_actions.py` and `vision/action_runtime.py`. Registered continuous parameters reuse one slider runtime; added CoreGraphics pixel scrolling, CoreAudio output volume and DisplayServices built-in brightness with actual availability discovery. `vision/cover.py` uses local MediaPipe hand overlap plus appearance/dwell/reset to drive one key tap per stationary cover cycle. Added sticker-region registration, selective SIFT recovery for registered tracks, generic action HTTP activation/update/stop, schema-generated ASI outputs, target list, active-state feedback, cover cards and global stop/cancellation. Real native brightness/volume readback tests restored their prior settings; real ASI mapping tests and local hand model inference verified. Physical cover interaction still needs operator verification. No universal arbitrary-app control is claimed: new settings require an executable registered adapter, not a new slider implementation.

## Exposure stability

Added verified C270 UVC exposure/white-balance locking (`vision/exposure.py`), browser/manual controls with automatic startup reapplication, and optional robust illumination normalization for live optical flow. Native C270 readback confirmed auto mode 8 → manual mode 1, exposure retained at 33.3ms, gain retained, auto white balance off. Helper source/binary remain ignored and MIT license retained. See `docs/camera-exposure.md` for setup and limits. Also completed the previously prepared desktop-action gap recovery/readback changes so brief camera contention pauses rather than immediately dropping a parameter mapping.
