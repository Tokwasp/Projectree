import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useState, useRef } from "react";
import { MOUSE } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { TreeScene } from "../tree/TreeScene";
import { SpaceBackground } from "./SpaceBackground";
import { ViewModeController } from "./ViewModeController";
import { ViewModeToggle } from "./ViewModeToggle";
import { ZoomControl } from "./ZoomControl";

const MIN_DISTANCE = 6;
const MAX_DISTANCE = 70;

export function SpaceScene() {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const [is2D, setIs2D] = useState(false);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Canvas camera={{ position: [10, 8, 22], fov: 50 }} gl={{ antialias: true }}>
        <color attach="background" args={["#000006"]} />
        <fogExp2 attach="fog" args={["#000006", 0.006]} />

        <ambientLight intensity={0.25} />
        <pointLight position={[10, 12, 10]} intensity={40} distance={80} decay={2} />

        <SpaceBackground />
        <TreeScene controlsRef={controlsRef} />

        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.08}
          minDistance={MIN_DISTANCE}
          maxDistance={MAX_DISTANCE}
          zoomToCursor
          mouseButtons={{ LEFT: MOUSE.ROTATE, MIDDLE: MOUSE.PAN, RIGHT: MOUSE.PAN }}
        />
        <ViewModeController is2D={is2D} controlsRef={controlsRef} />

        <EffectComposer multisampling={4}>
          <Bloom
            mipmapBlur
            intensity={0.9}
            luminanceThreshold={0.25}
            luminanceSmoothing={0.9}
            radius={0.7}
          />
        </EffectComposer>
      </Canvas>

      <ZoomControl controlsRef={controlsRef} minDistance={MIN_DISTANCE} maxDistance={MAX_DISTANCE} />
      <ViewModeToggle is2D={is2D} onToggle={() => setIs2D((prev) => !prev)} />
    </div>
  );
}
