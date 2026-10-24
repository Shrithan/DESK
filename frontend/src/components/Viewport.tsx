import { Canvas } from "@react-three/fiber";
import { Grid, OrbitControls, GizmoHelper, GizmoViewport } from "@react-three/drei";
import { useWorldStore } from "../store/worldStore";
import { ObjectMarker } from "./ObjectMarker";

export function Viewport() {
  const objects = useWorldStore((s) => s.objects);

  return (
    <Canvas
      camera={{ position: [1.2, 1.0, 1.2], fov: 50 }}
      style={{ background: "#121212" }}
    >
      <color attach="background" args={["#121212"]} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[2, 3, 2]} intensity={0.8} />

      <Grid
        args={[2, 2]}
        cellSize={0.1}
        cellColor="#2a2a2a"
        sectionSize={0.5}
        sectionColor="#3a3a3a"
        fadeDistance={6}
        infiniteGrid
      />

      {Object.values(objects).map((obj) => (
        <ObjectMarker key={obj.id} object={obj} />
      ))}

      <axesHelper args={[0.5]} />
      <OrbitControls makeDefault />

      <GizmoHelper alignment="bottom-right" margin={[60, 60]}>
        <GizmoViewport axisColors={["#ff4d4d", "#4dff88", "#4d88ff"]} labelColor="white" />
      </GizmoHelper>
    </Canvas>
  );
}
