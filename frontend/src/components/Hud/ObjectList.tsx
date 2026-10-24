import { useWorldStore } from "../../store/worldStore";

export function ObjectList() {
  const objects = useWorldStore((s) => s.objects);
  const selectedObjectId = useWorldStore((s) => s.selectedObjectId);
  const selectObject = useWorldStore((s) => s.selectObject);

  const entries = Object.values(objects);

  return (
    <div className="hud-panel">
      <div className="hud-title">Objects ({entries.length})</div>
      {entries.length === 0 && <div className="hud-muted">No objects tracked yet</div>}
      {entries.map((obj) => (
        <div
          key={obj.id}
          className={`hud-object-row ${selectedObjectId === obj.id ? "selected" : ""}`}
          onClick={() => selectObject(obj.id)}
        >
          <span className="hud-object-id">{obj.id}</span>
          <span className={`hud-badge hud-badge-${obj.trackingState}`}>{obj.trackingState}</span>
          <span className="hud-muted">
            {obj.confidence !== null ? `${Math.round(obj.confidence * 100)}%` : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
