# Bear voice studio

The root dashboard shows only the California bear and one text box. The supplied sticker image is served locally from `vision/web/cal-bear.webp`. Click the bear to start or stop listening. Type a command and press Enter to use the text box. Its mouth opening follows the actual Cartesia audio amplitude during speech; Cartesia Sonic produces the voice audio, and Cartesia Ink transcribes microphone commands. Camera and detailed control elements remain offscreen for the command handlers.

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

Camera capture, object tracking, macOS Accessibility permission, and application focus remain prerequisites for the corresponding actions. Browser background throttling can pause video or microphone processing; the existing output watchdog releases keys when camera frames stop. The interface reports missing credentials rather than pretending that speech is active.
