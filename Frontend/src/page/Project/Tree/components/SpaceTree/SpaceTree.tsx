import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { MOUSE, Vector3, type PerspectiveCamera } from "three";
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
import { boundingRadius, buildTree } from "./treeEngine";

/**
 * 마운트하는 단 하나의 컴포넌트. Canvas, 카메라·컨트롤, Bloom, 오버레이 UI를 소유한다.
 * 부모에 높이가 없으면 화면이 검게만 보이므로 반드시 크기가 있는 컨테이너에 넣을 것.
 *
 * `data`는 안정적인 참조여야 한다 — 렌더마다 새 객체를 주면 레이아웃이 다시 계산되고
 * 물리 상태가 초기화된다.
 */

interface SpaceTreeProps {
  data: TreeNodeInput;
  /** 선택된 결정과 연관된 노드 id. null이면 선택 없음. */
  highlightIds: Set<string> | null;
  onSelectDecision: (id: string) => void;
  /** 우측 패널이 덮는 폭 — 줌·보기 전환 버튼을 그만큼 왼쪽으로 밀어낸다. */
  rightInset?: number;
}

export function SpaceTree({
  data,
  highlightIds,
  onSelectDecision,
  rightInset = 0,
}: SpaceTreeProps) {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const [is2D, setIs2D] = useState(false);

  const flat = useMemo(() => buildTree(data), [data]);
  const planar = useMemo(() => buildTree(data, true), [data]);

  // 평면 배치는 3D보다 훨씬 넓게 퍼진다 — 전환할 때 카메라를 여기에 맞춰야 잘리지 않는다
  const planarRadius = useMemo(() => boundingRadius(planar), [planar]);

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

        <TreeScene
          flat={flat}
          planar={planar}
          controlsRef={controlsRef}
          is2D={is2D}
          highlightIds={highlightIds}
          onSelectDecision={onSelectDecision}
        />

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
        <ViewModeController
          is2D={is2D}
          controlsRef={controlsRef}
          fitRadius={planarRadius}
        />

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

      <ZoomControl controlsRef={controlsRef} rightInset={rightInset} />
      <ViewModeToggle
        is2D={is2D}
        onToggle={() => setIs2D((prev) => !prev)}
        rightInset={rightInset}
      />
    </div>
  );
}

interface CameraPose {
  position: Vector3;
  target: Vector3;
}

/** 반지름 radius인 구가 화면에 다 들어오는 카메라 거리 */
function fitDistance(camera: PerspectiveCamera, radius: number): number {
  const halfFov = (camera.fov * Math.PI) / 360;
  const byHeight = radius / Math.tan(halfFov);
  return Math.max(byHeight, byHeight / camera.aspect) * 1.1;
}

function ViewModeController({
  is2D,
  controlsRef,
  fitRadius,
}: {
  is2D: boolean;
  controlsRef: OrbitControlsRef;
  fitRadius: number;
}) {
  const goalRef = useRef<CameraPose | null>(null);
  const savedRef = useRef<CameraPose | null>(null);

  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    if (!is2D) {
      controls.maxDistance = CAMERA.MAX_DISTANCE;
      goalRef.current = savedRef.current;
      savedRef.current = null;
      return;
    }

    const camera = controls.object as PerspectiveCamera;
    savedRef.current = {
      position: camera.position.clone(),
      target: controls.target.clone(),
    };

    // 평면 배치는 원점 기준으로 퍼지므로 시선도 원점으로 되돌려야 한쪽이 잘리지 않는다
    const target = new Vector3(0, 0, 0);
    const distance = fitDistance(camera, fitRadius);

    // 기본 상한(70)으로는 못 담는 트리도 있다 — 그때만 상한을 늘린다
    controls.maxDistance = Math.max(CAMERA.MAX_DISTANCE, distance);
    camera.up.set(0, 1, 0);

    goalRef.current = {
      position: new Vector3(target.x, target.y, target.z + distance),
      target,
    };
  }, [is2D, controlsRef, fitRadius]);

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
  rightInset,
}: {
  is2D: boolean;
  onToggle: () => void;
  rightInset: number;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      style={{
        position: "absolute",
        top: 24,
        right: 24 + rightInset,
        transition: "right 0.2s ease",
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
function ZoomControl({
  controlsRef,
  rightInset,
}: {
  controlsRef: OrbitControlsRef;
  rightInset: number;
}) {
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
        right: 24 + rightInset,
        bottom: 28,
        transition: "right 0.2s ease",
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
