# Detected-object button inputs

Run the camera app at http://localhost:8765. Show and briefly move an object under the overhead camera so its detected card appears. Choose **Use as button** on that card, just as you choose a slider. Existing sliders/joysticks can also be changed to buttons. Alternatively select the detected object in **Overhead input object**, choose **Button · cover for 1**, and click **Use as input**.

No drawn region, key choice, Cartesia request or Accessibility permission is required for the binary preview. The server derives the initial cover target from the detected object's ID and bounding box. Leave it uncovered briefly to learn the clear appearance. The card displays a large live **0 / 1**:

- **0:** uncovered, missing, stale, or not yet ready.
- **1:** hand-confirmed covering, held for the duration of coverage.
- Uncovering clears the binary value; a 350 ms clear interval readies the next press, preventing repeated counts during one cover.

The same object ID remains attached while covered. When visible movement is tracked, its cover anchor follows the detected object and learns its new clear location. During occlusion, the last known clear location is retained. Appearance change without a detected hand does not produce 1. Inputs pause to 0 if the camera is stale or stopped. A camera-resolution change requires remapping.

These are **input values only**, with no native keyboard output. Up to eight button inputs can be monitored independently. Press counts are additional diagnostics; they are not the sustained binary value. Adding a preview button stops previous native controls and uses only the overhead camera. Existing sliders and joystick behavior is otherwise preserved.

Implementation: `vision/button_inputs.py` reuses the cover state machine and hand model; `/api/buttons/add` maps an already detected object and `/api/buttons/update` returns per-object states. `vision/web/object-buttons.js` updates the cards. The old fixed-region registration API remains for compatibility but its manual-drawing controls are hidden from the default flow.

Validation covers sustained 1 during hand occlusion, immediate release to 0, no press on disappearance alone, stale-frame reset, visible object movement, uncovered enrollment, and browser updates that retain the object ID without invoking native-action endpoints. Physical hand/object behavior still needs testing under the user's actual camera view and lighting.

## Voice-mapped tasks

With the object visible and uncovered, click **Talk to map** and say “When I cover this button, open Calculator.” Cartesia Ink transcribes; Fetch.ai ASI:One chooses a schema-validated mapping from the installed action catalog. A unique object already assigned as a button is supplied as the selected source for “this/the/my button.” If several possible buttons or an unspecified app remain, the agent asks for clarification.

The registry discovers up to 256 installed app bundles from `/System/Applications`, `/Applications` and `~/Applications` (including subfolders, excluding nested helper bundles). Each becomes an available cover-trigger action; app names are included in the ASI:One catalog. The agent cannot supply commands or paths. The launch adapter uses only a discovered, revalidated app path via `/usr/bin/open -a`, with no shell interpolation. Opening an app is supported; operating arbitrary workflows inside that app is not automatically supported. Tasks beyond registered actions return unsupported/clarification rather than invented automation.

Covering the detected object runs its mapped task once. Holding does not repeat; uncover to reset. The native-action card retains the 0/1 readout. Unlike native key events, opening an app does not require Accessibility permission or switching away from the dashboard. Existing stale-input/camera and stop controls still disarm execution. Only one native task mapping is active at a time; binary previews may still be monitored separately.

Enable **Voice feedback** to hear the validated agent explanation through Cartesia using Daniel by default (override with `CARTESIA_VOICE_ID`). `/api/voice/reply` accepts only an opaque ID for a recent server-generated plan message, never client-supplied speech text. Cartesia and ASI keys remain local.

Real-provider verification used generated speech “When I cover this button, open Calculator,” sample detected-object metadata and the actual installed-app registry. Cartesia transcription worked and ASI:One returned `cover_button` with `press:open` targeting the discovered Calculator bundle. Tests verified once-per-cover execution with a fake launcher, safe app-path arguments, changed-bundle rejection, schema grouping, assigned-object selection and restricted spoken replies. No actual app was launched during these automated tests; physical camera/voice activation remains the user's test.

### Missing registration is not an uncovered measurement

If a backend restart loses a button registration, the API returns its ID in `missing_ids` and the card displays **— / RECONNECT BUTTON**, rather than falsely displaying 0. If the original detected ID remains visible, the browser retries enrollment while the object is uncovered. Otherwise **Reconnect / relearn object** binds the explicitly selected current object (or the sole visible candidate after a user click). Native tasks are not automatically re-armed.

Polling one page's requested IDs no longer deletes another page's registrations. Removal is explicit; unused registrations expire after 60 seconds. This fixes a separate stuck-at-zero failure where a stale page kept polling a registration that no longer existed, so hand detection was never reached.

### Camera-lock contention

A real-camera cover test reached 97% hand coverage and produced value 1. It also exposed intermittent snapshot failures: the camera tracking lock could be busy for over the 30 ms snapshot timeout, which incorrectly sent the button back to `missing` while still covered. The action snapshot reader now reuses its most recent coherent per-object snapshot during that short lock wait. Original frame IDs and timestamps are preserved, repeated frames do not advance the detector or fire another event, and snapshots older than 350 ms still pause input. The cache is bounded to 16 objects and never writes camera frames to disk.
