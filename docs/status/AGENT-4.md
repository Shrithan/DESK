# Agent 4 — status log

## H1 — 2026-10-24

**Branch:** `agent/digital-twin`
**Commit:** (see git log after push)

**Runnable:**
```bash
cd frontend
npm install
npm run dev
```
Opens at http://localhost:5173 in Mock mode — two virtual objects moving in
3D immediately, no backend or cameras required.

**Working features:**
- Dark Blender-style R3F viewport: grid, axes, orbit/pan/zoom, gizmo
- World(Z-up) → Three(Y-up) coordinate transform, unit-tested
- Mock trajectory generator (2 objects, one with a scripted lost→predicted→
  tracked dropout) and a live/mock toggle
- `/ws/world` client with reconnect, latency estimate, structural validation
  against `shared/contracts/world-state.v1.schema.json` (malformed messages
  are dropped, never rendered as fake "tracked" state)
- Object list, FPS, connection status, trail toggle, tracking-state badges
  (tracked/predicted/lost)
- Camera-preview click-to-select with correct native-pixel mapping
  (letterbox-aware), unit-tested
- Convex/Cartesia/Fetch.ai integration seams — all mock-mode by default, see
  `docs/sponsors.md`
- Visual pass: header bar, design-token theming, contact shadows, error
  boundary around the 3D canvas (a WebGL init failure was previously taking
  down the whole app, HUD included — found by actually rendering it, not
  just build/tests)
- **Held-keys HUD**: subscribes to Agent 3's `backend/tilt_keys` `/ws/keys`
  feed (`key_state` v1.0.0) and lights up W/A/S/D in sync with real
  keystrokes their backend sends via pynput. Visualization only — this
  frontend does not inject keystrokes. (I initially built my own parallel
  velocity→arrow-keys injector before discovering Agent 3 had already
  shipped a much more complete tilt-based version straight to `main` with
  calibration, filtering, and safety handling; dropped mine in favor of
  consuming theirs — see git history on this branch for both halves of
  that.)

**Tests:** `cd frontend && npm test` — 38 passing (coords transform, pixel
mapping, contract validation, key_state parsing, role-matching, role
controller hysteresis/center-calibration, store + mock-world integration
smoke test)

## Update — Cartesia real integration + voice-assigned object roles

**Cartesia is now REAL, not mocked**, verified against current docs (not
guessed) and round-trip tested with a live key:
- TTS (`POST /speak`): confirmed working, returns real audio.
- STT (`WS /stt`): confirmed working — fed a TTS-generated clip back through
  it and got a correct transcript back.
- `integrations/cartesia/` needs `npm install` now (added the `ws` package
  for the STT websocket relay — no longer zero-dependency).

**New feature — voice-assigned object roles**: select a tracked object, hold
the mic button, say e.g. "this is a steering wheel." Cartesia transcribes it,
a keyword match (`frontend/src/lib/roleProfiles.ts` — explicitly not a
language model, documented as such in the UI) picks a role, the object's
current position becomes its calibrated center, and from then on its live
position relative to that center holds real keys (steering wheel: left/right
→ A/D, gas pedal: away → W, brake: toward → S, jump: up → Space) via
`integrations/voicecontrol/server.mjs` (osascript, same mock/live-gated
pattern as everything else). Independent of Agent 3's tilt_keys — drives off
position (which Agent 4 already has via world_state), not tilt angle.

**Bug found and fixed during manual verification** (not caught by unit
tests): a fast press-and-release of push-to-talk could race the STT
websocket's handshake — if `stop()` fired before the socket finished
connecting, `finalize` never got sent and the UI stuck on "Transcribing…"
forever with no recovery. Fixed with a pending-finalize flag plus a 6s
client-side timeout that always returns the UI to idle with an error.

**Not verified**: real human speech through an actual microphone — no audio
hardware in my environment, and the browser automation I used can only
instant-click (not hold-and-speak). STT itself is verified (see above); the
browser-side mic capture/downsampling path needs a real human test.

**Blockers:** None yet — no backend exists, so Live mode is untested against
a real `/ws/world` server. `shared/contracts/*.v1.schema.json` is my
interpretation of the provisional protocol in the milestone contract; Agent 3
should confirm/finalize it.

**Next:** wire a real Convex deployment; get a real backend to test Live
mode against; camera-preview images are currently SVG placeholders — swap
for Agent 1's actual preview endpoint once it exists; someone needs to
actually speak into a mic and confirm the full voice-role flow end to end.
