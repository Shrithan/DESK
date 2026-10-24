import { useWorldStore } from "../../store/worldStore";
import { useFps } from "../../hooks/useFps";

const STATUS_COLOR: Record<string, string> = {
  connected: "#4ade80",
  connecting: "#facc15",
  disconnected: "#9ca3af",
  error: "#f87171",
};

export function StatusPanel() {
  const mode = useWorldStore((s) => s.mode);
  const setMode = useWorldStore((s) => s.setMode);
  const connectionStatus = useWorldStore((s) => s.connectionStatus);
  const latencyMs = useWorldStore((s) => s.latencyMs);
  const showTrails = useWorldStore((s) => s.showTrails);
  const toggleTrails = useWorldStore((s) => s.toggleTrails);
  const fps = useFps();

  return (
    <div className="hud-panel">
      <div className="hud-row">
        <span>Mode</span>
        <div className="hud-toggle-group">
          <button className={mode === "mock" ? "active" : ""} onClick={() => setMode("mock")}>
            Mock
          </button>
          <button className={mode === "live" ? "active" : ""} onClick={() => setMode("live")}>
            Live
          </button>
        </div>
      </div>

      <div className="hud-row">
        <span>Connection</span>
        <span style={{ color: STATUS_COLOR[connectionStatus] }}>{connectionStatus}</span>
      </div>

      <div className="hud-row">
        <span>FPS</span>
        <span>{fps}</span>
      </div>

      <div className="hud-row">
        <span>Latency</span>
        <span>{latencyMs !== null ? `${latencyMs} ms` : "—"}</span>
      </div>

      <div className="hud-row">
        <span>Trails</span>
        <button className={showTrails ? "active" : ""} onClick={toggleTrails}>
          {showTrails ? "On" : "Off"}
        </button>
      </div>
    </div>
  );
}
