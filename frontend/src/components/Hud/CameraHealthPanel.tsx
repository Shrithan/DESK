import { useWorldStore } from "../../store/worldStore";

export function CameraHealthPanel() {
  const cameras = useWorldStore((s) => s.cameras);

  return (
    <div className="hud-panel">
      <div className="hud-title">Cameras</div>
      {cameras.length === 0 && <div className="hud-muted">No camera health reported</div>}
      {cameras.map((cam) => (
        <div key={cam.id} className="hud-row">
          <span>{cam.id}</span>
          <span style={{ color: cam.connected ? "#4ade80" : "#f87171" }}>
            {cam.connected ? `${cam.fps ?? "—"} fps` : "offline"}
          </span>
        </div>
      ))}
    </div>
  );
}
