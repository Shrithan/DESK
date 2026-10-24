# Shared contracts

Versioned schemas for cross-agent messages. **Provisional — Agent 3 finalizes
the coordinate/protocol contract.** Do not silently change units, axis
directions, IDs, or field names; propose changes in a PR and flag them to
every agent before merging.

- `world-state.v1.schema.json` — `/ws/world` WebSocket payload (backend → frontend)
- `selection-command.v1.schema.json` — object-selection command (frontend → backend)
- `types.ts` — TypeScript mirror of both schemas, hand-maintained in lockstep

## Coordinate frame

World: right-handed, meters. +X right, +Y away from viewer on tabletop, +Z up.
Origin is a fixed calibration reference on the table, not a camera origin.

Three.js is Y-up, so the frontend renderer maps `world(x, y, z) -> three(x, z, -y)`.
This conversion lives in `frontend/src/lib/coords.ts` and is unit-tested — never
duplicate it ad hoc elsewhere.

## Timestamps

Unix epoch milliseconds (`timestamp_ms`), plus a monotonic capture timestamp
for synchronization where available.
