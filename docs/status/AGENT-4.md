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

**Tests:** `cd frontend && npm test` — 23 passing (coords transform, pixel
mapping, contract validation, key_state parsing, store + mock-world
integration smoke test)

**Blockers:** None yet — no backend exists, so Live mode is untested against
a real `/ws/world` server. `shared/contracts/*.v1.schema.json` is my
interpretation of the provisional protocol in the milestone contract; Agent 3
should confirm/finalize it.

**Next:** wire a real Convex deployment if time allows; get a real backend
to test Live mode against; camera-preview images are currently SVG
placeholders — swap for Agent 1's actual preview endpoint once it exists.
