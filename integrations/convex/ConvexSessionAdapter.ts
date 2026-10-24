import type { CalibrationSummary, CameraRecord, SelectedObjectRecord, SessionRecord } from "./types";

export interface ConvexSessionAdapter {
  readonly mode: "mock" | "live";
  createSession(sessionId: string): Promise<SessionRecord>;
  upsertCamera(record: CameraRecord): Promise<void>;
  recordSelection(record: SelectedObjectRecord): Promise<void>;
  getCalibrationSummary(sessionId: string): Promise<CalibrationSummary | null>;
}

/** In-memory adapter — the default. No network calls, no credentials needed. */
export class MockConvexSessionAdapter implements ConvexSessionAdapter {
  readonly mode = "mock" as const;
  private sessions = new Map<string, SessionRecord>();
  private cameras = new Map<string, CameraRecord>();
  private calibrations = new Map<string, CalibrationSummary>();

  async createSession(sessionId: string): Promise<SessionRecord> {
    const record: SessionRecord = { sessionId, createdAtMs: Date.now(), status: "idle" };
    this.sessions.set(sessionId, record);
    return record;
  }

  async upsertCamera(record: CameraRecord): Promise<void> {
    this.cameras.set(`${record.sessionId}:${record.cameraId}`, record);
  }

  async recordSelection(record: SelectedObjectRecord): Promise<void> {
    console.info("[ConvexSessionAdapter:mock] recordSelection", record);
  }

  async getCalibrationSummary(sessionId: string): Promise<CalibrationSummary | null> {
    return this.calibrations.get(sessionId) ?? null;
  }
}

/**
 * Live adapter — NOT implemented yet. Convex's client API must be verified
 * against current docs before writing real calls; a guess here would risk
 * calling methods that don't exist. Throws until that verification happens
 * and `VITE_CONVEX_URL` is actually set.
 */
export class LiveConvexSessionAdapter implements ConvexSessionAdapter {
  readonly mode = "live" as const;
  private convexUrl: string;

  constructor(convexUrl: string) {
    this.convexUrl = convexUrl;
  }

  private notImplemented(): never {
    throw new Error(
      `LiveConvexSessionAdapter is a scaffold (configured url: ${this.convexUrl}). Verify the ` +
        "current convex/react client API, implement each method against convex/schema.md, then remove this guard.",
    );
  }

  async createSession(): Promise<SessionRecord> {
    this.notImplemented();
  }
  async upsertCamera(): Promise<void> {
    this.notImplemented();
  }
  async recordSelection(): Promise<void> {
    this.notImplemented();
  }
  async getCalibrationSummary(): Promise<CalibrationSummary | null> {
    this.notImplemented();
  }
}

export function createConvexSessionAdapter(): ConvexSessionAdapter {
  const url = import.meta.env.VITE_CONVEX_URL as string | undefined;
  if (url) return new LiveConvexSessionAdapter(url);
  return new MockConvexSessionAdapter();
}
