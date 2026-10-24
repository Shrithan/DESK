import { useEffect, useRef, useState } from "react";
import { Viewport } from "./components/Viewport";
import { ViewportErrorBoundary } from "./components/ViewportErrorBoundary";
import { Header } from "./components/Header";
import { StatusPanel } from "./components/Hud/StatusPanel";
import { SpeakerIcon } from "./components/Hud/SpeakerIcon";
import { ObjectList } from "./components/Hud/ObjectList";
import { CameraHealthPanel } from "./components/Hud/CameraHealthPanel";
import { HeldKeysPanel } from "./components/Hud/HeldKeysPanel";
import { VoiceControlPanel } from "./components/Hud/VoiceControlPanel";
import { CameraPreviewPanel } from "./components/CameraSelect/CameraPreviewPanel";
import { useWorldStore } from "./store/worldStore";
import { startMockWorld } from "./lib/mockWorld";
import { connectWorldSocket, type ConnectionStatus } from "./lib/wsClient";
import { connectKeysSocket } from "./lib/keysSocket";
import type { KeyState } from "./lib/keyState";
import { matchRoleProfile, type RoleProfile } from "./lib/roleProfiles";
import { RoleController, type Position3 } from "./lib/roleController";
import { VoiceCommandSession, type VoiceStatus } from "./lib/voiceCommandSession";
import { CartesiaAdapter } from "../../integrations/cartesia/CartesiaAdapter";
import { createConvexSessionAdapter } from "../../integrations/convex/ConvexSessionAdapter";
import { VoiceControlAdapter } from "../../integrations/voicecontrol/VoiceControlAdapter";
import type { RenderObject } from "./store/worldStore";
import type { SelectionCommand, WorldState } from "./lib/contract";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws/world";
const KEYS_WS_URL = import.meta.env.VITE_KEYS_WS_URL ?? "ws://localhost:8765/ws/keys";
const STT_WS_URL = import.meta.env.VITE_CARTESIA_STT_WS_URL ?? "ws://localhost:8787/stt";

export default function App() {
  const mode = useWorldStore((s) => s.mode);
  const applyWorldState = useWorldStore((s) => s.applyWorldState);
  const setConnectionStatus = useWorldStore((s) => s.setConnectionStatus);
  const markStaleObjects = useWorldStore((s) => s.markStaleObjects);
  const selectedObjectId = useWorldStore((s) => s.selectedObjectId);

  const [narration, setNarration] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [keyState, setKeyState] = useState<KeyState | null>(null);
  const [keysConnectionStatus, setKeysConnectionStatus] = useState<ConnectionStatus>("disconnected");

  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("idle");
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [roleAssignments, setRoleAssignments] = useState<Record<string, RoleProfile>>({});

  const cartesiaRef = useRef<CartesiaAdapter | null>(null);
  const convexRef = useRef(createConvexSessionAdapter());
  const roleControllerRef = useRef<RoleController | null>(null);
  const voiceControlRef = useRef<VoiceControlAdapter | null>(null);
  const voiceSessionRef = useRef<VoiceCommandSession | null>(null);
  const lastRawPositionsRef = useRef<Record<string, Position3>>({});
  const prevStatesRef = useRef<Record<string, RenderObject["trackingState"]>>({});

  if (!cartesiaRef.current) {
    cartesiaRef.current = new CartesiaAdapter(undefined, setNarration);
  }
  if (!roleControllerRef.current) {
    roleControllerRef.current = new RoleController();
  }
  if (!voiceControlRef.current) {
    voiceControlRef.current = new VoiceControlAdapter();
  }

  useEffect(() => {
    cartesiaRef.current?.setMuted(muted);
  }, [muted]);

  // Release any held voice-control keys if the tab closes / component unmounts.
  useEffect(() => {
    return () => {
      void voiceControlRef.current?.releaseAll();
    };
  }, []);

  // Feeds every live object position to the role controller and to
  // lastRawPositionsRef (so a new voice assignment can snapshot a fresh
  // center). Uses the RAW world position_m, not the Three.js render
  // transform, since role axes (x=right, y=away, z=up) are defined in the
  // world frame everyone else shares.
  const handleWorldState = (state: WorldState) => {
    const controller = roleControllerRef.current;
    if (!controller) return;

    const assignedIds = new Set(controller.assignedObjectIds());
    const transitions = [];
    for (const obj of state.objects) {
      lastRawPositionsRef.current[obj.id] = obj.position_m;
      if (assignedIds.has(obj.id) && obj.tracking_state !== "lost") {
        transitions.push(...controller.update(obj.id, obj.position_m));
      }
    }
    if (transitions.length > 0) void voiceControlRef.current?.applyTransitions(transitions);
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

  // Visualizes Agent 3's tilt_keys held-key state (/ws/keys). This is
  // display-only — the real OS keystroke injection happens entirely in that
  // backend via pynput; the frontend never injects keys itself.
  useEffect(() => {
    const disconnect = connectKeysSocket(KEYS_WS_URL, {
      onState: setKeyState,
      onStatus: setKeysConnectionStatus,
    });
    return disconnect;
  }, []);

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

  const applyRoleTranscript = (text: string) => {
    const profile = matchRoleProfile(text);
    if (!profile) {
      setVoiceError(`No known role recognized in: "${text}"`);
      return;
    }
    if (!selectedObjectId) {
      setVoiceError("Select an object first, then assign it a role.");
      return;
    }
    const center = lastRawPositionsRef.current[selectedObjectId];
    if (!center) {
      setVoiceError("No position data yet for that object.");
      return;
    }
    const released = roleControllerRef.current?.assign(selectedObjectId, profile, center) ?? [];
    if (released.length > 0) void voiceControlRef.current?.applyTransitions(released);
    setRoleAssignments((prev) => ({ ...prev, [selectedObjectId]: profile }));
    setVoiceError(null);
  };

  const handlePressStart = () => {
    if (!selectedObjectId) return;
    setVoiceTranscript("");
    setVoiceError(null);
    const session = new VoiceCommandSession(STT_WS_URL, {
      onTranscript: (text, isFinal) => {
        setVoiceTranscript(text);
        if (isFinal && text) applyRoleTranscript(text);
      },
      onError: setVoiceError,
      onStatus: setVoiceStatus,
    });
    voiceSessionRef.current = session;
    void session.start();
  };

  const handlePressEnd = () => {
    voiceSessionRef.current?.stop();
  };

  const handleClearAssignment = (objectId: string) => {
    const released = roleControllerRef.current?.unassign(objectId) ?? [];
    if (released.length > 0) void voiceControlRef.current?.applyTransitions(released);
    setRoleAssignments((prev) => {
      const next = { ...prev };
      delete next[objectId];
      return next;
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
        <VoiceControlPanel
          status={voiceStatus}
          transcript={voiceTranscript}
          error={voiceError}
          selectedObjectId={selectedObjectId}
          assignments={roleAssignments}
          onPressStart={handlePressStart}
          onPressEnd={handlePressEnd}
          onClearAssignment={handleClearAssignment}
        />
        <CameraHealthPanel />
      </div>

      <div className="hud-right">
        <CameraPreviewPanel onSelect={handleSelection} />
        <HeldKeysPanel connectionStatus={keysConnectionStatus} keyState={keyState} />
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
