import { Html } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  EDGE_COLOR,
  LABEL_FADE_DISTANCE,
  NODE_VISUALS,
  SPACE,
  UI_FONT,
  type FlatTreeNode,
  type OrbitControlsRef,
  type TreeEdge,
} from "./config";
import {
  nodeVertexShader,
  planetFragmentShader,
  starFragmentShader,
  starfieldFragmentShader,
  starfieldVertexShader,
} from "./shaders";
import {
  useTreeRuntime,
  type FlatTree,
  type TreeRuntime,
} from "./treeEngine";

const PLANET_TYPES = ["category", "decision", "task", "issue"] as const;

interface TreeSceneProps {
  /** 기본(3D) 배치 */
  flat: FlatTree;
  /** "펼쳐 보기"용 평면 배치 */
  planar: FlatTree;
  controlsRef: OrbitControlsRef;
  is2D: boolean;
}

export function TreeScene({
  flat,
  planar,
  controlsRef,
  is2D,
}: TreeSceneProps) {
  const runtime = useTreeRuntime(flat);

  // 목표만 바꾸면 스프링이 새 배치까지 끌고 간다 — 순간이동이 아니라 이동 모션이 된다
  useEffect(() => {
    runtime.applyLayout(is2D ? planar : flat);
  }, [is2D, flat, planar, runtime]);

  return (
    <>
      <StarfieldBackdrop />
      <TreeEdges edges={flat.edges} runtime={runtime} />
      <RootNode id={flat.rootId} runtime={runtime} controlsRef={controlsRef} />
      {PLANET_TYPES.map((type) =>
        flat.byType[type].length > 0 ? (
          <PlanetNodes key={type} nodes={flat.byType[type]} runtime={runtime} />
        ) : null,
      )}
      {flat.order.map((node) => (
        <NodeLabel key={node.id} node={node} runtime={runtime} />
      ))}
    </>
  );
}

function createStarfieldGeometry(): THREE.BufferGeometry {
  const positions = new Float32Array(SPACE.STAR_COUNT * 3);
  const sizes = new Float32Array(SPACE.STAR_COUNT);
  const phases = new Float32Array(SPACE.STAR_COUNT);
  const speeds = new Float32Array(SPACE.STAR_COUNT);

  for (let i = 0; i < SPACE.STAR_COUNT; i++) {
    const radius = THREE.MathUtils.lerp(
      SPACE.STAR_INNER_RADIUS,
      SPACE.STAR_OUTER_RADIUS,
      Math.cbrt(Math.random()),
    );
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(THREE.MathUtils.lerp(-1, 1, Math.random()));

    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = radius * Math.cos(phi);

    sizes[i] = THREE.MathUtils.lerp(0.6, 2.2, Math.random());
    phases[i] = Math.random() * Math.PI * 2;
    speeds[i] = THREE.MathUtils.lerp(0.4, 1.6, Math.random());
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
  geometry.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
  geometry.setAttribute("aSpeed", new THREE.BufferAttribute(speeds, 1));
  return geometry;
}

function StarfieldBackdrop() {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const [geometry] = useState(createStarfieldGeometry);
  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), []);

  useFrame((_, delta) => {
    if (materialRef.current) materialRef.current.uniforms.uTime.value += delta;
  });

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={starfieldVertexShader}
        fragmentShader={starfieldFragmentShader}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function TreeEdges({
  edges,
  runtime,
}: {
  edges: TreeEdge[];
  runtime: TreeRuntime;
}) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(edges.length * 6), 3),
    );
    return geo;
  }, [edges]);

  useFrame(() => {
    const positionAttr = geometry.getAttribute(
      "position",
    ) as THREE.BufferAttribute;
    const array = positionAttr.array as Float32Array;

    for (let i = 0; i < edges.length; i++) {
      const parentState = runtime.nodeStates.get(edges[i].parentId);
      const childState = runtime.nodeStates.get(edges[i].childId);
      if (!parentState || !childState) continue;

      const offset = i * 6;
      array[offset] = parentState.current.x;
      array[offset + 1] = parentState.current.y;
      array[offset + 2] = parentState.current.z;
      array[offset + 3] = childState.current.x;
      array[offset + 4] = childState.current.y;
      array[offset + 5] = childState.current.z;
    }
    positionAttr.needsUpdate = true;
  }, 1);

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial
        color={EDGE_COLOR}
        transparent
        opacity={0.55}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
        depthWrite={false}
      />
    </lineSegments>
  );
}

function PlanetNodes({
  nodes,
  runtime,
}: {
  nodes: FlatTreeNode[];
  runtime: TreeRuntime;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const visual = NODE_VISUALS[nodes[0].type];
  const uniforms = useMemo(
    () => ({
      uBaseColor: { value: new THREE.Color(visual.baseColor) },
      uBandColor: { value: new THREE.Color(visual.bandColor) },
      uGlowColor: { value: new THREE.Color(visual.glowColor) },
      uTime: { value: 0 },
    }),
    [visual],
  );

  useFrame((_, delta) => {
    const mesh = meshRef.current;
    if (mesh) {
      for (let i = 0; i < nodes.length; i++) {
        const state = runtime.nodeStates.get(nodes[i].id);
        if (!state) continue;
        dummy.position.copy(state.current);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
    if (materialRef.current) materialRef.current.uniforms.uTime.value += delta;
  }, 1);

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, nodes.length]}>
      <sphereGeometry args={[visual.radius, 32, 32]} />
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={nodeVertexShader}
        fragmentShader={planetFragmentShader}
        toneMapped={false}
      />
    </instancedMesh>
  );
}

function RootNode({
  id,
  runtime,
  controlsRef,
}: {
  id: string;
  runtime: TreeRuntime;
  controlsRef: OrbitControlsRef;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const [dragPlane, setDragPlane] = useState<{
    origin: THREE.Vector3;
    quaternion: THREE.Quaternion;
  } | null>(null);
  const { camera } = useThree();
  const visual = NODE_VISUALS.root;

  const uniforms = useMemo(
    () => ({
      uBaseColor: { value: new THREE.Color(visual.baseColor) },
      uBandColor: { value: new THREE.Color(visual.bandColor) },
      uGlowColor: { value: new THREE.Color(visual.glowColor) },
      uTime: { value: 0 },
    }),
    [visual],
  );

  useFrame((_, delta) => {
    const state = runtime.nodeStates.get(id);
    if (state && meshRef.current) meshRef.current.position.copy(state.current);
    if (materialRef.current) materialRef.current.uniforms.uTime.value += delta;
  }, 1);

  const endDrag = useCallback(() => {
    runtime.endDrag();
    if (controlsRef.current) controlsRef.current.enabled = true;
    setDragPlane(null);
  }, [runtime, controlsRef]);

  useEffect(() => {
    if (!dragPlane) return;
    window.addEventListener("pointerup", endDrag);
    return () => window.removeEventListener("pointerup", endDrag);
  }, [dragPlane, endDrag]);

  const handlePointerDown = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    const state = runtime.nodeStates.get(id);
    if (!state) return;
    setDragPlane({
      origin: state.current.clone(),
      quaternion: camera.quaternion.clone(),
    });
    runtime.beginDrag(id);
    if (controlsRef.current) controlsRef.current.enabled = false;
  };

  return (
    <>
      <mesh ref={meshRef} onPointerDown={handlePointerDown}>
        <sphereGeometry args={[visual.radius, 48, 48]} />
        <shaderMaterial
          ref={materialRef}
          uniforms={uniforms}
          vertexShader={nodeVertexShader}
          fragmentShader={starFragmentShader}
          toneMapped={false}
        />
      </mesh>
      {dragPlane && (
        <mesh
          position={dragPlane.origin}
          quaternion={dragPlane.quaternion}
          onPointerMove={(event) => runtime.updateDragPoint(event.point)}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <planeGeometry args={[1000, 1000]} />
          <meshBasicMaterial visible={false} />
        </mesh>
      )}
    </>
  );
}

/**
 * 노드 아래에 떠 있는 제목 태그. 위치와 투명도를 물리 상태에서 직접 갱신하므로
 * 리렌더 없이 드래그와 스프링 모션을 따라간다. 카메라가 멀어지면 타입별로 순서대로
 * 사라져(LABEL_FADE_DISTANCE) 줌아웃할 때 화면이 정리된다.
 */
function NodeLabel({
  node,
  runtime,
}: {
  node: FlatTreeNode;
  runtime: TreeRuntime;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const lastOpacityRef = useRef(-1);
  const visual = NODE_VISUALS[node.type];
  const fadeRange = LABEL_FADE_DISTANCE[node.type];
  const { camera } = useThree();

  useFrame(() => {
    const state = runtime.nodeStates.get(node.id);
    const wrapper = wrapperRef.current;
    if (!state || !groupRef.current || !wrapper) return;

    groupRef.current.position.copy(state.current);
    groupRef.current.position.y -= visual.radius + 0.35;

    const distance = camera.position.distanceTo(state.current);
    const opacity =
      1 - THREE.MathUtils.smoothstep(distance, fadeRange.start, fadeRange.end);

    // 대부분의 프레임에서 값이 그대로다. 매번 쓰면 라벨 수만큼 스타일 재계산이 걸린다
    if (Math.abs(opacity - lastOpacityRef.current) > 0.01) {
      lastOpacityRef.current = opacity;
      wrapper.style.opacity = opacity.toString();
      wrapper.style.display = opacity < 0.02 ? "none" : "block";
    }
  }, 1);

  const glowColor = visual.glowColor;

  return (
    <group ref={groupRef}>
      <Html
        center
        pointerEvents="none"
        style={{ pointerEvents: "none" }}
        zIndexRange={[10, 0]}
      >
        <div
          ref={wrapperRef}
          style={{
            // 0에서 시작해야 한다. 기본값 1이면 붙는 첫 프레임에 불투명하게 번쩍이고,
            // drei가 좌표를 잡기 전이라 화면 구석에 잠깐 찍히는 것까지 같이 보인다
            opacity: 0,
            textAlign: "center",
            pointerEvents: "none",
            userSelect: "none",
            transition: "opacity 0.18s linear",
          }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              margin: "0 auto 4px",
              borderRadius: "50%",
              background: glowColor,
              boxShadow: `0 0 6px 1px ${glowColor}`,
            }}
          />
          <div
            style={{
              display: "inline-block",
              width: "max-content",
              maxWidth: 160,
              padding: "3px 9px",
              borderRadius: 999,
              // backdrop-filter는 요소마다 뒤 배경을 다시 샘플링해 블러한다.
              // 캔버스 위에서 움직이는 라벨 100개에 걸면 합성 비용이 감당이 안 된다 —
              // 배경을 더 불투명하게 해서 같은 가독성을 얻는다
              background: "rgba(6, 8, 20, 0.82)",
              border: `1px solid ${glowColor}66`,
              color: "#f2f4ff",
              fontSize: 11,
              fontFamily: UI_FONT,
              letterSpacing: "0.01em",
              lineHeight: 1.35,
              textAlign: "center",
              whiteSpace: "normal",
              wordBreak: "keep-all",
              overflowWrap: "break-word",
            }}
          >
            {node.title}
          </div>
        </div>
      </Html>
    </group>
  );
}
