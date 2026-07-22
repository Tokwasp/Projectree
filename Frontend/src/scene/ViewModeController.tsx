import { useThree } from "@react-three/fiber";
import { useEffect } from "react";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

interface ViewModeControllerProps {
  is2D: boolean;
  controlsRef: React.RefObject<OrbitControlsImpl | null>;
}

/** Logic-only: on entering 2D, snaps the (still-perspective) camera to look
 * straight down the Z axis at whatever point/distance it was already at, and
 * disables rotation so it can only be panned/zoomed — reading as a flat
 * node-graph view without the cost/risk of swapping camera types. Leaving 2D
 * just re-enables rotation from wherever the view currently sits. */
export function ViewModeController({ is2D, controlsRef }: ViewModeControllerProps) {
  const { camera } = useThree();

  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    if (is2D) {
      const distance = camera.position.distanceTo(controls.target);
      camera.up.set(0, 1, 0);
      camera.position.set(controls.target.x, controls.target.y, controls.target.z + distance);
      controls.enableRotate = false;
    } else {
      controls.enableRotate = true;
    }
    controls.update();
  }, [is2D, camera, controlsRef]);

  return null;
}
