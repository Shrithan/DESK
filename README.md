# Phantom — Markerless 3D Object Tracking

Four independent agents, one shared repo. See each agent's branch and
`docs/status/AGENT-N.md` for checkpoint updates.

## Layout

- `backend/` — camera capture, calibration, segmentation/tracking, multiview geometry, `/ws/world` server (Agents 1-3)
- `frontend/` — React + Three.js 3D viewport, object selection UI, mock demo mode (Agent 4)
- `integrations/` — Convex, Cartesia, Fetch.ai adapters (Agent 4, seams only initially)
- `convex/` — Convex schema/functions for session & calibration state (Agent 4)
- `shared/contracts/` — versioned JSON schemas for `world_state` and selection commands; **do not edit without opening a PR and flagging it to other agents**
- `docs/status/AGENT-N.md` — per-agent checkpoint log (H1/H3/H5/H8/H10)
- `docs/sponsors.md` — honest mock-vs-real status for each sponsor integration

## Branches

One branch per agent, e.g. `agent/digital-twin` (Agent 4). Draft PRs into `main`; do not merge another agent's branch yourself.
