# 우주 3D 트리(SpaceTree) 이식 가이드

이 문서 하나만 있으면 다른 프로젝트에 **똑같은 우주 3D 트리 환경**을 그대로 만들 수 있다.
아래 순서대로 그대로 따라 하면 된다. 파일 7개를 만들고, 컴포넌트 하나를 붙이면 끝이다.

## 완성되는 것

- 검은 우주 배경 + 반짝이는 별 6000개 (전부 셰이더로 처리, JS 비용 거의 0)
- 중앙의 빛나는 별(root) + 궤도처럼 퍼진 행성 노드들 (decision / task / issue)
- 부모–자식을 잇는 발광 선(edge)
- **root를 드래그하면 자식들이 스프링으로 줄줄이 따라오는 젤리 체인 모션**
- 노드마다 떠 있는 HTML 라벨 — 카메라가 멀어지면 깊은 타입부터 순서대로 사라짐
- 마우스 커서 기준 확대/축소, 우클릭 팬, 우하단 줌 슬라이더
- 우상단 2D/3D 전환 버튼 (2D는 회전을 잠그고 정면 뷰로 고정)
- Bloom 후처리로 발광 표현

---

## 1. 요구사항

- React 18 이상 (19 권장) + TypeScript
- 번들러는 Vite / Next.js / CRA 무엇이든 상관없음 (아래 "프레임워크별 주의" 참고)

## 2. 패키지 설치

```bash
npm install three @react-three/fiber @react-three/drei @react-three/postprocessing three-stdlib
```

> `@types/three`는 설치하지 않는다. 최신 `three`는 타입을 자체 포함하고 있어서
> 오히려 충돌한다.

검증된 조합 (이 버전대면 그대로 동작한다):

| 패키지                        | 버전     |
| ----------------------------- | -------- |
| `three`                       | ^0.185.1 |
| `@react-three/fiber`          | ^9.6.1   |
| `@react-three/drei`           | ^10.7.7  |
| `@react-three/postprocessing` | ^3.0.4   |
| `three-stdlib`                | ^2.36.1  |
| `react` / `react-dom`         | ^19.2.7  |

> `three-stdlib`은 OrbitControls **타입**용이다. drei가 내부적으로 이미 쓰지만,
> 직접 import 하므로 package.json에 명시적으로 넣는다.
> React 18을 쓴다면 `@react-three/fiber@8`, `@react-three/drei@9` 계열을 설치할 것.

## 3. 파일 구조

프로젝트에 `src/spacetree/` 폴더를 만들고 아래 7개 파일을 그대로 생성한다.

```
src/spacetree/
├── config.ts       # 타입 + 모든 수치/색상 (튜닝은 전부 여기서)
├── treeEngine.ts   # 레이아웃 계산 + 스프링 물리 런타임
├── shaders.ts      # GLSL (행성 / 별 / 별가루 배경)
├── TreeScene.tsx   # <Canvas> 안쪽 전부 (배경, 엣지, 노드, 라벨)
├── SpaceTree.tsx   # <Canvas> + 카메라/컨트롤 + 오버레이 UI  ← 진입점
├── treeData.ts     # 샘플 데이터 (본인 데이터로 교체)
└── index.ts        # 공개 export
```

의존 방향은 한 방향으로만 흐른다:

```
index.ts → SpaceTree.tsx → TreeScene.tsx → treeEngine.ts → config.ts
                                        ↘ shaders.ts    ↗
```

---

## 4. 전체 코드

아래 7개 파일을 **내용 그대로** 복사한다. 수정할 필요 없다.

### 4-1. `src/spacetree/config.ts`

```ts
import type { Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

/* ------------------------------------------------------------------ *
 * Types
 * ------------------------------------------------------------------ */

export type NodeType = "root" | "decision" | "task" | "issue";

/** Raw authoring data — no layout information. This is what you feed `<SpaceTree data={...} />`. */
export interface TreeNodeInput {
  id: string;
  type: NodeType;
  title: string;
  children?: TreeNodeInput[];
}

/**
 * A node after layout. `localOffset` is relative to the parent (not world
 * space) — the physics runtime adds it to the parent's *live* position every
 * frame, which is what produces the trailing "jelly chain" motion.
 */
export interface FlatTreeNode {
  id: string;
  type: NodeType;
  title: string;
  parentId?: string;
  localOffset: Vector3;
}

export interface TreeEdge {
  parentId: string;
  childId: string;
}

/** Shorthand for the OrbitControls ref threaded through the scene. */
export type OrbitControlsRef = React.RefObject<OrbitControlsImpl | null>;

/* ------------------------------------------------------------------ *
 * Look & feel — everything tunable lives below this line.
 * ------------------------------------------------------------------ */

export interface NodeVisual {
  radius: number;
  /** Base surface tone. */
  baseColor: string;
  /** Secondary tone used for bands (planets) or core flicker mix (star). */
  bandColor: string;
  /** Fresnel rim / corona tint. */
  glowColor: string;
}

export const NODE_VISUALS: Record<NodeType, NodeVisual> = {
  root: {
    radius: 1.2,
    baseColor: "#a855f7",
    bandColor: "#f5d0fe",
    glowColor: "#e879f9",
  },
  decision: {
    radius: 0.8,
    baseColor: "#3b6fdd",
    bandColor: "#8fd6ff",
    glowColor: "#4f8dff",
  },
  task: {
    radius: 0.6,
    baseColor: "#178f7c",
    bandColor: "#7dffe0",
    glowColor: "#2fe6c8",
  },
  issue: {
    radius: 0.4,
    baseColor: "#dc2626",
    bandColor: "#fee2e2",
    glowColor: "#f87171",
  },
};

export interface SpringConfig {
  stiffness: number;
  damping: number;
}

/** Softer & wobblier further from the root, so the lag cascades down the tree. */
export const SPRING_BY_TYPE: Record<NodeType, SpringConfig> = {
  root: { stiffness: 130, damping: 16 },
  decision: { stiffness: 70, damping: 9 },
  task: { stiffness: 48, damping: 7 },
  issue: { stiffness: 34, damping: 5.5 },
};

/** Base radius of the circle a parent's children are placed on. */
export const CHILD_RING_BASE_RADIUS = 2.4;
/** Extra radius added per child beyond 3, so crowded parents spread wider. */
export const CHILD_RING_RADIUS_PER_EXTRA_CHILD = 0.75;

export const EDGE_COLOR = "#7fd8ff";

export interface LabelFadeRange {
  /** Camera distance at which the label starts fading out. */
  start: number;
  /** Camera distance at which the label is fully invisible. */
  end: number;
}

/**
 * As the camera pulls back, deeper node types fade out first (issue → task →
 * decision → root), so the tree declutters progressively instead of turning
 * into a wall of text once it grows large. `issue.start` sits above the
 * initial camera distance (~26) so nothing fades at the opening view, and
 * `root.end` sits comfortably *below* `CAMERA.MAX_DISTANCE` — with real
 * margin, not right at the cap — so the root label reliably disappears well
 * before you hit full zoom-out.
 */
export const LABEL_FADE_DISTANCE: Record<NodeType, LabelFadeRange> = {
  issue: { start: 27, end: 36 },
  task: { start: 36, end: 45 },
  decision: { start: 46, end: 54 },
  root: { start: 55, end: 62 },
};

export const CAMERA = {
  INITIAL_POSITION: [10, 8, 22] as [number, number, number],
  FOV: 50,
  MIN_DISTANCE: 6,
  MAX_DISTANCE: 70,
  /** Distance added/removed by one click of the zoom +/- buttons. */
  ZOOM_STEP: 2,
};

export const SPACE = {
  BACKGROUND_COLOR: "#000006",
  FOG_DENSITY: 0.006,
  STAR_COUNT: 6000,
  /** Stars are scattered in the shell between these two radii. */
  STAR_INNER_RADIUS: 60,
  STAR_OUTER_RADIUS: 400,
};

export const UI_FONT =
  "'Pretendard', 'Segoe UI', system-ui, -apple-system, sans-serif";
/** Glass-panel styling shared by the overlay buttons. */
export const UI_SURFACE = {
  border: "1px solid rgba(127, 216, 255, 0.4)",
  background: "rgba(6, 8, 20, 0.55)",
  backdropFilter: "blur(3px)",
  color: "#f2f4ff",
};
```

### 4-2. `src/spacetree/shaders.ts`

```ts
/* ------------------------------------------------------------------ *
 * Node shaders (root star + planet spheres)
 * ------------------------------------------------------------------ */

/**
 * Shared vertex shader for both the star (root, plain Mesh) and the planet
 * spheres (decision/task/issue, InstancedMesh). `USE_INSTANCING` is defined
 * automatically by three.js only when the material is attached to an
 * InstancedMesh, so one source works for both without a branch at the call site.
 */
export const nodeVertexShader = /* glsl */ `
  varying vec3 vLocalPos;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;

  void main() {
    vLocalPos = position;

    #ifdef USE_INSTANCING
      vec4 worldPos = instanceMatrix * vec4(position, 1.0);
      vec3 worldNormal = normalize(mat3(instanceMatrix) * normal);
    #else
      vec4 worldPos = vec4(position, 1.0);
      vec3 worldNormal = normalize(normal);
    #endif

    vWorldNormal = worldNormal;
    vWorldPos = worldPos.xyz;

    vec4 mvPosition = modelViewMatrix * worldPos;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const noiseFn = /* glsl */ `
  float hash(vec3 p) {
    return fract(sin(dot(p, vec3(12.9898, 78.233, 45.164))) * 43758.5453);
  }

  float noise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash(i);
    float n100 = hash(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash(i + vec3(1.0, 1.0, 1.0));
    return mix(
      mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
      mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y),
      f.z
    );
  }
`;

/** Two-tone banded surface + a fresnel atmosphere rim — reads as a small glowing planet. */
export const planetFragmentShader = /* glsl */ `
  uniform vec3 uBaseColor;
  uniform vec3 uBandColor;
  uniform vec3 uGlowColor;
  uniform float uTime;

  varying vec3 vLocalPos;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;

  ${noiseFn}

  void main() {
    vec3 normal = normalize(vWorldNormal);
    vec3 viewDir = normalize(cameraPosition - vWorldPos);

    vec3 spinPos = vLocalPos;
    float angle = uTime * 0.15;
    spinPos.xz = mat2(cos(angle), -sin(angle), sin(angle), cos(angle)) * spinPos.xz;

    float bandNoise = noise(spinPos * 2.5);
    float bands = sin(spinPos.y * 4.0 + bandNoise * 2.2) * 0.5 + 0.5;
    vec3 surfaceColor = mix(uBaseColor, uBandColor, bands * 0.5 + bandNoise * 0.15);

    float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 2.5);
    vec3 color = surfaceColor + uGlowColor * fresnel * 1.3;

    gl_FragColor = vec4(color, 1.0);
  }
`;

/** Bright flickering core + a wide corona — reads as a small star/sun. */
export const starFragmentShader = /* glsl */ `
  uniform vec3 uBaseColor;
  uniform vec3 uBandColor;
  uniform vec3 uGlowColor;
  uniform float uTime;

  varying vec3 vLocalPos;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;

  ${noiseFn}

  void main() {
    vec3 normal = normalize(vWorldNormal);
    vec3 viewDir = normalize(cameraPosition - vWorldPos);

    float flicker = noise(vLocalPos * 3.0 + vec3(0.0, 0.0, uTime * 0.7));
    float surfaceGlow = 0.8 + 0.45 * flicker;
    vec3 core = mix(uBaseColor, uBandColor, flicker * 0.4) * surfaceGlow;

    float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 1.8);
    vec3 color = core + uGlowColor * fresnel * 2.1;

    gl_FragColor = vec4(color, 1.0);
  }
`;

/* ------------------------------------------------------------------ *
 * Starfield backdrop
 * ------------------------------------------------------------------ */

export const starfieldVertexShader = /* glsl */ `
  attribute float aSize;
  attribute float aPhase;
  attribute float aSpeed;
  varying float vPhase;
  varying float vSpeed;
  void main() {
    vPhase = aPhase;
    vSpeed = aSpeed;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    gl_PointSize = aSize * (300.0 / -mvPosition.z);
  }
`;

export const starfieldFragmentShader = /* glsl */ `
  uniform float uTime;
  varying float vPhase;
  varying float vSpeed;
  void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float dist = length(centered);
    if (dist > 0.5) discard;
    float circle = smoothstep(0.5, 0.0, dist);
    float twinkle = 0.5 + 0.5 * sin(uTime * vSpeed + vPhase);
    float alpha = circle * mix(0.35, 1.0, twinkle);
    vec3 color = mix(vec3(0.75, 0.82, 1.0), vec3(1.0), twinkle);
    gl_FragColor = vec4(color, alpha);
  }
`;
```

### 4-3. `src/spacetree/treeEngine.ts`

```ts
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Vector3 } from "three";
import {
  CHILD_RING_BASE_RADIUS,
  CHILD_RING_RADIUS_PER_EXTRA_CHILD,
  NODE_VISUALS,
  SPRING_BY_TYPE,
  type FlatTreeNode,
  type NodeType,
  type TreeEdge,
  type TreeNodeInput,
} from "./config";

/* ------------------------------------------------------------------ *
 * 1. Layout — nested authoring data → flat draw-ready arrays
 * ------------------------------------------------------------------ */

export interface FlatTree {
  rootId: string;
  /** Top-down order: a parent always appears before its children. */
  order: FlatTreeNode[];
  byType: Record<NodeType, FlatTreeNode[]>;
  edges: TreeEdge[];
}

const TAU = Math.PI * 2;

/** Deterministic 0..1 hash, so each parent's ring gets a stable-but-varied rotation. */
function hash01(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0;
  }
  return (h % 1000) / 1000;
}

function ringRadius(parentType: NodeType, childCount: number): number {
  const extra = Math.max(0, childCount - 3) * CHILD_RING_RADIUS_PER_EXTRA_CHILD;
  return CHILD_RING_BASE_RADIUS + NODE_VISUALS[parentType].radius + extra;
}

/**
 * Builds a radial ("mind-map") layout in a single pass: each node's children
 * are spread evenly around a circle centred on it, with the ring radius
 * growing with the child count, plus a little Z jitter so the tree doesn't
 * read as flat. Each node keeps only its offset *from its parent*; the runtime
 * turns those into world positions every frame.
 */
export function buildTree(input: TreeNodeInput): FlatTree {
  const order: FlatTreeNode[] = [];
  const edges: TreeEdge[] = [];
  const byType: Record<NodeType, FlatTreeNode[]> = {
    root: [],
    decision: [],
    task: [],
    issue: [],
  };

  const visit = (
    node: TreeNodeInput,
    worldPos: Vector3,
    parent: { id: string; worldPos: Vector3 } | undefined,
  ) => {
    const flat: FlatTreeNode = {
      id: node.id,
      type: node.type,
      title: node.title,
      parentId: parent?.id,
      localOffset: parent
        ? worldPos.clone().sub(parent.worldPos)
        : worldPos.clone(),
    };
    order.push(flat);
    byType[node.type].push(flat);
    if (parent) edges.push({ parentId: parent.id, childId: node.id });

    const children = node.children ?? [];
    if (children.length === 0) return;

    const radius = ringRadius(node.type, children.length);
    const rotationOffset = hash01(node.id) * TAU;

    children.forEach((child, index) => {
      const angle = rotationOffset + (TAU * index) / children.length;
      const zJitter =
        Math.sin(angle * 2 + hash01(child.id) * 10) * radius * 0.18;
      const childWorldPos = new Vector3(
        worldPos.x + Math.cos(angle) * radius,
        worldPos.y + Math.sin(angle) * radius,
        worldPos.z + zJitter,
      );
      visit(child, childWorldPos, { id: node.id, worldPos });
    });
  };

  visit(input, new Vector3(0, 0, 0), undefined);

  return { rootId: input.id, order, byType, edges };
}

/* ------------------------------------------------------------------ *
 * 2. Runtime — spring physics shared by every renderer in the scene
 * ------------------------------------------------------------------ */

export interface NodeRuntimeState {
  id: string;
  type: NodeType;
  parentId?: string;
  localOffset: Vector3;
  /** Live world position, mutated in place each frame. */
  current: Vector3;
  velocity: Vector3;
}

export interface TreeRuntime {
  nodeStates: Map<string, NodeRuntimeState>;
  order: string[];
  beginDrag: (id: string) => void;
  updateDragPoint: (point: Vector3) => void;
  endDrag: () => void;
}

/** Clamp the physics step so a stalled tab can't explode the simulation. */
const MAX_DELTA = 1 / 30;

/**
 * Owns the spring simulation for the whole tree. Every node springs toward
 * (parent's live position + its fixed local offset); the dragged node springs
 * toward the pointer instead. Because each level's target depends on the level
 * above's *already-lagging* position, the trailing follow effect falls out of
 * the recursion for free — no per-level special-casing.
 *
 * Nothing here goes through React state: positions are mutated in place and
 * read by the renderers in their own `useFrame`, so a 60fps simulation costs
 * zero re-renders.
 */
export function useTreeRuntime(flat: FlatTree): TreeRuntime {
  const nodeStates = useMemo(() => {
    const states = new Map<string, NodeRuntimeState>();
    // `flat.order` is top-down, so a parent's start position is always known.
    for (const node of flat.order) {
      const parentState = node.parentId ? states.get(node.parentId) : undefined;
      const worldPos = parentState
        ? parentState.current.clone().add(node.localOffset)
        : node.localOffset.clone();
      states.set(node.id, {
        id: node.id,
        type: node.type,
        parentId: node.parentId,
        localOffset: node.localOffset,
        current: worldPos,
        velocity: new Vector3(),
      });
    }
    return states;
  }, [flat]);

  const order = useMemo(() => flat.order.map((n) => n.id), [flat]);

  const draggingIdRef = useRef<string | null>(null);
  const dragTargetRef = useRef(new Vector3());

  const targetScratch = useRef(new Vector3()).current;
  const forceScratch = useRef(new Vector3()).current;

  // Priority 0: run before every renderer's useFrame(…, 1) below.
  useFrame((_, rawDelta) => {
    const dt = Math.min(rawDelta, MAX_DELTA);
    for (const id of order) {
      const state = nodeStates.get(id)!;

      let target: Vector3;
      if (id === draggingIdRef.current) {
        target = dragTargetRef.current;
      } else if (state.parentId) {
        const parentState = nodeStates.get(state.parentId)!;
        target = targetScratch.copy(parentState.current).add(state.localOffset);
      } else {
        target = state.current; // free root: stays wherever it was left
      }

      const { stiffness, damping } = SPRING_BY_TYPE[state.type];
      forceScratch
        .copy(target)
        .sub(state.current)
        .multiplyScalar(stiffness)
        .addScaledVector(state.velocity, -damping);

      state.velocity.addScaledVector(forceScratch, dt);
      state.current.addScaledVector(state.velocity, dt);
    }
  }, 0);

  return {
    nodeStates,
    order,
    beginDrag: (id) => {
      draggingIdRef.current = id;
      const state = nodeStates.get(id);
      if (state) dragTargetRef.current.copy(state.current);
    },
    updateDragPoint: (point) => dragTargetRef.current.copy(point),
    endDrag: () => {
      draggingIdRef.current = null;
    },
  };
}
```

### 4-4. `src/spacetree/TreeScene.tsx`

```tsx
import { Html } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
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
  type TreeNodeInput,
} from "./config";
import {
  nodeVertexShader,
  planetFragmentShader,
  starFragmentShader,
  starfieldFragmentShader,
  starfieldVertexShader,
} from "./shaders";
import { buildTree, useTreeRuntime, type TreeRuntime } from "./treeEngine";

/* ==================================================================== *
 * TreeScene — everything that lives *inside* the <Canvas>.
 *
 * Rendering rule for the whole file: node positions are owned by the spring
 * runtime and copied into three.js objects inside `useFrame`. Nothing here
 * stores a position in React state, so the tree animates at 60fps without a
 * single re-render. All renderers use priority 1 so they read positions the
 * runtime (priority 0) already advanced this frame.
 * ==================================================================== */

const PLANET_TYPES = ["decision", "task", "issue"] as const;

interface TreeSceneProps {
  data: TreeNodeInput;
  controlsRef: OrbitControlsRef;
}

export function TreeScene({ data, controlsRef }: TreeSceneProps) {
  const flat = useMemo(() => buildTree(data), [data]);
  const runtime = useTreeRuntime(flat);

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

/* ------------------------------------------------------------------ *
 * Starfield backdrop
 * ------------------------------------------------------------------ */

/** Scatters the stars. Kept outside the component so the randomness never runs
 *  during render — a re-render can't reshuffle the sky. */
function createStarfieldGeometry(): THREE.BufferGeometry {
  const positions = new Float32Array(SPACE.STAR_COUNT * 3);
  const sizes = new Float32Array(SPACE.STAR_COUNT);
  const phases = new Float32Array(SPACE.STAR_COUNT);
  const speeds = new Float32Array(SPACE.STAR_COUNT);

  for (let i = 0; i < SPACE.STAR_COUNT; i++) {
    // cbrt keeps the density even across the shell instead of clumping inward.
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

/**
 * Thousands of twinkling points on a spherical shell around the origin.
 * Twinkling and size falloff run entirely in the shader — the only per-frame
 * JS cost is bumping a single `uTime` uniform.
 */
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

/* ------------------------------------------------------------------ *
 * Edges
 * ------------------------------------------------------------------ */

/** Every parent-child connection as one LineSegments draw call, with the
 *  vertex buffer rewritten in place each frame from the live node positions. */
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

/* ------------------------------------------------------------------ *
 * Nodes
 * ------------------------------------------------------------------ */

/** All non-root nodes of one type as a single InstancedMesh — they share
 *  geometry and material and differ only by position, so it costs one draw
 *  call per type instead of one per node. Callers must not render this with
 *  an empty `nodes` array. */
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

/** The only draggable node. Dragging moves it across an invisible plane that
 *  faces the camera; every other node follows through the spring runtime. */
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
  /** Non-null only while dragging: the pose of the invisible pick plane,
   *  frozen at pointer-down so the node slides across the screen plane. */
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

  const endDrag = () => {
    runtime.endDrag();
    if (controlsRef.current) controlsRef.current.enabled = true;
    setDragPlane(null);
  };

  // Releasing outside the drag plane (or outside the canvas) must still end the
  // drag, otherwise the node stays glued to the cursor.
  useEffect(() => {
    if (!dragPlane) return;
    window.addEventListener("pointerup", endDrag);
    return () => window.removeEventListener("pointerup", endDrag);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragPlane]);

  const handlePointerDown = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    const state = runtime.nodeStates.get(id);
    if (!state) return;
    setDragPlane({
      origin: state.current.clone(),
      quaternion: camera.quaternion.clone(),
    });
    runtime.beginDrag(id);
    if (controlsRef.current) controlsRef.current.enabled = false; // don't orbit while dragging
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

/* ------------------------------------------------------------------ *
 * Labels
 * ------------------------------------------------------------------ */

/** A title tag floating just under its node. Position and opacity are driven
 *  imperatively from the shared physics state, same as the meshes and edges,
 *  so labels track drag and spring motion without React re-renders. Opacity
 *  fades with camera distance, tiered by node type (see LABEL_FADE_DISTANCE),
 *  so zooming out declutters instead of leaving a wall of text. */
function NodeLabel({
  node,
  runtime,
}: {
  node: FlatTreeNode;
  runtime: TreeRuntime;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const visual = NODE_VISUALS[node.type];
  const fadeRange = LABEL_FADE_DISTANCE[node.type];
  const { camera } = useThree();

  useFrame(() => {
    const state = runtime.nodeStates.get(node.id);
    if (!state || !groupRef.current) return;

    groupRef.current.position.copy(state.current);
    groupRef.current.position.y -= visual.radius + 0.35;

    const distance = camera.position.distanceTo(state.current);
    const opacity =
      1 - THREE.MathUtils.smoothstep(distance, fadeRange.start, fadeRange.end);
    if (wrapperRef.current) {
      wrapperRef.current.style.opacity = opacity.toString();
      wrapperRef.current.style.display = opacity < 0.02 ? "none" : "block";
    }
  }, 1);

  return (
    <group ref={groupRef}>
      {/* drei's `pointerEvents` prop is a no-op outside `transform` mode — the
          wrapper div only stops picking up pointer events via `style`. Without
          it the label div sits (invisibly) on top of the canvas and swallows
          pointermove events whenever the cursor crosses it mid-drag, freezing
          the drag target until the cursor clears it — which reads as a jump. */}
      <Html
        center
        pointerEvents="none"
        style={{ pointerEvents: "none" }}
        zIndexRange={[10, 0]}
      >
        <div
          ref={wrapperRef}
          style={{
            textAlign: "center",
            pointerEvents: "none",
            userSelect: "none",
            transition: "opacity 0.12s linear",
          }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              margin: "0 auto 4px",
              borderRadius: "50%",
              background: visual.glowColor,
              boxShadow: `0 0 6px 1px ${visual.glowColor}`,
            }}
          />
          <div
            style={{
              display: "inline-block",
              width: "max-content",
              maxWidth: 160,
              padding: "3px 9px",
              borderRadius: 999,
              background: "rgba(6, 8, 20, 0.55)",
              border: `1px solid ${visual.glowColor}66`,
              backdropFilter: "blur(3px)",
              color: "#f2f4ff",
              fontSize: 11,
              fontFamily: UI_FONT,
              letterSpacing: "0.01em",
              lineHeight: 1.35,
              textAlign: "center",
              whiteSpace: "normal",
              wordBreak: "keep-all",
              overflowWrap: "break-word",
              textShadow: `0 0 8px ${visual.glowColor}55`,
            }}
          >
            {node.title}
          </div>
        </div>
      </Html>
    </group>
  );
}
```

### 4-5. `src/spacetree/SpaceTree.tsx`

```tsx
import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useRef, useState } from "react";
import { MOUSE } from "three";
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

/* ==================================================================== *
 * SpaceTree — the single component you mount in your app.
 *
 *   <div style={{ width: "100vw", height: "100vh" }}>
 *     <SpaceTree data={myTree} />
 *   </div>
 *
 * It owns the <Canvas>, the camera/controls, the post-processing bloom, and
 * the HTML overlay UI (2D toggle + zoom slider). Everything scene-side lives
 * in TreeScene.tsx.
 *
 * `data` should be a stable reference (module constant or useMemo/useState) —
 * a new object every render rebuilds the layout and resets the simulation.
 * ==================================================================== */

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

        <TreeScene data={data} controlsRef={controlsRef} />

        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.08}
          minDistance={CAMERA.MIN_DISTANCE}
          maxDistance={CAMERA.MAX_DISTANCE}
          zoomToCursor
          // Left drag orbits, right/middle drag pans — no context menu surprise.
          mouseButtons={{
            LEFT: MOUSE.ROTATE,
            MIDDLE: MOUSE.PAN,
            RIGHT: MOUSE.PAN,
          }}
        />
        <ViewModeController is2D={is2D} controlsRef={controlsRef} />

        {/* Makes the emissive shaders actually glow. */}
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

/* ------------------------------------------------------------------ *
 * 2D / 3D view mode
 * ------------------------------------------------------------------ */

/**
 * Logic-only. On entering 2D it snaps the (still perspective) camera to look
 * straight down the Z axis at whatever point and distance it was already at,
 * and disables rotation so the view can only be panned and zoomed — reading as
 * a flat node-graph without the cost and risk of swapping camera types.
 * Leaving 2D just re-enables rotation from wherever the view currently sits.
 */
function ViewModeController({
  is2D,
  controlsRef,
}: {
  is2D: boolean;
  controlsRef: OrbitControlsRef;
}) {
  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    if (is2D) {
      const camera = controls.object;
      const distance = camera.position.distanceTo(controls.target);
      camera.up.set(0, 1, 0);
      camera.position.set(
        controls.target.x,
        controls.target.y,
        controls.target.z + distance,
      );
      controls.enableRotate = false;
    } else {
      controls.enableRotate = true;
    }
    controls.update();
  }, [is2D, controlsRef]);

  return null;
}

/** Top-right pill that flips between the free-orbiting 3D view and the locked
 *  front-on 2D view, for users who find tumbling 3D navigation uncomfortable. */
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

/* ------------------------------------------------------------------ *
 * Zoom slider
 * ------------------------------------------------------------------ */

/**
 * A vertical zoom slider pinned to the bottom-right, so users can zoom without
 * reaching for the scroll wheel. It reads and writes the camera distance
 * straight off the OrbitControls instance each frame via a plain rAF loop (not
 * R3F's loop — this lives outside the Canvas), so dragging it and wheel-zoom
 * stay in sync with no React re-renders.
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
        // Invert so sliding up (toward "+") zooms in, matching the button labels.
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

const zoomButtonStyle: React.CSSProperties = {
  width: 26,
  height: 26,
  borderRadius: "50%",
  fontSize: 15,
  lineHeight: 1,
  cursor: "pointer",
  ...UI_SURFACE,
};
```

### 4-6. `src/spacetree/treeData.ts`

```ts
import type { TreeNodeInput } from "./config";

/** Sample data — replace with your own. Ids must be unique across the tree. */
export const demoTree: TreeNodeInput = {
  id: "root",
  type: "root",
  title: "프론트엔드",
  children: [
    {
      id: "decision-jwt",
      type: "decision",
      title: "JWT 사용",
      children: [
        {
          id: "task-interceptor",
          type: "task",
          title: "인터셉터 구현",
          children: [
            {
              id: "issue-httponly-cookie",
              type: "issue",
              title: "httpOnly 쿠키 처리 문제",
            },
            {
              id: "issue-token-refresh",
              type: "issue",
              title: "토큰 재발급 타이밍",
            },
          ],
        },
        {
          id: "task-login-persist",
          type: "task",
          title: "로그인 상태 유지",
          children: [
            {
              id: "issue-refresh-flicker",
              type: "issue",
              title: "새로고침 시 깜빡임",
            },
          ],
        },
      ],
    },
    {
      id: "decision-state-management",
      type: "decision",
      title: "상태 관리 전략",
      children: [
        {
          id: "task-global-store",
          type: "task",
          title: "전역 스토어 설계",
          children: [
            {
              id: "issue-cache-sync",
              type: "issue",
              title: "서버 상태와 캐시 동기화",
            },
          ],
        },
      ],
    },
  ],
};
```

### 4-7. `src/spacetree/index.ts`

```ts
export { SpaceTree } from "./SpaceTree";
export { demoTree } from "./treeData";
export type { NodeType, TreeNodeInput } from "./config";
```

---

## 5. 앱에 붙이기

```tsx
import { SpaceTree, demoTree } from "./spacetree";

export default function App() {
  return (
    <div style={{ width: "100vw", height: "100vh" }}>
      <SpaceTree data={demoTree} />
    </div>
  );
}
```

### ⚠️ 가장 흔한 실패 원인: 부모 높이

`SpaceTree`는 `width: 100% / height: 100%`로 부모를 꽉 채운다.
**부모에 높이가 없으면 화면이 그냥 검거나 아무것도 안 보인다.** 전역 CSS에 아래를 넣어두면 안전하다.

```css
html,
body,
#root {
  width: 100%;
  height: 100%;
  margin: 0;
  overflow: hidden;
}

* {
  box-sizing: border-box;
}
```

---

## 6. 내 데이터 넣기

`treeData.ts`를 본인 데이터로 바꾸거나, 같은 모양의 객체를 `data` prop으로 넘기면 된다.

```ts
import type { TreeNodeInput } from "./spacetree";

export const myTree: TreeNodeInput = {
  id: "root", // 트리 전체에서 유일해야 함
  type: "root", // "root" | "decision" | "task" | "issue"
  title: "우리 프로젝트", // 라벨에 표시될 텍스트
  children: [
    {
      id: "d1",
      type: "decision",
      title: "결정 사항",
      children: [
        { id: "t1", type: "task", title: "할 일" },
        { id: "i1", type: "issue", title: "이슈" },
      ],
    },
  ],
};
```

규칙:

- `id`는 트리 전체에서 유일해야 한다 (레이아웃 회전값과 물리 상태의 키로 쓰인다).
- 루트는 하나뿐이고 `type: "root"`여야 한다. root만 드래그 가능하다.
- 깊이 제한은 없다. 자식이 많은 부모는 링 반지름이 자동으로 커진다.
- `type`은 4종 고정이다. 늘리고 싶으면 `NodeType`에 추가하고
  `NODE_VISUALS` / `SPRING_BY_TYPE` / `LABEL_FADE_DISTANCE`에 각각 항목을 추가한 뒤,
  `TreeScene.tsx`의 `PLANET_TYPES` 배열에도 넣으면 된다 (그게 전부다).

### ⚠️ `data`는 안정적인 참조여야 한다

렌더마다 새 객체를 만들면 레이아웃이 다시 계산되고 물리 상태가 초기화된다.

```tsx
// ✅ 모듈 상수
const tree = { ... };
<SpaceTree data={tree} />

// ✅ 서버에서 받아온 경우
const tree = useMemo(() => toTree(apiData), [apiData]);

// ❌ 매 렌더 새 객체
<SpaceTree data={{ id: "root", ... }} />
```

---

## 7. 커스터마이징 — 전부 `config.ts`에서

| 바꾸고 싶은 것             | 건드릴 값                                                     |
| -------------------------- | ------------------------------------------------------------- |
| 노드 크기·색·발광색        | `NODE_VISUALS`                                                |
| 따라오는 느낌(출렁임)      | `SPRING_BY_TYPE` — `stiffness` ↑ 딱딱, `damping` ↓ 오래 출렁  |
| 노드 간격                  | `CHILD_RING_BASE_RADIUS`, `CHILD_RING_RADIUS_PER_EXTRA_CHILD` |
| 연결선 색                  | `EDGE_COLOR`                                                  |
| 라벨이 사라지는 거리       | `LABEL_FADE_DISTANCE`                                         |
| 초기 카메라 위치·줌 한계   | `CAMERA`                                                      |
| 배경색·안개·별 개수        | `SPACE`                                                       |
| 오버레이 UI 폰트·유리 패널 | `UI_FONT`, `UI_SURFACE`                                       |

### 값들 사이의 숨은 규칙 (깨면 티가 난다)

- `LABEL_FADE_DISTANCE.root.end` < `CAMERA.MAX_DISTANCE` 여야 한다.
  안 그러면 최대로 줌아웃해도 루트 라벨이 안 사라진다. 여유를 두고 잡을 것.
- `LABEL_FADE_DISTANCE.issue.start`는 초기 카메라 거리(약 26)보다 커야 한다.
  아니면 첫 화면부터 라벨이 흐리게 보인다.
- 페이드 구간은 `issue → task → decision → root` 순서로 겹치지 않게 올라가야
  줌아웃할 때 깊은 것부터 차례로 정리되는 느낌이 난다.
- 별 셰이더는 `SPACE.STAR_INNER_RADIUS` 안쪽에는 별을 두지 않는다.
  트리보다 별이 앞에 오지 않게 하려는 것이니, 트리가 커지면 이 값도 같이 키울 것.

---

## 8. 동작 원리 (수정할 때 알아야 하는 것만)

**레이아웃(1회) → 물리(매 프레임) → 렌더(매 프레임)** 3단 구조다.

1. **`buildTree(data)`** — 중첩 데이터를 한 번 순회하며 방사형(마인드맵) 좌표를 계산해
   평평한 배열로 만든다. 각 노드는 월드 좌표가 아니라 **부모 기준 오프셋**만 들고 있다.
   부모 id 해시로 링 회전값을 정하므로, 같은 데이터면 항상 같은 모양이 나온다(랜덤 아님).

2. **`useTreeRuntime(flat)`** — 매 프레임 모든 노드를 스프링으로 적분한다.
   각 노드의 목표는 `부모의 현재 위치 + 자기 오프셋`이다. 부모는 이미 한 박자 늦게
   따라가는 중이므로, 그 지연이 아래로 전파되면서 젤리 체인 모션이 **공짜로** 나온다.
   드래그 중인 노드만 목표가 포인터 위치로 바뀐다.

3. **렌더러들** — 위치는 전부 `useFrame` 안에서 three.js 객체에 직접 복사한다.
   **위치를 React state에 넣는 곳은 한 군데도 없다.** 60fps로 움직여도 리렌더는 0회다.

`useFrame`의 **우선순위(priority)** 규칙이 중요하다:

- 물리 = `priority 0`
- 모든 렌더러(노드/엣지/라벨) = `priority 1`

즉 "이번 프레임에 이미 계산된 위치"를 렌더러가 읽는다. 새 렌더러를 추가한다면
**반드시 `useFrame(fn, 1)`로** 등록해야 한 프레임 밀리지 않는다.

성능 메모: 같은 타입의 노드는 `InstancedMesh` 하나로 그린다(타입당 draw call 1개).
엣지는 전체가 `LineSegments` 하나이고, 정점 버퍼를 매 프레임 제자리에서 덮어쓴다.
노드가 수천 개가 돼도 draw call은 그대로다. 다만 **라벨은 노드당 DOM 요소 1개**라
가장 먼저 한계에 부딪힌다. 노드가 아주 많아지면 `TreeScene`에서 라벨을 그릴 대상을
필터링하는 게 첫 번째 최적화 지점이다.

---

## 9. 조작법

| 동작       | 조작                                                    |
| ---------- | ------------------------------------------------------- |
| 회전       | 좌클릭 드래그 (2D 모드에서는 잠김)                      |
| 이동(팬)   | 우클릭 / 휠클릭 드래그                                  |
| 확대·축소  | 휠 (**커서 위치 기준**), 또는 우하단 슬라이더 / +– 버튼 |
| 노드 이동  | 중앙 root를 드래그 → 나머지가 스프링으로 따라옴         |
| 2D/3D 전환 | 우상단 버튼                                             |

## 10. 프레임워크별 주의

**Next.js (App Router)** — WebGL은 브라우저 전용이다.

```tsx
"use client";
import dynamic from "next/dynamic";

const SpaceTree = dynamic(
  () => import("@/spacetree").then((m) => m.SpaceTree),
  {
    ssr: false,
  },
);
```

`SpaceTree.tsx` 파일 맨 위에도 `"use client";`를 붙인다.

**Vite** — 추가 설정 없음. 그대로 동작한다.

**CRA / webpack** — 추가 설정 없음. 다만 `three`가 커서 초기 번들이 늘어나므로
라우트 단위 lazy import를 권장한다.

## 11. 확인 체크리스트

빌드 후 아래가 모두 맞으면 이식 성공이다.

- [ ] 검은 배경에 별이 **반짝인다** (정지 상태가 아님)
- [ ] 중앙 보라색 별이 일렁이고, 주변 행성들이 천천히 자전한다
- [ ] 노드 아래 라벨이 붙어 있다
- [ ] root를 드래그하면 자식들이 **늦게** 따라오고, 놓으면 출렁이며 멈춘다
- [ ] 줌아웃하면 라벨이 issue → task → decision → root 순으로 사라진다
- [ ] 휠을 굴리면 **커서가 가리키는 지점** 쪽으로 확대된다
- [ ] 2D 버튼을 누르면 회전이 잠기고 정면 뷰가 된다

## 12. 문제 해결

| 증상                                                  | 원인 / 해결                                                                                                                                                               |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 화면이 완전히 검다                                    | 부모 컨테이너에 높이가 없다. 5번 항목의 CSS 확인                                                                                                                          |
| 아무것도 안 빛난다                                    | `EffectComposer`(Bloom)가 빠졌거나, 셰이더에 `toneMapped={false}`가 빠졌다                                                                                                |
| 드래그가 중간에 뚝뚝 끊긴다                           | 라벨 div가 포인터 이벤트를 가로채는 것. `Html`의 `style={{ pointerEvents: "none" }}` 필수 (drei의 `pointerEvents` prop만으로는 `transform` 모드가 아니면 동작하지 않는다) |
| 드래그 중 화면이 같이 돌아간다                        | 드래그 시작에서 `controls.enabled = false` 처리가 빠졌다                                                                                                                  |
| 마우스를 캔버스 밖에서 떼면 노드가 커서에 붙어 다닌다 | `RootNode`의 `window` `pointerup` 리스너가 빠졌다                                                                                                                         |
| 트리가 흐물흐물 너무 오래 출렁인다                    | `SPRING_BY_TYPE`의 `damping`을 올린다                                                                                                                                     |
| 탭을 갔다 오면 트리가 폭발한다                        | `treeEngine.ts`의 `MAX_DELTA` 클램프가 빠졌다                                                                                                                             |
| 타입 에러 `three-stdlib` 없음                         | `npm i three-stdlib`                                                                                                                                                      |
| 콘솔에 WebGL context lost                             | Bloom + 6000개 별이 저사양 GPU에 무겁다. `SPACE.STAR_COUNT`를 2000 정도로 낮춘다                                                                                          |

---

## 부록: 이 코드를 만질 때의 원칙

1. **위치는 절대 React state에 넣지 않는다.** 물리 런타임이 소유하고, 렌더러는 `useFrame`에서 읽어간다.
2. **수치는 전부 `config.ts`로.** 컴포넌트 안에 매직 넘버를 두지 않는다.
3. **새 렌더러는 `useFrame(fn, 1)`.** 물리(0)보다 뒤에 실행되어야 한다.
4. **스케일이 필요하면 인스턴싱.** 노드 하나당 컴포넌트 하나를 만들지 않는다.
