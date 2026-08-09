import { Html } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  ALWAYS_LABELED_TYPES,
  EDGE_COLOR,
  HOVER_SCALE,
  LABEL_FADE_DISTANCE,
  NODE_VISUALS,
  PICKED_BRIGHTNESS,
  PICK_MODE_BRIGHTNESS,
  SELECTION_BRIGHTNESS,
  SELECTION_LABEL_DIM,
  SPACE,
  UI_FONT,
  highlightFadeRange,
  type FlatTreeNode,
  type OrbitControlsRef,
  type PickMode,
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

/** 라벨 기본 z-index 범위 — 카메라에 가까운 라벨이 위로 온다. */
const LABEL_Z_RANGE: [number, number] = [10, 0];
/** 마우스를 올린 라벨은 거리와 무관하게 위로. 필터·범례 패널(20)보다는 낮아야 한다. */
const HOVERED_LABEL_Z = 15;

interface TreeSceneProps {
  /** 기본(3D) 배치 */
  flat: FlatTree;
  /** "펼쳐 보기"용 평면 배치 */
  planar: FlatTree;
  controlsRef: OrbitControlsRef;
  is2D: boolean;
  /** 선택된 결정과 연관된 노드 id. null이면 선택 없음 — 전부 기본 상태로 둔다. */
  highlightIds: Set<string> | null;
  onSelectDecision: (id: string) => void;
  /** 노드 고르기 모드 — 결정 클릭 대신 아무 노드나 삭제·수정 대상으로 고른다. */
  pickMode: PickMode | null;
  pickedIds: Set<string>;
  onTogglePick: (id: string) => void;
}

export function TreeScene({
  flat,
  planar,
  controlsRef,
  is2D,
  highlightIds,
  onSelectDecision,
  pickMode,
  pickedIds,
  onTogglePick,
}: TreeSceneProps) {
  const runtime = useTreeRuntime(flat);
  // 노드를 지날 때만 바뀌므로 state로 둬도 리렌더가 잦지 않다. 라벨까지 같이 강조해야 해서
  // PlanetNodes 안에 두지 않고 여기서 들고 있는다
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  // 목표만 바꾸면 스프링이 새 배치까지 끌고 간다 — 순간이동이 아니라 이동 모션이 된다
  useEffect(() => {
    runtime.applyLayout(is2D ? planar : flat);
  }, [is2D, flat, planar, runtime]);

  /**
   * 라벨은 개당 DOM 한 덩이라 노드 수만큼 붙이면 프레임이 무너진다.
   * 상위 타입만 항상 띄우고, 작업·이슈는 선택된 가지이거나 마우스를 올렸을 때만 붙인다.
   */
  const labelNodes = useMemo(
    () =>
      flat.order.filter(
        (node) =>
          ALWAYS_LABELED_TYPES.includes(node.type) ||
          highlightIds?.has(node.id) ||
          node.id === hoveredNodeId,
      ),
    [flat, highlightIds, hoveredNodeId],
  );

  return (
    <>
      <StarfieldBackdrop />
      <TreeEdges
        edges={flat.edges}
        runtime={runtime}
        highlightIds={highlightIds}
      />
      <RootNode
        id={flat.rootId}
        runtime={runtime}
        controlsRef={controlsRef}
        highlightIds={highlightIds}
        onHover={setHoveredNodeId}
        pickMode={pickMode}
      />
      {PLANET_TYPES.map((type) =>
        flat.byType[type].length > 0 ? (
          <PlanetNodes
            key={type}
            nodes={flat.byType[type]}
            runtime={runtime}
            highlightIds={highlightIds}
            /*
             * 평소 클릭 대상은 결정 노드뿐이다. 고르기 모드에서는 실제 그래프 노드
             * (결정·작업·이슈)를 모두 고를 수 있다 — 카테고리는 서버가 만드는
             * 묶음이라 지우지도 고치지도 못한다.
             */
            onSelect={
              pickMode
                ? type === "category"
                  ? undefined
                  : onTogglePick
                : type === "decision"
                  ? onSelectDecision
                  : undefined
            }
            pickMode={pickMode}
            pickedIds={pickedIds}
            // hover는 전 타입에서 받는다 — 라벨을 펼치는 신호라서.
            // 포인터가 움직일 때마다 타입별 인스턴스를 레이캐스팅하게 되지만,
            // 인스턴스당 경계구 판정이라 삼각형 검사까지 가는 건 실제로 맞은 하나뿐이다
            hoveredId={hoveredNodeId}
            onHover={setHoveredNodeId}
          />
        ) : null,
      )}
      {labelNodes.map((node) => (
        <NodeLabel
          key={node.id}
          node={node}
          runtime={runtime}
          highlightIds={highlightIds}
          hovered={node.id === hoveredNodeId}
        />
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
  highlightIds,
}: {
  edges: TreeEdge[];
  runtime: TreeRuntime;
  highlightIds: Set<string> | null;
}) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(edges.length * 6), 3),
    );
    // 선 전체가 머티리얼 하나라 선마다 밝기를 다르게 하려면 정점 색이 유일한 수단이다
    geo.setAttribute(
      "color",
      new THREE.BufferAttribute(new Float32Array(edges.length * 6).fill(1), 3),
    );
    return geo;
  }, [edges]);

  // 선택이 바뀔 때만 칠한다 — 위치와 달리 매 프레임 다시 쓸 값이 아니다
  useEffect(() => {
    const colorAttr = geometry.getAttribute("color") as THREE.BufferAttribute;
    const array = colorAttr.array as Float32Array;

    for (let i = 0; i < edges.length; i++) {
      // 양끝이 모두 연관된 선만 살린다 — 한쪽만 걸친 선을 살리면 강조 범위가 번져 보인다
      const lit =
        !highlightIds ||
        (highlightIds.has(edges[i].parentId) &&
          highlightIds.has(edges[i].childId));
      array.fill(lit ? 1 : SELECTION_BRIGHTNESS.DIM, i * 6, i * 6 + 6);
    }
    colorAttr.needsUpdate = true;
  }, [edges, geometry, highlightIds]);

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
    // 정점을 매 프레임 갈아끼우는데 three는 경계구를 한 번만 계산해 캐시한다 —
    // 배치가 바뀌면 그 구가 실제 선들과 어긋나 선 전체가 통째로 컬링된다.
    // 어차피 트리 전체를 덮는 draw call 하나라 컬링해서 얻을 것도 없다
    <lineSegments geometry={geometry} frustumCulled={false}>
      <lineBasicMaterial
        color={EDGE_COLOR}
        vertexColors
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
  highlightIds,
  onSelect,
  hoveredId,
  onHover,
  pickMode,
  pickedIds,
}: {
  nodes: FlatTreeNode[];
  runtime: TreeRuntime;
  highlightIds: Set<string> | null;
  onSelect?: (id: string) => void;
  hoveredId: string | null;
  onHover?: (id: string | null) => void;
  pickMode: PickMode | null;
  /** 고른 노드 — 삭제 모드면 셰이더에서 회색으로 죽고, 수정 모드면 더 밝아진다. */
  pickedIds: Set<string>;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const brightnessRef = useRef<THREE.InstancedBufferAttribute>(null);
  const deadRef = useRef<THREE.InstancedBufferAttribute>(null);
  const pressPointRef = useRef<{ x: number; y: number } | null>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const visual = NODE_VISUALS[nodes[0].type];
  const uniforms = useMemo(
    () => ({
      uBaseColor: { value: new THREE.Color(visual.baseColor) },
      uBandColor: { value: new THREE.Color(visual.bandColor) },
      uGlowColor: { value: new THREE.Color(visual.glowColor) },
      uTime: { value: 0 },
      uBrightness: { value: 1 },
      // 인스턴싱 쪽은 aDead를 쓰지만, 셰이더가 root와 공용이라 선언은 채워 둔다
      uDead: { value: 0 },
    }),
    [visual],
  );

  const brightness = useMemo(
    () => new Float32Array(nodes.length).fill(1),
    [nodes],
  );

  const dead = useMemo(() => new Float32Array(nodes.length), [nodes]);

  useEffect(() => {
    const attr = deadRef.current;
    if (!attr) return;

    const array = attr.array as Float32Array;
    for (let i = 0; i < nodes.length; i++) {
      // 죽이는 건 삭제뿐이다 — 수정 대상은 밝기로만 구분한다
      array[i] =
        pickMode === "delete" && pickedIds.has(nodes[i].id) ? 1 : 0;
    }
    attr.needsUpdate = true;
  }, [nodes, pickMode, pickedIds]);

  // 크기와 밝기를 매 프레임 비교하지 않도록 인덱스로 한 번 찾아둔다
  const hoveredIndex = useMemo(
    () => (hoveredId ? nodes.findIndex((node) => node.id === hoveredId) : -1),
    [nodes, hoveredId],
  );
  // 키우고 밝히는 건 "누를 수 있다"는 신호다 — 클릭 대상이 아닌 타입은 라벨만 펼친다
  const emphasizedIndex = onSelect ? hoveredIndex : -1;

  useEffect(() => {
    const attr = brightnessRef.current;
    if (!attr) return;

    const array = attr.array as Float32Array;
    for (let i = 0; i < nodes.length; i++) {
      array[i] =
        i === emphasizedIndex
          ? SELECTION_BRIGHTNESS.HOVER
          : // 고르기 모드에서는 전체를 고르게 밝힌다 — 결정 선택 강조와 섞이면 신호가 흐려진다.
            // 수정 대상으로 고른 노드만 그 위로 한 단계 더 올려 구분한다
            pickMode
            ? pickMode === "edit" && pickedIds.has(nodes[i].id)
              ? PICKED_BRIGHTNESS
              : PICK_MODE_BRIGHTNESS
            : !highlightIds
              ? 1
              : highlightIds.has(nodes[i].id)
                ? SELECTION_BRIGHTNESS.HIGHLIGHT
                : SELECTION_BRIGHTNESS.DIM;
    }
    attr.needsUpdate = true;
  }, [nodes, highlightIds, emphasizedIndex, pickMode, pickedIds]);

  /**
   * 클릭 판정용 경계구. three는 이 구를 한 번 계산해 캐시하는데 인스턴스는 매 프레임
   * 움직이므로, 캐시된 구 밖으로 나간 노드는 판정에서 아예 빠진다.
   * 넉넉한 구를 직접 박아 넣어 정확한 인스턴스별 판정으로 넘긴다.
   *
   * nodes가 의존성에 있어야 한다 — 필터로 노드 수가 바뀌면 R3F가 InstancedMesh를
   * 새로 만들고, 그 메시는 경계구가 비어 있어 다시 캐시가 잡힌다.
   */
  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    mesh.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e4);

    // 메시가 교체되면 onPointerOut이 오지 않아 커서가 손 모양으로 남는다
    return () => {
      document.body.style.cursor = "auto";
    };
  }, [nodes]);

  const handleClick = (event: ThreeEvent<MouseEvent>) => {
    const press = pressPointRef.current;
    pressPointRef.current = null;
    if (!onSelect || event.instanceId === undefined) return;

    // 카메라를 돌리다 노드 위에서 손을 뗀 것은 선택이 아니다
    if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 4) {
      return;
    }

    event.stopPropagation();
    onSelect(nodes[event.instanceId].id);
  };

  useFrame((_, delta) => {
    const mesh = meshRef.current;
    if (mesh) {
      for (let i = 0; i < nodes.length; i++) {
        const state = runtime.nodeStates.get(nodes[i].id);
        if (!state) continue;
        dummy.position.copy(state.current);
        // dummy를 공유하므로 매번 다시 써야 한다 — 안 그러면 배율이 다음 노드로 번진다
        dummy.scale.setScalar(i === emphasizedIndex ? HOVER_SCALE : 1);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
    if (materialRef.current) materialRef.current.uniforms.uTime.value += delta;
  }, 1);

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, nodes.length]}
      // 캐시된 경계구가 실제 인스턴스 위치와 어긋나 타입 하나가 통째로 사라지는 것을 막는다.
      // 타입별 draw call 하나뿐이라 컬링을 켜도 이득이 없다
      frustumCulled={false}
      onPointerDown={
        onSelect
          ? (event) =>
              (pressPointRef.current = {
                x: event.clientX,
                y: event.clientY,
              })
          : undefined
      }
      onClick={onSelect ? handleClick : undefined}
      // 인스턴스 메시는 노드 사이를 옮겨도 out/over가 오지 않는다 — 어느 노드 위인지는
      // move로 계속 따라가야 한다
      onPointerMove={
        onHover
          ? (event) => {
              if (event.instanceId === undefined) return;
              // 타입마다 메시가 따로라 뒤에 겹친 노드까지 핸들러가 돈다. stopPropagation으로
              // 막으면 R3F가 뒤쪽 객체에 out/leave를 쏴버려서(루트 드래그 판이 그걸 맞으면
              // 드래그가 끊긴다) 대신 가장 가까운 교차일 때만 hover를 잡는다
              const nearest = event.intersections[0];
              if (
                nearest?.object !== event.object ||
                nearest.instanceId !== event.instanceId
              ) {
                return;
              }
              onHover(nodes[event.instanceId].id);
            }
          : undefined
      }
      onPointerOver={
        onSelect ? () => (document.body.style.cursor = "pointer") : undefined
      }
      onPointerOut={() => {
        if (onSelect) document.body.style.cursor = "auto";
        onHover?.(null);
      }}
    >
      <sphereGeometry args={[visual.radius, 32, 32]}>
        <instancedBufferAttribute
          ref={brightnessRef}
          attach="attributes-aBrightness"
          args={[brightness, 1]}
        />
        <instancedBufferAttribute
          ref={deadRef}
          attach="attributes-aDead"
          args={[dead, 1]}
        />
      </sphereGeometry>
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
  highlightIds,
  onHover,
  pickMode,
}: {
  id: string;
  runtime: TreeRuntime;
  controlsRef: OrbitControlsRef;
  highlightIds: Set<string> | null;
  onHover: (id: string | null) => void;
  pickMode: PickMode | null;
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
      uBrightness: { value: 1 },
      // 루트는 고르기 대상이 아니라 항상 0이다 — 셰이더가 선언을 요구해서 채워 둔다
      uDead: { value: 0 },
    }),
    [visual],
  );

  // 루트는 인스턴싱이 아니라 uniform 하나로 끝난다
  const brightness = pickMode
    ? PICK_MODE_BRIGHTNESS
    : !highlightIds
      ? 1
      : highlightIds.has(id)
        ? SELECTION_BRIGHTNESS.HIGHLIGHT
        : SELECTION_BRIGHTNESS.DIM;

  useFrame((_, delta) => {
    const state = runtime.nodeStates.get(id);
    if (state && meshRef.current) meshRef.current.position.copy(state.current);
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value += delta;
      materialRef.current.uniforms.uBrightness.value = brightness;
    }
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
      <mesh
        ref={meshRef}
        onPointerDown={handlePointerDown}
        // 행성 메시와 같은 규칙 — 가장 가까운 교차일 때만 hover를 잡는다.
        // 드래그 중에는 좌표를 받는 판이 이 구 바로 뒤에 있으므로 절대 막지 않는다
        onPointerMove={(event) => {
          if (event.intersections[0]?.object !== event.object) return;
          onHover(id);
        }}
        onPointerOut={() => onHover(null)}
      >
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
  highlightIds,
  hovered,
}: {
  node: FlatTreeNode;
  runtime: TreeRuntime;
  highlightIds: Set<string> | null;
  hovered: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const lastOpacityRef = useRef(-1);
  // hover로 z-index를 올리기 전 값. 뗄 때 drei가 쓰던 값으로 돌려놔야 한다
  const restoreZRef = useRef<string | null>(null);
  const visual = NODE_VISUALS[node.type];
  const emphasized = (highlightIds?.has(node.id) ?? false) || hovered;
  // 마우스를 올린 노드는 어둡게 깔린 상태에서도 제 밝기로 올라와야 한다
  const dimmed = highlightIds !== null && !emphasized;
  const fadeRange = emphasized
    ? highlightFadeRange(node.type)
    : LABEL_FADE_DISTANCE[node.type];
  const { camera } = useThree();

  useFrame(() => {
    const state = runtime.nodeStates.get(node.id);
    const wrapper = wrapperRef.current;
    if (!state || !groupRef.current || !wrapper) return;

    groupRef.current.position.copy(state.current);
    groupRef.current.position.y -= visual.radius + 0.35;

    const distance = camera.position.distanceTo(state.current);
    const opacity =
      (1 -
        THREE.MathUtils.smoothstep(distance, fadeRange.start, fadeRange.end)) *
      (dimmed ? SELECTION_LABEL_DIM : 1);

    // 대부분의 프레임에서 값이 그대로다. 매번 쓰면 라벨 수만큼 스타일 재계산이 걸린다
    if (Math.abs(opacity - lastOpacityRef.current) > 0.01) {
      lastOpacityRef.current = opacity;
      wrapper.style.opacity = opacity.toString();
      wrapper.style.display = opacity < 0.02 ? "none" : "block";
    }

    // drei는 라벨이 화면에서 움직였을 때만 z-index를 다시 쓴다(Html.js). 카메라가 멈춘 채
    // 마우스만 올리면 zIndexRange를 바꿔도 반영되지 않으므로 여기서 직접 올린다
    const layer = wrapper.parentElement;
    if (layer) {
      if (hovered && restoreZRef.current === null) {
        restoreZRef.current = layer.style.zIndex;
        layer.style.zIndex = String(HOVERED_LABEL_Z);
      } else if (!hovered && restoreZRef.current !== null) {
        layer.style.zIndex = restoreZRef.current;
        restoreZRef.current = null;
      }
    }
  }, 1);

  const glowColor = visual.glowColor;
  // 제목이 길면 라벨이 여러 줄로 부풀어 트리를 가린다 — 평소엔 한 줄로 자르고,
  // 마우스를 올린 노드에서만 전체를 펼친다
  const titleClamp = hovered
    ? ({
        whiteSpace: "normal",
        wordBreak: "keep-all",
        overflowWrap: "break-word",
      } as const)
    : ({
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
      } as const);

  return (
    <group ref={groupRef}>
      <Html
        center
        pointerEvents="none"
        style={{ pointerEvents: "none" }}
        zIndexRange={
          hovered ? [HOVERED_LABEL_Z, HOVERED_LABEL_Z] : LABEL_Z_RANGE
        }
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
              maxWidth: hovered ? 260 : 160,
              padding: "3px 9px",
              borderRadius: 999,
              // backdrop-filter는 요소마다 뒤 배경을 다시 샘플링해 블러한다.
              // 캔버스 위에서 움직이는 라벨 100개에 걸면 합성 비용이 감당이 안 된다 —
              // 배경을 더 불투명하게 해서 같은 가독성을 얻는다
              // 올린 라벨은 완전 불투명 — 밑에 깔린 라벨이 비쳐 보이면 위로 올린 의미가 없다
              background: hovered ? "rgb(6, 8, 20)" : "rgba(6, 8, 20, 0.82)",
              border: `1px solid ${glowColor}${emphasized ? "cc" : "66"}`,
              boxShadow: emphasized ? `0 0 10px ${glowColor}55` : undefined,
              color: "#f2f4ff",
              fontSize: 11,
              fontFamily: UI_FONT,
              letterSpacing: "0.01em",
              lineHeight: 1.35,
              textAlign: "center",
              ...titleClamp,
            }}
          >
            {node.title}
          </div>
        </div>
      </Html>
    </group>
  );
}
