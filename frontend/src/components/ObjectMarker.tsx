import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import type { RenderObject } from "../store/worldStore";
import { lerpVec3 } from "../lib/coords";
import { useWorldStore } from "../store/worldStore";

const STATE_COLOR: Record<RenderObject["trackingState"], string> = {
  tracked: "#4ade80",
  predicted: "#facc15",
  lost: "#f87171",
};

interface Props {
  object: RenderObject;
}

export function ObjectMarker({ object }: Props) {
  const meshRef = useRef<THREE.Mesh>(null);
  const showTrails = useWorldStore((s) => s.showTrails);
  const selectedObjectId = useWorldStore((s) => s.selectedObjectId);
  const isSelected = selectedObjectId === object.id;

  useFrame(() => {
    if (!meshRef.current) return;
    const span = Math.max(object.nextTimeMs - object.prevTimeMs, 1);
    const elapsed = performance.now() - object.prevTimeMs;
    const t = object.trackingState === "lost" ? 1 : Math.min(elapsed / span, 1);
    const pos = lerpVec3(object.prevPos, object.nextPos, t);
    meshRef.current.position.set(...pos);
  });

  const color = STATE_COLOR[object.trackingState];
  const opacity = object.trackingState === "lost" ? 0.35 : 1;

  return (
    <group>
      <mesh ref={meshRef} position={object.nextPos}>
        <sphereGeometry args={[0.025, 24, 24]} />
        <meshStandardMaterial color={color} transparent opacity={opacity} />
        {isSelected && (
          <mesh>
            <sphereGeometry args={[0.04, 16, 16]} />
            <meshBasicMaterial color="white" wireframe />
          </mesh>
        )}
      </mesh>
      {showTrails && object.trail.length > 1 && (
        <Line points={object.trail} color={color} lineWidth={1} transparent opacity={0.4} />
      )}
    </group>
  );
}
