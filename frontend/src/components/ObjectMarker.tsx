import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, Line } from "@react-three/drei";
import * as THREE from "three";
import type { RenderObject } from "../store/worldStore";
import { lerpVec3 } from "../lib/coords";
import { useWorldStore } from "../store/worldStore";

const STATE_COLOR: Record<RenderObject["trackingState"], string> = {
  tracked: "#4ade80",
  predicted: "#fbbf24",
  lost: "#f87171",
};

interface Props {
  object: RenderObject;
}

export function ObjectMarker({ object }: Props) {
  const groupRef = useRef<THREE.Group>(null);
  const showTrails = useWorldStore((s) => s.showTrails);
  const selectedObjectId = useWorldStore((s) => s.selectedObjectId);
  const isSelected = selectedObjectId === object.id;

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const span = Math.max(object.nextTimeMs - object.prevTimeMs, 1);
    const elapsed = performance.now() - object.prevTimeMs;
    const t = object.trackingState === "lost" ? 1 : Math.min(elapsed / span, 1);
    const pos = lerpVec3(object.prevPos, object.nextPos, t);
    groupRef.current.position.set(...pos);

    if (isSelected) {
      const pulse = 1 + Math.sin(clock.elapsedTime * 4) * 0.08;
      groupRef.current.scale.setScalar(pulse);
    } else {
      groupRef.current.scale.setScalar(1);
    }
  });

  const color = STATE_COLOR[object.trackingState];
  const opacity = object.trackingState === "lost" ? 0.35 : 1;

  return (
    <group>
      <group ref={groupRef} position={object.nextPos}>
        <mesh>
          <sphereGeometry args={[0.025, 32, 32]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={0.6}
            roughness={0.35}
            metalness={0.1}
            transparent
            opacity={opacity}
          />
        </mesh>
        {isSelected && (
          <mesh>
            <sphereGeometry args={[0.042, 24, 24]} />
            <meshBasicMaterial color="white" wireframe transparent opacity={0.6} />
          </mesh>
        )}
        <Html occlude={false} zIndexRange={[0, 0]} center sprite>
          <div className="object-label" style={{ color }}>
            {object.id} · {object.trackingState}
          </div>
        </Html>
      </group>
      {showTrails && object.trail.length > 1 && (
        <Line points={object.trail} color={color} lineWidth={1} transparent opacity={0.4} />
      )}
    </group>
  );
}
