# Convex schema (design, not yet deployed)

Convex owns low-rate, durable/reactive state only. High-rate `world_state`
(10-30Hz pose) stays on the local `/ws/world` socket — never routed through
Convex.

```ts
// convex/schema.ts (sketch — verify exact `defineSchema`/`defineTable` and
// validator syntax against current Convex docs before deploying; do not
// trust this file's syntax as final)
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  sessions: defineTable({
    sessionId: v.string(),
    status: v.union(v.literal("idle"), v.literal("calibrating"), v.literal("tracking"), v.literal("ended")),
    createdAtMs: v.number(),
  }).index("by_sessionId", ["sessionId"]),

  cameras: defineTable({
    sessionId: v.string(),
    cameraId: v.string(),
    connected: v.boolean(),
    lastSeenMs: v.union(v.number(), v.null()),
  }).index("by_session", ["sessionId"]),

  selectedObjects: defineTable({
    sessionId: v.string(),
    objectId: v.string(),
    cameraId: v.string(),
    pixelX: v.number(),
    pixelY: v.number(),
    selectedAtMs: v.number(),
  }).index("by_session", ["sessionId"]),

  calibrationSummaries: defineTable({
    sessionId: v.string(),
    calibratedAtMs: v.union(v.number(), v.null()),
    reprojectionErrorPx: v.union(v.number(), v.null()),
    cameraCount: v.number(),
  }).index("by_session", ["sessionId"]),

  // Optional, capped at 1-2Hz — a coarse history, not the render feed.
  poseSnapshots: defineTable({
    sessionId: v.string(),
    objectId: v.string(),
    x: v.number(),
    y: v.number(),
    z: v.number(),
    timestampMs: v.number(),
  }).index("by_session_object", ["sessionId", "objectId"]),
});
```

Reactive queries (`sessions.get`, `cameras.listBySession`, etc.) back the
session-status and camera-health UI. `ConvexSessionAdapter.ts` wraps these
behind `enabled`/`disabled` modes so the frontend runs with zero Convex
config.
