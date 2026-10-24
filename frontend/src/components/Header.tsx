import { useWorldStore } from "../store/worldStore";

const STATUS_COLOR: Record<string, string> = {
  connected: "#4ade80",
  connecting: "#fbbf24",
  disconnected: "#5b6673",
  error: "#f87171",
};

export function Header() {
  const sessionId = useWorldStore((s) => s.sessionId);
  const connectionStatus = useWorldStore((s) => s.connectionStatus);
  const mode = useWorldStore((s) => s.mode);

  return (
    <div className="app-header">
      <div className="app-brand">
        <span className="app-brand-dot" />
        <span className="app-brand-name">PHANTOM</span>
        <span className="app-brand-sub">digital twin viewport</span>
      </div>

      <div className="app-session">
        <span className="mono">{sessionId || "no session"}</span>
        <span className="mono">· {mode}</span>
        <span className="status-dot" style={{ background: STATUS_COLOR[connectionStatus] }} />
      </div>
    </div>
  );
}
