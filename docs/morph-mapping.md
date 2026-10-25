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

## Voice module setup

The main screen now uses Cartesia speech and the ASI:One planner as a setup agent.
The planner first resolves a module from `catalog.modules`, then chooses that
module's required physical source and target. Ready plans carry `module` and
`setup_action`; the server validates game bindings against the existing profiles.
The browser adapter in `vision/web/module-agent.js` calls `mapGameModule`,
`activateControlEntry`, `activateDJPlan` and `djGuideNext`. Flight anchors, Subway
flicks, slider direction, button sensing, watchdogs, MIDI feedback and pickup still
run through their existing implementations.

Start the overhead camera and move objects briefly. Click **Talk to map**:

- “Use this can for the flight simulator.”
- “Use the bottle to play Subway.”
- “Make this object a brightness slider.”
- “Cover the cup to press Space.”
- “Use this slider for Deck A volume.”

When there are several possible objects, answer the agent's question using an
object label or displayed number. The last eight setup turns provide follow-up
context. One physical assignment is made per turn; other general controls and DJ
faders can remain mapped. Same-source general reassignment replaces that source's
previous general mapping. Manual controls remain in **Developer controls**.

DJ travel is still measured: move to the desired 0% position and say “save
minimum”, then move to 100% and say “save maximum”, then say “enable DJ controls”.
The same endpoint-separation checks and real Mixxx feedback/pickup apply. The
agent cannot invent travel endpoints or enable a disconnected mixer. External
Mixxx setup and macOS Accessibility permission are still required where relevant.

**Keep listening for setup replies** allows another spoken turn after the agent's
reply finishes. The microphone starts only after clicking Talk; **End voice
setup**, Escape or **STOP ALL OUTPUT** ends the conversation. A silent listening
window ends after ten seconds. Typed commands remain available.

**Reset module** stops output and clears general/DJ mappings, game anchors,
registered buttons/regions, tracks, pending detection generations, map references
and setup conversation. Connected camera streams resume observing from scratch,
so the same physical objects can control a different interface. It does not reset
hardware calibration or change the destination app's current values.

Verification: `tests/test_module_agent.cjs`, `tests/test_module_reset.py` and
`tests/test_morph.py`, plus the existing game, control and DJ regression suites.
Real speech, camera identification and hardware output require a live check.

Completed assignments end voice listening; automatic follow-ups continue only for
clarification and remaining DJ calibration steps. App-launch buttons retain their
assignment across browser heartbeat stalls. Output pauses during the gap and
requires a fresh uncovered view before another cover can launch the app. Stop and
Reset still explicitly end activation.
