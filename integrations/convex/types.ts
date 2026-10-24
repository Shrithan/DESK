export interface SessionRecord {
  sessionId: string;
  createdAtMs: number;
  status: "idle" | "calibrating" | "tracking" | "ended";
}

export interface CameraRecord {
  sessionId: string;
  cameraId: string;
  connected: boolean;
  lastSeenMs: number | null;
}

export interface SelectedObjectRecord {
  sessionId: string;
  objectId: string;
  cameraId: string;
  pixel: { x: number; y: number };
  selectedAtMs: number;
}

export interface CalibrationSummary {
  sessionId: string;
  calibratedAtMs: number | null;
  reprojectionErrorPx: number | null;
  cameraCount: number;
}
