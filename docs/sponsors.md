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

## Cartesia — **REAL, verified end-to-end with a live key**

Both directions confirmed working against the actual API (2026-10-24), not
guessed — see `integrations/cartesia/server.mjs`, a Node proxy (needs the
`ws` package; `npm install` in that directory) that keeps the key
server-side for both:

- **TTS** (`POST /speak`): `https://api.cartesia.ai/tts/bytes`,
  `Authorization: Bearer <key>` + `Cartesia-Version: 2026-08-14`,
  `model_id: "sonic-3"`, a voice UUID, `output_format`. Verified with a real
  key — returns a playable WAV. Used for status narration ("Object lost",
  "Tracking started", etc.), debounced per event (4s), never fires on every
  pose update.
- **STT** (`WS /stt`): relays to `wss://api.cartesia.ai/stt/websocket`
  (`model=ink-whisper`), `X-API-Key` header, binary PCM16 16kHz chunks in,
  `finalize`/`close` text commands, `transcript`/`flush_done`/`done`/`error`
  JSON back. Verified with a real round-trip (TTS output fed back through
  STT, got a correct transcript). Drives the **voice-assigned object roles**
  feature — see `frontend/README.md` — not a canned "Track this object"
  command, but free speech matched against a small keyword list
  (`frontend/src/lib/roleProfiles.ts`), explicitly not claimed as full NLU.

Without `CARTESIA_API_KEY` set on the proxy, both fall back to mock
(`{mocked:true}` / STT connection that reports an error instead of hanging)
so the UI still runs end-to-end with no key.

`integrations/voicecontrol/server.mjs` is the actual keystroke injector that
voice-assigned roles drive (osascript/System Events, same mechanism as
Agent 3's pynput approach but independently implemented) — not a Cartesia
API itself, just what sits downstream of its STT output. Mock unless
`VOICECONTROL_ALLOW_INJECT=1`.

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
