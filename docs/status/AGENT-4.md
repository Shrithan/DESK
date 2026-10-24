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

**Tests:** `cd frontend && npm test` — 14 passing (coords transform, pixel
mapping, contract validation, store + mock-world integration smoke test)

**Blockers:** None yet — no backend exists, so Live mode is untested against
a real `/ws/world` server. `shared/contracts/*.v1.schema.json` is my
interpretation of the provisional protocol in the milestone contract; Agent 3
should confirm/finalize it.

**Next:** wire a real Convex deployment if time allows; get a real backend
to test Live mode against; camera-preview images are currently SVG
placeholders — swap for Agent 1's actual preview endpoint once it exists.
