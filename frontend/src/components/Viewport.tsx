import { Canvas } from "@react-three/fiber";
import { ContactShadows, Grid, GizmoHelper, GizmoViewport, OrbitControls } from "@react-three/drei";
import { useWorldStore } from "../store/worldStore";
import { ObjectMarker } from "./ObjectMarker";

export function Viewport() {
  const objects = useWorldStore((s) => s.objects);

  return (
    <Canvas
      camera={{ position: [1.3, 1.05, 1.3], fov: 45 }}
      gl={{ alpha: true, antialias: true }}
      dpr={[1, 2]}
    >
      <ambientLight intensity={0.5} />
      <directionalLight position={[2, 3.5, 2]} intensity={1.1} color="#dce8f5" />
      <pointLight position={[-1.5, 1, -1.5]} intensity={0.25} color="#38bdf8" />

      <Grid
        args={[2, 2]}
        cellSize={0.1}
        cellColor="#20262f"
        sectionSize={0.5}
        sectionColor="#2f3a47"
        fadeDistance={6}
        infiniteGrid
      />

      <ContactShadows position={[0, 0, 0]} opacity={0.55} scale={3} blur={2.2} far={1.5} resolution={512} color="#000000" />

      {Object.values(objects).map((obj) => (
        <ObjectMarker key={obj.id} object={obj} />
      ))}

      <axesHelper args={[0.4]} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} />

      <GizmoHelper alignment="bottom-right" margin={[60, 60]}>
        <GizmoViewport axisColors={["#f87171", "#4ade80", "#38bdf8"]} labelColor="white" />
      </GizmoHelper>
    </Canvas>
  );
}
