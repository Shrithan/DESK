# Bear voice studio

The root dashboard shows a close-up cuboid 3D bear and one text box on a pastel cyan background. `vision/web/bear-scene.js` builds the chubby head from overlapping stepped volumes: narrow forehead, broad cheeks, and tapered jaw, with tiny rectangular eyes and a lighter muzzle. It also builds broad navy Berkeley sweatshirt shoulders, a gold-trimmed crewneck, and a stepped navy cap. A locally drawn gold “Cal” script texture stays attached to the cap. The straight-on, eye-level orthographic camera frames the character like the supplied headshot: comfortable space above the cap, centered face, short visible neck, shoulders widening toward the lower corners, and upper chest cropped at the bottom. The photo is only a framing reference and is not stored in the app. The head turns toward the pointer or a touch position on a neck pivot while the shoulders follow slightly. Reduced-motion mode removes idle breathing and blinks and uses immediate, smaller head movement. Click the bear to start or stop listening. Type a command and press Enter to use the text box. A cuboid mouth opens with the decoded Cartesia audio waveform and closes during pauses. Cartesia Sonic produces the voice audio, and Cartesia Ink transcribes microphone commands. Camera and detailed control elements remain offscreen for the command handlers.

## Configure and run

Add `CARTESIA_API_KEY=...` to the ignored `.env` in this checkout (not the browser or a committed file). For open-ended object-to-app mappings, also add `ASI1_API_KEY=...`. Start with `.venv/bin/python -m vision.live`; if the model has not been prepared, use `--detector motion` for moving-region tracking. Open the printed localhost URL, click the bear, and grant browser microphone permission. Say **Stop listening**, click the bear again, or press Escape while the dashboard is focused to end capture. The camera needs separate browser permission when first started.

## Voice commands

Cartesia transcribes every spoken request. The text box sends typed requests through the same command path. Common control commands use an explicit local command list and call the existing handlers. Examples:

- “Start the overhead camera”; “stop cameras”; “refresh cameras”; “overhead only”; “two camera mode.”
- “Reset zoom”; “lock side exposure”; “auto exposure”; “reverse X direction”; “turn off prediction.”
- “Make disk number one a joystick”; “make cup two a slider”; “make the can a button.” Name the visible object's label or number if more than one candidate exists.
- “Calibrate upright”; “learn W”; “learn D”; “center disk one”; “set slider two to 100 percent here.”
- “Arm mapped keys”; “stop keyboard”; “game mode”; “document mode”; “request keyboard permission”; “stop all output.”
- “Reset all tracks”; “zero workspace”; “undo mapping”; “open workspace”; “test voice.”

Requests such as “When I cover this bottle, open Calculator” still use the validated ASI:One planner after Cartesia transcription. The bear speaks the local action result through Cartesia Sonic. ASI:One replies use the existing Cartesia reply path. The microphone closes while transcribing or speaking so the bear does not transcribe its own voice. A quiet ten-second window is discarded locally.

If a request needs a specific visible object or the planner needs a mapping detail, the bear asks a follow-up aloud and puts the question in the text box placeholder. A short answer such as “disk number two” or “right increases it” completes the original request. Say or type “cancel” to discard it.

Camera capture, object tracking, macOS Accessibility permission, and application focus remain prerequisites for the corresponding actions. Browser background throttling can pause video or microphone processing; the existing output watchdog releases keys when camera frames stop. The interface reports missing credentials rather than pretending that speech is active.
