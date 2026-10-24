import type { WorldState } from "./contract";

/**
 * Drives two virtual objects on known trajectories so the UI is demoable with
 * no cameras or backend. Judges should be able to toggle this on and watch
 * spheres move in X/Y/Z, including a brief simulated "lost" dropout.
 */
export function startMockWorld(
  onState: (state: WorldState) => void,
  sessionId = "mock-demo",
  hz = 15,
): () => void {
  const start = performance.now();

  const interval = setInterval(() => {
    const t = (performance.now() - start) / 1000;

    const obj1X = 0.3 * Math.cos(t * 0.6);
    const obj1Y = 0.3 * Math.sin(t * 0.6);
    const obj1Z = 0.15 + 0.05 * Math.sin(t * 1.2);

    const obj2X = 0.4 * Math.sin(t * 0.3);
    const obj2Y = -0.25;
    const obj2Z = 0.1 + 0.2 * Math.abs(Math.sin(t * 0.4));

    // Simulate a brief tracking dropout every ~12s for ~1s so the UI's
    // lost/predicted/tracked handling is actually exercised, not just claimed.
    const dropoutPhase = t % 12;
    const obj2State = dropoutPhase > 10 && dropoutPhase < 11 ? "lost" : dropoutPhase >= 11 ? "predicted" : "tracked";

    const state: WorldState = {
      type: "world_state",
      timestamp_ms: Date.now(),
      session_id: sessionId,
      objects: [
        {
          id: "obj_1",
          position_m: { x: obj1X, y: obj1Y, z: obj1Z },
          tracking_state: "tracked",
          confidence: 0.92,
          source_cameras: ["mock_cam_1", "mock_cam_2"],
        },
        {
          id: "obj_2",
          position_m: { x: obj2X, y: obj2Y, z: obj2Z },
          tracking_state: obj2State,
          confidence: obj2State === "lost" ? null : 0.78,
          source_cameras: obj2State === "lost" ? [] : ["mock_cam_1"],
        },
      ],
    };

    onState(state);
  }, 1000 / hz);

  return () => clearInterval(interval);
}
