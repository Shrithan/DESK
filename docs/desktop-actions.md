# Reusable physical controls and desktop actions

The mapping system separates **sources** from **destinations**. A joystick produces direction input, a slider produces normalized position/motion, and a stationary cover target produces a debounced press edge. An action adapter exposes an executable computer control. ASI:One selects the source, target, axis/direction, deadzone and keyboard mode from this registry. It does not write or execute code.

The same slider implementation can drive every registered continuous parameter. `ActionRegistry.register(identifier, spec, adapter)` adds a destination with a label, kind, compatible controllers, direction bindings and availability. A continuous adapter implements `get_value()` and `set_value(value)`; values are normalized to 0–1. The runtime applies centering, smoothing, speed limits and writes through that adapter. Adding a compatible parameter requires no new slider, browser gesture code or target-specific AI prompt branch. `tests/test_action_runtime.py` verifies this with an unrelated synth-filter test adapter.

An app-specific control still needs an executable adapter (API, supported integration or another reliable interface). The model cannot invent access to arbitrary app settings. Unavailable actions return `unsupported`; ambiguous objects return `clarify`. Available and unavailable targets, with reasons, are included in the catalog. There is one active native controller at a time; tracked dashboard inputs remain independent.

## Implemented targets

| Destination | Physical input | Behavior |
| --- | --- | --- |
| `keyboard` | Joystick or slider | Directional held keys / repeated typing |
| `keyboard` | Cover button | One key tap per cover/uncover cycle |
| `desktop.scroll` | X/Y slider | Movement produces pixel-wheel scroll; stationary input stops scrolling |
| `display.brightness` | X/Y slider | Adjust built-in Mac display brightness relative to its activation value |
| `audio.volume` | X/Y slider | Adjust current writable audio-output volume relative to its activation value |

Brightness and volume are discovered on the actual machine. Brightness uses macOS DisplayServices (a private API, potentially subject to OS changes); it targets an active built-in display and keeps a minimum of 8%. External-display DDC brightness is not implemented. Volume uses CoreAudio and reports unsupported outputs instead of faking control. If the audio output device changes, stop/restart the server to rediscover its adapter. Stop freezes system parameters at their last value; it does not restore the activation value.

Keyboard and scroll require macOS Accessibility. Keyboard targets the focused app; scroll follows normal macOS wheel routing under the pointer. While the dashboard has focus, keyboard/scroll are paused except in its explicit local test areas. Continuous system settings remain usable while viewing the dashboard. Camera loss or a 350ms update stall disarms the action. Cover events are immediate key-down/up pairs, so no cover key remains held.

## Voice examples

- “Use this bottle as a WASD joystick.”
- “Move this sticker up and down to scroll.”
- “Cover this object to press Space.”
- “Use this slider to control volume.”
- “Use this slider to control brightness.”

Start the overhead camera, show and briefly move the object, then click **Talk to map**. Cartesia Ink transcribes audio; ASI:One gets text and metadata, not camera frames. An optional text field uses the same planner for testing. The planner receives a strict JSON schema generated from registered compatible sources and targets, and the backend validates the returned plan again before activation. **STOP ALL OUTPUT** also cancels pending planning. **Undo AI mapping** restores the prior mapping if its object remains tracked.

## Cover buttons and stickers

Cover detection uses Google's local MediaPipe Hand Landmarker. It combines hand-hull overlap of the registered region with a change from the clear reference image. It requires approximately 180ms covered and 350ms clear to reset. An object disappearing without hand evidence does not fire. The target must remain stationary and away from frame edges; after a camera/target move, remap. A hand over the region is visual evidence, not guaranteed physical contact; unusual lighting, partial occlusion or removing an object under a hand can remain ambiguous.

If automatic detection misses a sticker, click **Register sticker / button area** and drag a tight region around it in the overhead feed. Registered regions join the normal object list and can become sliders or cover buttons. Textured stickers support optical-flow/SIFT tracking; a blank region cannot provide reliable moving identity. Registered tracks keep their IDs on feature-based recovery and are not forced lost for lacking a semantic detector label. Cover buttons use their fixed clear reference even while the underlying object is occluded.

Install optional model support with `.venv/bin/python -m pip install '.[gestures]'`, then `.venv/bin/python -m vision.cover --download`. The download command pins the official Google model version and verifies SHA-256. Model and camera frames stay local; frames are not saved. The current workspace already has the dependency/model installed. Sources: [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python), [Core Graphics scrolling](https://developer.apple.com/documentation/coregraphics/cgeventcreatescrollwheelevent), [DisplayServices behavior used by brightness](https://github.com/nriley/brightness).

## Validation

Fake adapters verify source/target independence, movement-only scrolling, bounded parameter changes, tracking loss, token ownership, stale input, cover dwell/reset, missing-object rejection and unknown-target rejection. HTTP tests cover registration and actual snapshot routing. Real native brightness and volume were each changed slightly, read back successfully, then restored. Actual MediaPipe inference initialized and returned zero hand coverage for a blank image. Real ASI requests selected brightness, volume, scrolling and cover-to-Space; an unregistered speaker EQ request returned unsupported. A physical hand-cover interaction still requires an operator test under the current camera/lighting.

Final automated validation: **248 Python tests passed, 2 skipped; all 14 JavaScript checks passed**. The live dashboard exposes all four registered targets and the C270 capture path remains approximately 30 updates/sec. Native actions remain disarmed until a mapping is activated.

Slider recovery retains enrolled object IDs for appearance-based re-entry for up to two minutes, including return through a different edge. It requires two consistent unambiguous detections; similar-looking items may remain unresolved. While missing, output pauses. Recovery rebases the parameter to its current value and the object's new location, preventing a brightness/volume jump.

Continuous slider sensitivity uses a gain of 3.0: moving across 10% of the camera width/height changes the parameter by about 30 percentage points. The maximum adjustment speed is 130 percentage points per second. Small-jitter filtering and normalized output bounds remain active.
