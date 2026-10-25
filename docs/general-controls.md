# General controls module

The **Sliders & buttons** panel provides manual mappings without a voice provider or AI planner.

1. Start the overhead camera and move the physical object briefly to acquire its track.
2. Choose Horizontal slider, Vertical slider, or Button · cover / uncover.
3. Choose an available action. Sliders support current output volume, built-in display brightness, and scrolling. Buttons support a single keyboard key or opening an installed app. Unavailable adapters are excluded.
4. Optionally name the control and reverse the slider direction. Click **Save mapping**, then **Activate** on its card.

Right/up increases continuous parameters by default. Activation anchors relative travel to the current system value to avoid an immediate jump. Scrolling follows measured motion; holding still stops scrolling. Buttons learn the uncovered object and fire immediately on confirmed cover, then require uncovering before another press. A button requires the existing hand-detector dependency.

Multiple mappings can be saved in the current page session, with independent native action leases so all activated mappings run simultaneously. Independent DJ sliders remain managed by the DJ module. Saved cards are not persisted across reloads. Activated objects keep a persistent enrolled identity across frame exits; appearance-based re-identification restores their original ID when the evidence is unambiguous. Select the new object and click **Use selected object** on its card, then activate again.

**Stop controls** releases/disarms native output. Tracking freshness and a 350 ms output lease retain the existing backend protections. Keyboard and scrolling need macOS Accessibility. Volume, brightness and app triggers may operate while this panel is visible; keyboard/scroll output requires another app focused or the existing Local key test / Scroll test area. App buttons open installed apps only; no arbitrary command execution is supported.

`vision/web/controls.js` builds declarative mappings against `/api/morph/status`'s current action catalog. The existing validated `/api/actions` backend executes them; no Subway detector code is changed.

Validation: `node tests/test_controls_module.cjs` and `.venv/bin/python -m pytest -q tests/test_action_runtime.py tests/test_app_actions.py tests/test_keyboard.py`.

Tracking loss pauses native output without discarding activation while dashboard heartbeats continue. Reacquired sliders re-anchor to the current parameter value, preventing a jump. Camera snapshot absence does not impose a two-second re-arm requirement. Stalled dashboard heartbeats still disarm after 350 ms. Activated general-control identities bypass the normal 120-second re-entry expiry. Strong appearance recovery handles disk/cup/can label changes; plausible ambiguous matches are reserved instead of creating duplicate tracks. Identical lookalikes still require explicit selection when visual evidence cannot distinguish them.

Concurrent controls use /api/controls/arm, update and stop with independent tokens. Stopping/removing one mapping leaves others active. Stop controls and STOP ALL OUTPUT stop the group. Each cover button senses the central 60% width and height of its original bounds. A press needs hand overlap or a separate detected occluding object plus visible appearance change; lost tracking alone never fires. Button rectangles are rendered on the camera. Independent action leases expire on missing heartbeats.
