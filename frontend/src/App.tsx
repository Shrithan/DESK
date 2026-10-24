import { useEffect, useRef, useState } from "react";
import { Viewport } from "./components/Viewport";
import { ViewportErrorBoundary } from "./components/ViewportErrorBoundary";
import { Header } from "./components/Header";
import { StatusPanel } from "./components/Hud/StatusPanel";
import { SpeakerIcon } from "./components/Hud/SpeakerIcon";
import { ObjectList } from "./components/Hud/ObjectList";
import { CameraHealthPanel } from "./components/Hud/CameraHealthPanel";
import { GameControlPanel, type GestureLogEntry } from "./components/Hud/GameControlPanel";
import { CameraPreviewPanel } from "./components/CameraSelect/CameraPreviewPanel";
import { useWorldStore } from "./store/worldStore";
import { startMockWorld } from "./lib/mockWorld";
import { connectWorldSocket } from "./lib/wsClient";
import { GestureDetector, GESTURE_KEY_MAP } from "./lib/gestureDetector";
import { CartesiaAdapter } from "../../integrations/cartesia/CartesiaAdapter";
import { createConvexSessionAdapter } from "../../integrations/convex/ConvexSessionAdapter";
import { GameControlAdapter } from "../../integrations/gamecontrol/GameControlAdapter";
import type { RenderObject } from "./store/worldStore";
import type { SelectionCommand, WorldState } from "./lib/contract";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws/world";

export default function App() {
  const mode = useWorldStore((s) => s.mode);
  const applyWorldState = useWorldStore((s) => s.applyWorldState);
  const setConnectionStatus = useWorldStore((s) => s.setConnectionStatus);
  const markStaleObjects = useWorldStore((s) => s.markStaleObjects);
  const selectedObjectId = useWorldStore((s) => s.selectedObjectId);

  const [narration, setNarration] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [gameControlArmed, setGameControlArmed] = useState(false);
  const [gestureLog, setGestureLog] = useState<GestureLogEntry[]>([]);

  const cartesiaRef = useRef<CartesiaAdapter | null>(null);
  const convexRef = useRef(createConvexSessionAdapter());
  const gameControlRef = useRef<GameControlAdapter | null>(null);
  const gestureDetectorRef = useRef<GestureDetector | null>(null);
  const gestureLogIdRef = useRef(0);
  const prevStatesRef = useRef<Record<string, RenderObject["trackingState"]>>({});

  if (!cartesiaRef.current) {
    cartesiaRef.current = new CartesiaAdapter(undefined, setNarration);
  }
  if (!gameControlRef.current) {
    gameControlRef.current = new GameControlAdapter();
  }
  if (!gestureDetectorRef.current) {
    gestureDetectorRef.current = new GestureDetector();
  }

  useEffect(() => {
    cartesiaRef.current?.setMuted(muted);
  }, [muted]);

  useEffect(() => {
    gameControlRef.current?.setArmed(gameControlArmed);
    // Selecting a different object (or flipping Armed) with stale velocity
    // history would fire a false gesture from the jump in position.
    gestureDetectorRef.current?.reset();
  }, [gameControlArmed, selectedObjectId]);

  // Watches the currently-selected object's raw world position for a
  // left/right/jump/duck gesture and, if game control is armed, sends the
  // mapped key to the local OS-keystroke proxy. Lost tracking never fires a
  // gesture — a fabricated position must not control anything.
  const handleWorldState = (state: WorldState) => {
    const selectedId = useWorldStore.getState().selectedObjectId;
    if (!selectedId) return;
    const obj = state.objects.find((o) => o.id === selectedId);
    if (!obj || obj.tracking_state === "lost") return;

    const gesture = gestureDetectorRef.current?.feed(obj.position_m.x, obj.position_m.z, state.timestamp_ms);
    if (!gesture) return;

    const key = GESTURE_KEY_MAP[gesture];
    void gameControlRef.current?.fire(key).then((result) => {
      if (!result) return;
      setGestureLog((log) => {
        const entry: GestureLogEntry = {
          id: gestureLogIdRef.current++,
          gesture,
          key: result.key,
          mocked: result.mocked,
          atMs: Date.now(),
        };
        return [entry, ...log].slice(0, 6);
      });
    });
  };

  // Connect to whichever source the mode toggle selects. Mock mode needs no
  // backend at all; live mode talks the real /ws/world contract.
  useEffect(() => {
    if (mode === "mock") {
      setConnectionStatus("connected");
      const stop = startMockWorld((state) => {
        applyWorldState(state, 0);
        handleWorldState(state);
      });
      return stop;
    }

    const disconnect = connectWorldSocket(WS_URL, {
      onState: (state, latencyMs) => {
        applyWorldState(state, latencyMs);
        handleWorldState(state);
      },
      onStatus: setConnectionStatus,
    });
    return disconnect;
  }, [mode, applyWorldState, setConnectionStatus]);

  // Mark objects lost if nothing's arrived in 2s, and narrate tracking-state
  // transitions (not every frame — only on change, and debounced per event).
  useEffect(() => {
    const interval = setInterval(() => {
      markStaleObjects(performance.now(), 2000);

      const objects = useWorldStore.getState().objects;
      for (const obj of Object.values(objects)) {
        const prev = prevStatesRef.current[obj.id];
        if (prev !== obj.trackingState) {
          if (obj.trackingState === "lost" && prev && prev !== "lost") {
            void cartesiaRef.current?.announce("object_lost");
          } else if (obj.trackingState === "tracked" && prev === "lost") {
            void cartesiaRef.current?.announce("object_recovered");
          } else if (obj.trackingState === "tracked" && !prev) {
            void cartesiaRef.current?.announce("tracking_started");
          }
          prevStatesRef.current[obj.id] = obj.trackingState;
        }
      }
    }, 500);
    return () => clearInterval(interval);
  }, [markStaleObjects]);

  const handleSelection = (command: SelectionCommand) => {
    console.info("[selection]", command);
    void convexRef.current.recordSelection({
      sessionId: command.session_id,
      objectId: "pending-resolution", // Resolved server-side once segmentation maps pixel -> object_id.
      cameraId: command.camera_id,
      pixel: command.pixel,
      selectedAtMs: command.frame_timestamp_ms,
    });
  };

  return (
    <div className="app-shell">
      <div className="viewport-area">
        <ViewportErrorBoundary>
          <Viewport />
        </ViewportErrorBoundary>
      </div>

      <Header />

      <div className="hud-left">
        <StatusPanel />
        <ObjectList />
        <GameControlPanel
          armed={gameControlArmed}
          onToggleArmed={() => setGameControlArmed((a) => !a)}
          controllingObjectId={selectedObjectId}
          log={gestureLog}
        />
        <CameraHealthPanel />
      </div>

      <div className="hud-right">
        <CameraPreviewPanel onSelect={handleSelection} />
      </div>

      <div className="narration-banner">
        <button className="icon-btn" onClick={() => setMuted((m) => !m)} aria-label={muted ? "Unmute" : "Mute"}>
          <SpeakerIcon muted={muted} />
        </button>
        <span className="narration-dot" />
        <span>{narration ?? "Listening for tracking events…"}</span>
      </div>
    </div>
  );
}
