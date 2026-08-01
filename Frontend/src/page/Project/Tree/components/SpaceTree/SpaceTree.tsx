import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { MOUSE, Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import {
  CAMERA,
  SPACE,
  UI_FONT,
  UI_SURFACE,
  type OrbitControlsRef,
  type TreeNodeInput,
} from "./config";
import { TreeScene } from "./TreeScene";

/**
 * 마운트하는 단 하나의 컴포넌트. Canvas, 카메라·컨트롤, Bloom, 오버레이 UI를 소유한다.
 * 부모에 높이가 없으면 화면이 검게만 보이므로 반드시 크기가 있는 컨테이너에 넣을 것.
 *
 * `data`는 안정적인 참조여야 한다 — 렌더마다 새 객체를 주면 레이아웃이 다시 계산되고
 * 물리 상태가 초기화된다.
 */

interface SpaceTreeProps {
  data: TreeNodeInput;
}

export function SpaceTree({ data }: SpaceTreeProps) {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const [is2D, setIs2D] = useState(false);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Canvas
        camera={{ position: CAMERA.INITIAL_POSITION, fov: CAMERA.FOV }}
        gl={{ antialias: true }}
      >
        <color attach="background" args={[SPACE.BACKGROUND_COLOR]} />
        <fogExp2
          attach="fog"
          args={[SPACE.BACKGROUND_COLOR, SPACE.FOG_DENSITY]}
        />

        <ambientLight intensity={0.25} />
        <pointLight
          position={[10, 12, 10]}
          intensity={40}
          distance={80}
          decay={2}
        />

        <TreeScene data={data} controlsRef={controlsRef} is2D={is2D} />

        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.08}
          minDistance={CAMERA.MIN_DISTANCE}
          maxDistance={CAMERA.MAX_DISTANCE}
          zoomToCursor
          mouseButtons={{
            LEFT: MOUSE.ROTATE,
            MIDDLE: MOUSE.PAN,
            RIGHT: MOUSE.PAN,
          }}
        />
        <ViewModeController is2D={is2D} controlsRef={controlsRef} />

        {/* 셰이더의 발광을 실제로 빛나게 만든다 */}
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

      <ZoomControl controlsRef={controlsRef} />
      <ViewModeToggle is2D={is2D} onToggle={() => setIs2D((prev) => !prev)} />
    </div>
  );
}

interface CameraPose {
  position: Vector3;
  target: Vector3;
}

/**
 * 2D 전환의 본체는 노드 재배치(TreeScene)다. 여기서는 카메라만 거든다 —
 * 평면을 옆에서 보면 선으로만 보이므로 정면 쪽으로 부드럽게 이동시키고,
 * 3D로 돌아올 때는 2D로 들어가기 직전의 시점으로 되돌린다.
 * 회전을 잠그지는 않으므로 전환 후에도 자유롭게 돌려볼 수 있다.
 */
function ViewModeController({
  is2D,
  controlsRef,
}: {
  is2D: boolean;
  controlsRef: OrbitControlsRef;
}) {
  const goalRef = useRef<CameraPose | null>(null);
  /** 2D로 들어가기 직전의 시점. 3D로 돌아올 때 여기로 복귀한다 */
  const savedRef = useRef<CameraPose | null>(null);

  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    if (!is2D) {
      goalRef.current = savedRef.current;
      savedRef.current = null;
      return;
    }

    const camera = controls.object;
    savedRef.current = {
      position: camera.position.clone(),
      target: controls.target.clone(),
    };

    const distance = camera.position.distanceTo(controls.target);
    camera.up.set(0, 1, 0);
    goalRef.current = {
      position: new Vector3(
        controls.target.x,
        controls.target.y,
        controls.target.z + distance,
      ),
      target: controls.target.clone(),
    };
  }, [is2D, controlsRef]);

  // 이동 중에 사용자가 회전·줌을 시작하면 카메라를 놓아준다.
  // 안 그러면 OrbitControls가 옮긴 위치를 다음 프레임에 lerp가 덮어써 서로 밀고 당긴다
  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    const release = () => {
      goalRef.current = null;
    };

    controls.addEventListener("start", release);
    return () => controls.removeEventListener("start", release);
  }, [controlsRef]);

  useFrame((_, delta) => {
    const controls = controlsRef.current;
    const goal = goalRef.current;
    if (!controls || !goal) return;

    // 프레임레이트가 달라도 같은 속도로 붙도록 delta로 보간한다.
    // 시선(target)까지 같이 옮겨야 팬으로 옮겨둔 화면도 제대로 복귀한다
    const step = Math.min(1, delta * 3.5);
    controls.object.position.lerp(goal.position, step);
    controls.target.lerp(goal.target, step);
    controls.update();

    if (controls.object.position.distanceTo(goal.position) < 0.05) {
      goalRef.current = null;
    }
  });

  return null;
}

function ViewModeToggle({
  is2D,
  onToggle,
}: {
  is2D: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      style={{
        position: "absolute",
        top: 24,
        right: 24,
        zIndex: 20,
        padding: "8px 18px",
        borderRadius: 999,
        fontSize: 13,
        fontFamily: UI_FONT,
        letterSpacing: "0.02em",
        cursor: "pointer",
        userSelect: "none",
        ...UI_SURFACE,
      }}
    >
      {is2D ? "3D로 보기" : "펼쳐 보기"}
    </button>
  );
}

/**
 * 우하단 세로 줌 슬라이더. OrbitControls의 거리를 rAF로 직접 읽고 쓰므로
 * 휠 줌과 항상 동기화되고 리렌더는 발생하지 않는다.
 */
function ZoomControl({ controlsRef }: { controlsRef: OrbitControlsRef }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const draggingRef = useRef(false);
  const { MIN_DISTANCE, MAX_DISTANCE, ZOOM_STEP } = CAMERA;

  useEffect(() => {
    let rafId: number;
    const tick = () => {
      const controls = controlsRef.current;
      if (controls && inputRef.current && !draggingRef.current) {
        // 위로 밀수록 확대되도록 뒤집는다 (+/- 버튼과 방향을 맞춤)
        inputRef.current.value = (
          MAX_DISTANCE +
          MIN_DISTANCE -
          controls.getDistance()
        ).toString();
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [controlsRef, MIN_DISTANCE, MAX_DISTANCE]);

  const setDistance = (distance: number) => {
    const controls = controlsRef.current;
    if (!controls) return;
    const camera = controls.object;
    const clamped = Math.min(MAX_DISTANCE, Math.max(MIN_DISTANCE, distance));
    const direction = camera.position.clone().sub(controls.target).normalize();
    camera.position.copy(controls.target).addScaledVector(direction, clamped);
    controls.update();
  };

  const step = (sign: 1 | -1) => {
    const controls = controlsRef.current;
    if (!controls) return;
    setDistance(controls.getDistance() - sign * ZOOM_STEP);
  };

  return (
    <div
      style={{
        position: "absolute",
        right: 24,
        bottom: 28,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
        zIndex: 20,
        fontFamily: UI_FONT,
        userSelect: "none",
      }}
    >
      <button type="button" onClick={() => step(1)} style={zoomButtonStyle}>
        +
      </button>

      <div style={{ width: 32, height: 140, position: "relative" }}>
        <input
          ref={inputRef}
          type="range"
          min={MIN_DISTANCE}
          max={MAX_DISTANCE}
          step={0.1}
          defaultValue={(MIN_DISTANCE + MAX_DISTANCE) / 2}
          onPointerDown={() => (draggingRef.current = true)}
          onPointerUp={() => (draggingRef.current = false)}
          onChange={(event) =>
            setDistance(
              MAX_DISTANCE + MIN_DISTANCE - Number(event.target.value),
            )
          }
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: 140,
            height: 24,
            margin: 0,
            transform: "translate(-50%, -50%) rotate(-90deg)",
            accentColor: "#7fd8ff",
            cursor: "pointer",
          }}
        />
      </div>

      <button type="button" onClick={() => step(-1)} style={zoomButtonStyle}>
        −
      </button>
    </div>
  );
}

const zoomButtonStyle: CSSProperties = {
  width: 26,
  height: 26,
  borderRadius: "50%",
  fontSize: 15,
  lineHeight: 1,
  cursor: "pointer",
  ...UI_SURFACE,
};
