# Phantom — 3D Digital Twin Frontend (Agent 4)

React + TypeScript + Vite + React Three Fiber. Dark Blender-style viewport
rendering objects streamed from `/ws/world`, plus a self-contained mock mode
so the demo runs with zero cameras or backend.

## Quick start

```bash
npm install
cp .env.example .env.local   # optional — defaults work for mock mode
npm run dev
```

Open http://localhost:5173 — it starts in **Mock** mode by default, so two
virtual objects immediately move in 3D. Flip to **Live** in the top-left
panel once a real backend is serving `/ws/world`.

## Demo sequence for judges

1. App opens in Mock mode — two spheres orbiting/oscillating, confirms 3D
   rendering, coordinate mapping (watch the height/Z axis), and HUD (FPS,
   object list, tracking-state badges) all work with no hardware.
2. Around the 10-11s mark in the mock loop, `obj_2` goes **lost** then
   **predicted** then **tracked** again — watch its badge and trail color
   change, and the narration banner announce "Object lost" / "Object
   recovered" (debounced, never spammy).
3. Click a spot on either camera tile on the right — console logs the exact
   native-pixel `select_object` command and the HUD shows "Last selection".
4. Flip to Live mode with a real backend running to show the same UI driven
   by real camera data.

## Game control (object movement → real keyboard input)

The actual tilt→keyboard mapping and OS keystroke injection lives in Agent
3's `backend/tilt_keys/` (pynput-based, with calibration/filtering/safety —
see `docs/tilt_to_keys.md` at the repo root). This frontend does **not**
inject keystrokes itself; it only visualizes the held-key state by
subscribing to that backend's `/ws/keys` feed, so you can watch W/A/S/D
light up in the HUD in sync with whatever game is actually receiving the
real presses.

Run `python -m backend.tilt_keys.run --input ws --backend pynput,websocket`
(from the repo root, see that module's own setup instructions) and the
"Held Keys" panel here will light up live.

## Voice-assigned object roles (Cartesia STT, real)

Select a tracked object in the Objects list, then hold the mic button in
"Voice Roles" and say e.g. *"this is a steering wheel"*. On release, Cartesia
transcribes it, a keyword match (not a language model — see the panel's own
caption) picks a role, and that object's **current position becomes its
calibrated center**. From then on, moving it relative to that center holds
real keys: steering wheel = left/right → A/D, gas pedal = away from you → W,
brake = toward you → S, jump button = lift up → Space. This uses the same
position stream already flowing through `/ws/world` — no new camera/backend
work needed.

Requires both proxies running with real credentials:

```bash
CARTESIA_API_KEY=sk_car_... npm run proxy:cartesia      # TTS (/speak) + STT relay (/stt)
VOICECONTROL_ALLOW_INJECT=1 npm run proxy:voicecontrol  # real key-down/key-up via osascript
```

Without `VOICECONTROL_ALLOW_INJECT=1`, role assignment and the HUD state
still work end-to-end — it just logs what key would be held instead of
actually holding it. macOS will prompt for Accessibility permission on the
first real key-down.

## Game control (object movement → real keyboard input)

Separately, Agent 3's `backend/tilt_keys/` (pynput-based, with
calibration/filtering/safety — see `docs/tilt_to_keys.md` at the repo root)
does its own fixed tilt→WASD mapping. This frontend doesn't inject for that
path either; it only visualizes the held-key state by subscribing to that
backend's `/ws/keys` feed.

Run `python -m backend.tilt_keys.run --input ws --backend pynput,websocket`
(from the repo root) and the "Held Keys" panel here will light up live.

## Scripts

- `npm run dev` — Vite dev server
- `npm run build` — typecheck + production build
- `npm test` — Vitest unit + integration-smoke tests
- `npm run proxy:cartesia` — Cartesia proxy (`../integrations/cartesia/server.mjs`)
  on :8787 — TTS (`POST /speak`) + STT relay (`WS /stt`). Mock unless
  `CARTESIA_API_KEY` is set.
- `npm run proxy:voicecontrol` — key-injection proxy
  (`../integrations/voicecontrol/server.mjs`) on :8789. Mock unless
  `VOICECONTROL_ALLOW_INJECT=1` (macOS only).

## What's real vs. mocked

See `../docs/sponsors.md`.
