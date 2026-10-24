import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

/**
 * WebGL can fail to initialize (old GPU, disabled hardware acceleration,
 * restrictive sandbox/policy). Without this boundary, R3F's Canvas throws
 * and takes the entire app down — HUD included — instead of just the 3D view.
 */
export class ViewportErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("[ViewportErrorBoundary] 3D viewport failed to render:", error);
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="viewport-fallback">
          <div>3D rendering unavailable in this browser (WebGL failed to initialize).</div>
          <div className="hud-muted">The rest of the UI still works — object list, selection, and sponsor status below are unaffected.</div>
        </div>
      );
    }
    return this.props.children;
  }
}
