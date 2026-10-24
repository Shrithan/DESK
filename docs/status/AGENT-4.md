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
- **Game control**: object velocity → left/right/jump/duck gesture →
  real OS keystroke via a local proxy (`integrations/gamecontrol/`), so
  moving the tracked object can drive an actual focused game (team-agreed
  scope addition, not in the original milestone doc — flagging here so it's
  visible to the other 3 agents). OFF by default, two independent gates
  before anything real fires (UI arm + proxy env flag). Not in the written
  contract, so no shared-contract changes were needed — it only consumes
  `position_m` that's already flowing.

**Tests:** `cd frontend && npm test` — 23 passing (coords transform, pixel
mapping, contract validation, gesture detection thresholds/cooldown/priority,
store + mock-world integration smoke test)

**Blockers:** None yet — no backend exists, so Live mode is untested against
a real `/ws/world` server. `shared/contracts/*.v1.schema.json` is my
interpretation of the provisional protocol in the milestone contract; Agent 3
should confirm/finalize it.

**Next:** wire a real Convex deployment if time allows; get a real backend
to test Live mode against; camera-preview images are currently SVG
placeholders — swap for Agent 1's actual preview endpoint once it exists;
game-control gesture thresholds are tuned for a guess at real hand-swipe
speed and should get a pass with an actual tracked object once Agents 1-3
are live.
