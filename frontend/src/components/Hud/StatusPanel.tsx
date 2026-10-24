import { useWorldStore } from "../../store/worldStore";
import { useFps } from "../../hooks/useFps";
import { Switch } from "./Switch";

const STATUS_COLOR: Record<string, string> = {
  connected: "#4ade80",
  connecting: "#fbbf24",
  disconnected: "#8b98a5",
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
      <div className="hud-title">Session</div>

      <div className="hud-row">
        <span>Source</span>
        <div className="segmented">
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
        <span className="mono" style={{ color: STATUS_COLOR[connectionStatus] }}>
          {connectionStatus}
        </span>
      </div>

      <div className="hud-row">
        <span>FPS</span>
        <span className="mono">{fps}</span>
      </div>

      <div className="hud-row">
        <span>Latency</span>
        <span className="mono">{latencyMs !== null ? `${latencyMs} ms` : "—"}</span>
      </div>

      <div className="hud-row">
        <span>Trails</span>
        <Switch checked={showTrails} onChange={toggleTrails} label="Toggle trails" />
      </div>
    </div>
  );
}
