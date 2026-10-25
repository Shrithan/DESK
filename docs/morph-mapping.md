# Morph voice mapping

Cartesia Ink transcribes your command. ASI:One receives the transcript, actual tracked objects, target selection/motion context, current mapping and supported input/action catalog. It returns a declarative plan; the backend validates it before applying. Camera images never go to ASI:One and neither provider key enters the browser.

Add `ASI1_API_KEY=...` (or `ASI_ONE_API_KEY`) to the ignored root `.env`. Optional `ASI1_MODEL=asi1`. Credentials reload per request. Cartesia uses the existing `CARTESIA_API_KEY`. There is no keyword fallback masquerading as an AI planner; emergency stop remains deterministic.

Start the overhead webcam, briefly move the item, click **Talk to map**, then say what it should do:

- “Use this bottle as a WASD joystick.”
- “Move this sticker up and down to scroll.”
- “Cover this object to press Space.”
- “Use this slider to control volume.”
- “Use this slider to control brightness.”

Joysticks, X/Y sliders and stationary hand-cover buttons are reusable input sources. Their destinations come from the action registry. Rotation is excluded from new AI plans. Continuous parameters reuse the same normalized slider runtime; adding an executable parameter adapter does not require another slider implementation. Unknown app controls remain unsupported until an adapter exists.

The dashboard shows available targets, active mapping, undo, input cards and cover state. If detection misses a sticker, register its region once in the overhead view. Valid unambiguous plans activate automatically when the required permission and visible source are available. Hold a can upright to finish joystick calibration; keep cover targets stationary and uncovered initially. **STOP ALL OUTPUT** cancels planning and disarms native output. Tracking loss and stalled input stop actions. One native controller is active at a time. Session IDs are not persisted across restarts.

See [Desktop actions](desktop-actions.md) for supported destinations, provider/schema validation, adapters, native behavior, hand-model setup, physical limitations and test evidence.
