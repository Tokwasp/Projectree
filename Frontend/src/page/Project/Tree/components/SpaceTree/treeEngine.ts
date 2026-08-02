import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Vector3 } from "three";
import {
  CHILD_RING_BASE_RADIUS,
  MAX_CHILD_SPREAD,
  MIN_CHILD_SPREAD,
  MIN_SIBLING_GAP,
  NODE_VISUALS,
  SIBLING_CONE_RATIO,
  SPRING_BY_TYPE,
  type FlatTreeNode,
  type NodeType,
  type TreeEdge,
  type TreeNodeInput,
} from "./config";

export interface FlatTree {
  rootId: string;
  order: FlatTreeNode[];
  byType: Record<NodeType, FlatTreeNode[]>;
  edges: TreeEdge[];
}

const TAU = Math.PI * 2;

/** 같은 데이터면 항상 같은 모양이 나오도록 id로 회전값을 고정 */
function hash01(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0;
  }
  return (h % 1000) / 1000;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

/**
 * 루트의 자식은 구면에 고르게 흩는다(황금나선). 평면 원에 두면 옆에서 봤을 때
 * 트리 전체가 한 줄로 뭉쳐 보여 3D인 의미가 없어진다.
 */
function sphereDirections(count: number, seed: number): Vector3[] {
  return Array.from({ length: count }, (_, index) => {
    const y = 1 - ((index + 0.5) * 2) / count;
    const ring = Math.sqrt(Math.max(0, 1 - y * y));
    const phi = index * GOLDEN_ANGLE + seed * TAU;
    return new Vector3(Math.cos(phi) * ring, y, Math.sin(phi) * ring);
  });
}

/** 2D 배치용 — 루트의 자식을 XY 평면의 원 위에 둔다. */
function circleDirections(count: number, seed: number): Vector3[] {
  return Array.from({ length: count }, (_, index) => {
    const angle = seed * TAU + (TAU * index) / count;
    return new Vector3(Math.cos(angle), Math.sin(angle), 0);
  });
}

/** 2D 배치용 — 바깥 방향을 중심으로 XY 평면 부채꼴에 펼친다. */
function fanDirections(
  outward: Vector3,
  spread: number,
  count: number,
): Vector3[] {
  const base = Math.atan2(outward.y, outward.x);
  const slice = spread / count;

  return Array.from({ length: count }, (_, index) => {
    const angle = base - spread / 2 + slice * (index + 0.5);
    return new Vector3(Math.cos(angle), Math.sin(angle), 0);
  });
}

/** 그 아래는 부모에서 자기까지의 방향을 축으로 하는 원뿔면에 둘러 놓는다. */
function coneDirections(
  outward: Vector3,
  spread: number,
  count: number,
  seed: number,
): Vector3[] {
  if (count === 1) return [outward.clone()];

  // outward와 평행하지 않은 벡터를 골라야 외적이 0이 되지 않는다
  const helper =
    Math.abs(outward.y) < 0.9 ? new Vector3(0, 1, 0) : new Vector3(1, 0, 0);
  const u = new Vector3().crossVectors(outward, helper).normalize();
  const v = new Vector3().crossVectors(outward, u).normalize();

  const theta = spread / 2;
  const sinT = Math.sin(theta);
  const cosT = Math.cos(theta);

  return Array.from({ length: count }, (_, index) => {
    const phi = (TAU * index) / count + seed * TAU;
    return new Vector3()
      .addScaledVector(outward, cosT)
      .addScaledVector(u, Math.cos(phi) * sinT)
      .addScaledVector(v, Math.sin(phi) * sinT)
      .normalize();
  });
}

/** 방향 벡터들 중 가장 가까운 두 개의 거리 (단위구 위). */
function minDirectionDistance(directions: Vector3[]): number {
  let min = Infinity;
  for (let i = 0; i < directions.length; i++) {
    for (let j = i + 1; j < directions.length; j++) {
      min = Math.min(min, directions[i].distanceTo(directions[j]));
    }
  }
  return min;
}

/**
 * 자식을 놓을 거리. 방향이 촘촘하면 기본 거리로는 형제가 서로 닿으므로,
 * 가장 가까운 두 형제 사이가 MIN_SIBLING_GAP 이상 벌어지는 거리까지 밀어낸다.
 */
function ringRadius(
  parentType: NodeType,
  children: TreeNodeInput[],
  directions: Vector3[],
): number {
  const base = CHILD_RING_BASE_RADIUS + NODE_VISUALS[parentType].radius;

  if (directions.length < 2) return base;

  const widest = Math.max(
    ...children.map((child) => NODE_VISUALS[child.type].radius),
  );
  const needed =
    (2 * widest + MIN_SIBLING_GAP) / minDirectionDistance(directions);

  return Math.max(base, needed);
}

/**
 * 방사형 레이아웃을 한 번의 순회로 만든다. 루트의 자식은 구면에, 그 아래는 부모에서
 * 자기까지의 방향을 축으로 하는 원뿔면에 배치되어 어느 각도에서 봐도 입체로 보인다.
 * 각 노드는 부모 기준 오프셋만 들고 있고, 월드 좌표는 런타임이 매 프레임 계산한다.
 */
export function buildTree(input: TreeNodeInput, planar = false): FlatTree {
  const order: FlatTreeNode[] = [];
  const edges: TreeEdge[] = [];
  const byType: Record<NodeType, FlatTreeNode[]> = {
    root: [],
    category: [],
    decision: [],
    task: [],
    issue: [],
  };

  /**
   * outward: 부모에서 이 노드로 향하는 단위 벡터. 자식은 이 방향을 축으로만 뻗는다.
   * spread: 이 노드가 자식에게 쓸 수 있는 원뿔의 꼭지각.
   */
  const visit = (
    node: TreeNodeInput,
    worldPos: Vector3,
    parent: { id: string; worldPos: Vector3 } | undefined,
    outward: Vector3,
    spread: number,
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

    // 루트는 사방(구면)으로 흩고, 그 아래는 바깥 방향을 축으로 한 원뿔에만 둔다
    const isRoot = parent === undefined;
    const seed = hash01(node.id);
    const childSpread = Math.min(spread, MAX_CHILD_SPREAD);
    const directions = planar
      ? isRoot
        ? circleDirections(children.length, seed)
        : fanDirections(outward, childSpread, children.length)
      : isRoot
        ? sphereDirections(children.length, seed)
        : coneDirections(outward, childSpread, children.length, seed);

    const radius = ringRadius(node.type, children, directions);

    // 형제 사이 각도보다 좁은 원뿔을 물려줘야 아래 가지끼리 서로 파고들지 않는다
    const nextSpread =
      directions.length < 2
        ? childSpread
        : Math.min(
            MAX_CHILD_SPREAD,
            Math.max(
              MIN_CHILD_SPREAD,
              2 *
                Math.asin(Math.min(1, minDirectionDistance(directions) / 2)) *
                SIBLING_CONE_RATIO,
            ),
          );

    children.forEach((child, index) => {
      const direction = directions[index];
      const childWorldPos = worldPos
        .clone()
        .addScaledVector(direction, radius);

      visit(
        child,
        childWorldPos,
        { id: node.id, worldPos },
        direction,
        nextSpread,
      );
    });
  };

  visit(input, new Vector3(0, 0, 0), undefined, new Vector3(0, 1, 0), TAU);

  return { rootId: input.id, order, byType, edges };
}

/** 원점에서 가장 먼 노드까지의 거리. 카메라를 트리에 맞출 때 쓴다. */
export function boundingRadius(flat: FlatTree): number {
  const positions = new Map<string, Vector3>();
  let max = 0;

  for (const node of flat.order) {
    const parent = node.parentId ? positions.get(node.parentId) : undefined;
    const world = parent
      ? parent.clone().add(node.localOffset)
      : node.localOffset.clone();

    positions.set(node.id, world);
    max = Math.max(max, world.length());
  }

  return max;
}

export interface NodeRuntimeState {
  id: string;
  type: NodeType;
  parentId?: string;
  localOffset: Vector3;
  current: Vector3;
  velocity: Vector3;
}

export interface TreeRuntime {
  nodeStates: Map<string, NodeRuntimeState>;
  order: string[];
  /**
   * 목표 위치만 갈아끼운다. 노드를 순간이동시키지 않고 스프링이 새 위치로 끌고 가므로,
   * 2D/3D 전환이 그대로 이동 모션이 된다.
   */
  applyLayout: (next: FlatTree) => void;
  beginDrag: (id: string) => void;
  updateDragPoint: (point: Vector3) => void;
  endDrag: () => void;
}

/** 탭이 멈췄다 돌아왔을 때 시뮬레이션이 폭발하지 않게 물리 스텝을 자름. */
const MAX_DELTA = 1 / 30;

export function useTreeRuntime(flat: FlatTree): TreeRuntime {
  const nodeStates = useMemo(() => {
    const states = new Map<string, NodeRuntimeState>();
    // order가 top-down이라 부모의 시작 위치는 항상 먼저 정해져 있음
    for (const node of flat.order) {
      const parentState = node.parentId ? states.get(node.parentId) : undefined;
      const worldPos = parentState
        ? parentState.current.clone().add(node.localOffset)
        : node.localOffset.clone();
      states.set(node.id, {
        id: node.id,
        type: node.type,
        parentId: node.parentId,
        // 반드시 복사해야 한다 — 그대로 참조하면 applyLayout의 copy가
        // 원본 배치(flat)를 덮어써서 되돌아갈 곳이 사라진다
        localOffset: node.localOffset.clone(),
        current: worldPos,
        velocity: new Vector3(),
      });
    }
    return states;
  }, [flat]);

  const order = useMemo(() => flat.order.map((n) => n.id), [flat]);

  const draggingIdRef = useRef<string | null>(null);
  const dragTargetRef = useRef(new Vector3());

  const targetScratch = useMemo(() => new Vector3(), []);
  const forceScratch = useMemo(() => new Vector3(), []);

  useFrame((_, rawDelta) => {
    const dt = Math.min(rawDelta, MAX_DELTA);
    for (const id of order) {
      const state = nodeStates.get(id);
      if (!state) continue;

      let target: Vector3;
      if (id === draggingIdRef.current) {
        target = dragTargetRef.current;
      } else if (state.parentId) {
        const parentState = nodeStates.get(state.parentId);
        if (!parentState) continue;
        target = targetScratch.copy(parentState.current).add(state.localOffset);
      } else {
        target = state.current;
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

  // 참조가 매 렌더 바뀌면 이걸 의존성으로 쓰는 effect가 계속 다시 돈다
  return useMemo(
    () => ({
      nodeStates,
      order,
      applyLayout: (next: FlatTree) => {
        for (const node of next.order) {
          nodeStates.get(node.id)?.localOffset.copy(node.localOffset);
        }
      },
      beginDrag: (id: string) => {
        draggingIdRef.current = id;
        const state = nodeStates.get(id);
        if (state) dragTargetRef.current.copy(state.current);
      },
      updateDragPoint: (point: Vector3) => dragTargetRef.current.copy(point),
      endDrag: () => {
        draggingIdRef.current = null;
      },
    }),
    [nodeStates, order],
  );
}
