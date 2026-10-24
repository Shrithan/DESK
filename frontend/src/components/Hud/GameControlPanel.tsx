import { Switch } from "./Switch";

export interface GestureLogEntry {
  id: number;
  gesture: string;
  key: string;
  mocked: boolean;
  atMs: number;
}

interface Props {
  armed: boolean;
  onToggleArmed: () => void;
  controllingObjectId: string | null;
  log: GestureLogEntry[];
}

export function GameControlPanel({ armed, onToggleArmed, controllingObjectId, log }: Props) {
  return (
    <div className="hud-panel">
      <div className="hud-title">Game Control</div>

      <div className="hud-row">
        <span>Send real keystrokes</span>
        <Switch checked={armed} onChange={onToggleArmed} label="Arm game control" />
      </div>

      {armed && (
        <div className="hud-warning">
          Live — gestures send real keypresses to whichever window has focus, not just the
          game. Click the game window before moving the object.
        </div>
      )}

      <div className="hud-muted" style={{ marginTop: 6 }}>
        {controllingObjectId ? `Controlling: ${controllingObjectId}` : "Select an object above to control with it"}
      </div>

      {log.length > 0 && (
        <div className="gesture-log">
          {log.map((entry) => (
            <div key={entry.id} className="hud-row">
              <span className="mono">{entry.gesture}</span>
              <span className="mono" style={{ color: entry.mocked ? "var(--text-faint)" : "var(--accent)" }}>
                {entry.key}
                {entry.mocked ? " (mock)" : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
