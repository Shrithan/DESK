# Spoken object mapping → real W/A/S/D

## First run

1. Run `.venv/bin/python -m vision.live` and open http://localhost:8765. The Cartesia key stays in ignored `.env` as before.
2. **Joystick mode · overhead webcam only** is on by default. Choose the webcam and click **Start overhead webcam**. No iPhone or Continuity connection is needed for this mapping. Uncheck it to restore the two-camera spatial view.
3. Show the can clearly and move it briefly to acquire it. Press **Start talking** under the bear, allow microphone access, and say **“Map this can to a joystick.”** Pause after the sentence. The microphone restarts after each command and spoken reply. Say **“Stop listening”** or press **Stop listening** to close it. **Talk to map** remains available in **Workspace and camera setup** for one command at a time. Each clip is capped at ten seconds.
4. Cartesia Ink transcribes the actual microphone clip. A short explicit grammar resolves joystick mapping or stop commands. Cartesia Sonic confirms the result. One unique visible item is selected; among several, a unique recently moving item can be selected. Otherwise choose **Voice target** and repeat the command. No arbitrary target is guessed.
5. Keep the can upright for its neutral calibration. Use **Learn W** / **Learn D** to teach the tilted camera your directions.
6. Real output needs macOS Accessibility. Click **Request keyboard permission**; macOS identifies the responsible app. Enable that named app in System Settings → Privacy & Security → Accessibility, then retry **Arm real WASD**. The product only requests the standard prompt; it cannot grant permission itself. The responsible app can be Codex or a terminal, depending on how the server was launched. No keystroke injection is attempted without this permission.
7. Choose **Game · hold W/A/S/D** for held movement keys, or **Document · repeat letters** for repeated typing. Changing the mode disarms output; arm again. Click the local key-test box or focus your target app/document and lean the can.

A spoken mapping attempts to arm the mapped joystick if permission is already granted; otherwise the mapping is retained and the panel explains that real keys are off. **STOP ALL OUTPUT** releases immediately and closes hands-free listening. “Stop keyboard control” is also a voice command; it leaves hands-free listening on so another spoken command can follow. Esc stops output and hands-free listening when this dashboard has focus.

## Behavior and limits

Only lowercase w/a/s/d can be injected. Output is edge-triggered and diagonals are supported. Releases happen before new presses. No other key names, arbitrary text or desktop actions are accepted. No app/window is secretly targeted: events go to the focused app. Game mode posts a key-down until neutral/loss and then key-up. Document mode repeats held letters after 400 ms, at 10 Hz.

Input is disarmed on a missing heartbeat for 350 ms, server close or handled termination signals. The backend also checks that the chosen overhead object is still tracked with a frame received within 400 ms. A lost observation releases immediately; visual prediction/short holds do not sustain real keys. Recalibration, stopped cameras, removal of the joystick, changed target/mode, explicit stop and closing the dashboard release/disarm. Owners have independent opaque tokens and monotonic sequence numbers, so old or other-tab key updates cannot overwrite the current owner. A separate watchdog handles a lost browser connection.

Camera processing no longer intentionally stops when another tab/app is focused; frame progress uses video media time, not display callbacks. Keep the dashboard camera window visible/running when using another app. Browsers can still throttle or pause hidden/minimized camera pages; when that happens keys release and the panel requires re-arming. This first implementation does not claim native background capture or guaranteed full-screen-game compatibility.

The can control is relative lean/translation around a saved neutral projection, not measured physical 3D tilt. Keep the base fixed for joystick use and recalibrate after moving the camera or base. Exact application compatibility must be verified in the target app after macOS permission is granted.

## Privacy and implementation

Only microphone clips from a user-started Talk or hands-free session go through the local server to Cartesia's documented `POST /stt` endpoint (`ink-whisper`, API `2026-08-14`). Browser audio is encoded as bounded mono 16 kHz PCM WAV. Quiet ten-second windows are discarded locally. Microphone access stops during transcription and spoken replies, then resumes while hands-free remains enabled. No audio, transcript or camera image is written to disk by this feature. Camera frames do not go to Cartesia. Transcripts appear locally in the dashboard and are interpreted by `vision/commands.py`; the grammar cannot request shell commands or arbitrary keyboard actions. Replies use the existing server-side Sonic speech adapter. Clips and responses stay in memory; provider retention is governed by the provider account policy.

Hands-free listening requires the dashboard to stay open and the browser to keep its microphone permission active. Background tab throttling can pause the camera or microphone; the existing tracking watchdog releases keyboard output if camera input stalls. Use the visible stop control to end a session before leaving the dashboard.

Native output uses macOS CoreGraphics keyboard events, gated by Accessibility and limited to four fixed key codes. No additional keyboard injection package, system-wide keyboard listener or Input Monitoring permission is required. The optional older `backend/tilt_keys`/standalone controller remains separate.

Cartesia API reference: https://docs.cartesia.ai/api-reference/stt/transcribe and https://docs.cartesia.ai/api-reference/tts/bytes.

## Verified

- Real provider round trip: Cartesia Sonic generated “Map this can to a joystick.”; Ink returned that transcript; the parser returned `map_joystick`, label `can`.
- Native CoreGraphics entry points loaded successfully. The operator enabled Accessibility for ChatGPT; restarting the server picked up the change. The operator then clicked **Test real WASD here** and confirmed the test box received `wasd`. Automated tests still use fake output.
- Tests use fake keyboard output for held/released keys, typing repeat, opposite-key rejection, ownership/sequence, watchdog, tracking loss, HTTP origin rejection and cleanup.
- Browser helpers cover microphone WAV encoding, command ambiguity/selection and processing advancing video frames independently of document visibility.
- Operator confirmed the physical microphone command mapped the can. The live dashboard showed transcript “Map this can to a joystick.” and created “Voice joystick · cup #3” (the detector classified that can as cup). Native key delivery to the dashboard test field is confirmed; game-specific behavior has not been tested.
