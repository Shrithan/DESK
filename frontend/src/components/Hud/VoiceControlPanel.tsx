import { MicIcon } from "./MicIcon";
import { ROLE_PROFILES, type RoleProfile } from "../../lib/roleProfiles";
import type { VoiceStatus } from "../../lib/voiceCommandSession";

interface Props {
  status: VoiceStatus;
  transcript: string;
  error: string | null;
  selectedObjectId: string | null;
  assignments: Record<string, RoleProfile>;
  onPressStart: () => void;
  onPressEnd: () => void;
  onClearAssignment: (objectId: string) => void;
}

const STATUS_LABEL: Record<VoiceStatus, string> = {
  idle: "Hold to talk",
  listening: "Listening…",
  processing: "Transcribing…",
  error: "Error",
};

export function VoiceControlPanel({
  status,
  transcript,
  error,
  selectedObjectId,
  assignments,
  onPressStart,
  onPressEnd,
  onClearAssignment,
}: Props) {
  return (
    <div className="hud-panel">
      <div className="hud-title">Voice Roles (Cartesia STT)</div>

      <div className="hud-row">
        <span>Target</span>
        <span className="mono">{selectedObjectId ?? "none selected"}</span>
      </div>

      <button
        className={`mic-button ${status === "listening" ? "active" : ""}`}
        onMouseDown={onPressStart}
        onMouseUp={onPressEnd}
        onMouseLeave={() => status === "listening" && onPressEnd()}
        onTouchStart={onPressStart}
        onTouchEnd={onPressEnd}
        disabled={!selectedObjectId}
      >
        <MicIcon active={status === "listening"} />
        {STATUS_LABEL[status]}
      </button>

      {transcript && <div className="hud-muted" style={{ marginTop: 6 }}>&ldquo;{transcript}&rdquo;</div>}
      {error && <div className="hud-warning">{error}</div>}

      <div className="hud-muted" style={{ marginTop: 8 }}>
        Say e.g. &ldquo;this is a steering wheel&rdquo; — keyword match, not a language model. Known roles:{" "}
        {ROLE_PROFILES.map((p) => p.label).join(", ")}.
      </div>

      {Object.keys(assignments).length > 0 && (
        <div className="gesture-log">
          {Object.entries(assignments).map(([objectId, profile]) => (
            <div key={objectId} className="hud-row">
              <span className="mono">{objectId}</span>
              <span>{profile.label}</span>
              <button className="icon-btn" onClick={() => onClearAssignment(objectId)} aria-label={`Clear role for ${objectId}`}>
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
