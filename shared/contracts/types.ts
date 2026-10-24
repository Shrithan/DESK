export type TrackingState = "tracked" | "predicted" | "lost";

export interface Position3D {
  x: number;
  y: number;
  z: number;
}

export interface TrackedObject {
  id: string;
  position_m: Position3D;
  tracking_state: TrackingState;
  confidence: number | null;
  source_cameras: string[];
}

export interface WorldState {
  type: "world_state";
  timestamp_ms: number;
  session_id: string;
  objects: TrackedObject[];
}

export interface Pixel {
  x: number;
  y: number;
}

export interface SelectionCommand {
  type: "select_object";
  session_id: string;
  camera_id: string;
  pixel: Pixel;
  frame_timestamp_ms: number;
}
