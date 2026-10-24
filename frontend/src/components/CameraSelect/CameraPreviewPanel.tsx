import { useRef, useState } from "react";
import { cssClickToNativePixel } from "../../lib/pixelMap";
import {
  PLACEHOLDER_NATIVE_HEIGHT,
  PLACEHOLDER_NATIVE_WIDTH,
  placeholderFrameDataUrl,
} from "../../lib/placeholderFrame";
import { useWorldStore } from "../../store/worldStore";
import type { SelectionCommand } from "../../lib/contract";

const MOCK_CAMERA_IDS = ["mock_cam_1", "mock_cam_2"];

interface Props {
  onSelect: (command: SelectionCommand) => void;
}

export function CameraPreviewPanel({ onSelect }: Props) {
  const sessionId = useWorldStore((s) => s.sessionId) || "mock-demo";
  const [lastClick, setLastClick] = useState<{ cam: string; x: number; y: number } | null>(null);

  return (
    <div className="hud-panel">
      <div className="hud-title">Cameras — click an object to select it</div>
      <div className="camera-grid">
        {MOCK_CAMERA_IDS.map((camId, idx) => (
          <CameraTile
            key={camId}
            cameraId={camId}
            seed={idx * 3.1}
            onClick={(x, y) => {
              setLastClick({ cam: camId, x, y });
              onSelect({
                type: "select_object",
                session_id: sessionId,
                camera_id: camId,
                pixel: { x, y },
                frame_timestamp_ms: Date.now(),
              });
            }}
          />
        ))}
      </div>
      {lastClick && (
        <div className="hud-muted">
          Last selection: {lastClick.cam} @ ({lastClick.x}, {lastClick.y}) native px
        </div>
      )}
    </div>
  );
}

function CameraTile({
  cameraId,
  seed,
  onClick,
}: {
  cameraId: string;
  seed: number;
  onClick: (x: number, y: number) => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);

  const handleClick = (e: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const native = cssClickToNativePixel(
      clickX,
      clickY,
      rect.width,
      rect.height,
      PLACEHOLDER_NATIVE_WIDTH,
      PLACEHOLDER_NATIVE_HEIGHT,
    );
    if (native) onClick(native.x, native.y);
  };

  return (
    <div className="camera-tile-wrap">
      <img
        ref={imgRef}
        src={placeholderFrameDataUrl(cameraId, seed)}
        alt={cameraId}
        className="camera-tile"
        onClick={handleClick}
      />
    </div>
  );
}
