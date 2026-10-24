# Sponsor integration status

Honest accounting of what's real vs. mocked, per the milestone-1 contract's
instruction not to claim sponsor-track compliance without verifying actual
requirements and using the actual service.

## Convex — **MOCKED**

- `integrations/convex/ConvexSessionAdapter.ts` exposes `MockConvexSessionAdapter`
  (in-memory, default) and `LiveConvexSessionAdapter` (throws — scaffold only).
- `integrations/convex/schema.md` sketches the intended schema (sessions,
  cameras, selected objects, calibration summaries, optional low-rate pose
  snapshots) but **has not been deployed or verified against current Convex
  docs/API**.
- To go live: verify `convex/server` + `convex/react` current syntax, run
  `npx convex dev`, implement each `LiveConvexSessionAdapter` method, set
  `VITE_CONVEX_URL`.

## Cartesia — **MOCKED (text-only), live path scaffolded but unverified**

- `integrations/cartesia/server.mjs` is a dependency-free Node proxy so the
  API key never reaches the browser. Without `CARTESIA_API_KEY` set it
  echoes `{mocked: true, text}` and the frontend shows text-only narration.
- The "live" branch in `server.mjs` calls an **unverified** Cartesia TTS
  endpoint/shape — explicitly marked with a TODO to confirm against
  https://docs.cartesia.ai before it's claimed as a working integration. Any
  failure there falls back to mock rather than breaking the demo.
- Narration is debounced per event (4s) and never fires on every pose
  update — only on tracking-state transitions.

## Fetch.ai — **MOCKED (seam only)**

- `integrations/fetchai/MorphAgentGateway.ts` defines the agreed interface
  (`getWorldState`, `requestInterfaceConfig`, `getAgentStatus`,
  `applyInterfaceConfig`) with an in-memory mock implementation.
- No Agentverse/uAgents/ASI:One registration, discoverability, or protocol
  work has been done. This is explicitly **not** sponsor-track-eligible yet;
  a dedicated Morph agent owner should take this over next milestone. A
  generic LLM call would not satisfy sponsor eligibility either — this
  gateway makes no such claim.
- Never blocks the render/tracking loop — all calls are async and optional.

## Why mock-first

All three were mocked for milestone 1 per explicit instruction: build a
runnable demo immediately, add real integrations as time permits, and never
fabricate sponsor-track compliance.
