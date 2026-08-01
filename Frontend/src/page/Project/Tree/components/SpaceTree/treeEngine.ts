import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Vector3 } from "three";
import {
  CHILD_RING_BASE_RADIUS,
  CHILD_RING_RADIUS_PER_EXTRA_CHILD,
  MAX_CHILD_SPREAD,
  MIN_CHILD_SPREAD,
  MIN_SIBLING_GAP,
  NODE_VISUALS,
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

/**
 * 자식을 놓을 원의 반지름. 부채꼴이 좁으면 기본 반지름으로는 형제가 서로 닿으므로,
 * 이웃 사이 간격이 MIN_SIBLING_GAP 이상이 되는 거리까지 밀어낸다.
 */
function ringRadius(
  parentType: NodeType,
  children: TreeNodeInput[],
  spread: number,
): number {
  const extra =
    Math.max(0, children.length - 3) * CHILD_RING_RADIUS_PER_EXTRA_CHILD;
  const base = CHILD_RING_BASE_RADIUS + NODE_VISUALS[parentType].radius + extra;

  if (children.length < 2) return base;

  const slice = spread / children.length;
  const widest = Math.max(
    ...children.map((child) => NODE_VISUALS[child.type].radius),
  );
  const needed = (widest + MIN_SIBLING_GAP / 2) / Math.sin(slice / 2);

  return Math.max(base, needed);
}

/**
 * 방사형(마인드맵) 레이아웃을 한 번의 순회로 만든다. 자식은 부모를 중심으로 한 원에
 * 고르게 퍼지고, 자식이 많을수록 반지름이 커진다. 각 노드는 부모 기준 오프셋만 들고
 * 있으며, 월드 좌표는 런타임이 매 프레임 계산한다.
 */
export function buildTree(input: TreeNodeInput): FlatTree {
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
   * outward: 부모에서 이 노드로 향하는 방향(라디안). 자식은 이 방향을 중심으로만 뻗는다.
   * spread: 이 노드가 자식에게 쓸 수 있는 부채꼴 폭.
   */
  const visit = (
    node: TreeNodeInput,
    worldPos: Vector3,
    parent: { id: string; worldPos: Vector3 } | undefined,
    outward: number,
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

    // 루트만 360도를 나눠 쓴다 — 위로 올라갈 부모가 없어 되돌아올 걱정이 없다
    const isRoot = parent === undefined;
    const childSpread = isRoot ? TAU : Math.min(spread, MAX_CHILD_SPREAD);
    const radius = ringRadius(node.type, children, childSpread);
    const slice = childSpread / children.length;
    // 루트에서만 해시로 전체를 회전시킨다. 아래 단계는 바깥 방향에 고정돼야 일관적이다
    const start = isRoot
      ? hash01(node.id) * TAU
      : outward - childSpread / 2;

    children.forEach((child, index) => {
      const angle = start + slice * (index + 0.5);
      const zJitter =
        Math.sin(angle * 2 + hash01(child.id) * 10) * radius * 0.18;
      const childWorldPos = new Vector3(
        worldPos.x + Math.cos(angle) * radius,
        worldPos.y + Math.sin(angle) * radius,
        worldPos.z + zJitter,
      );
      // 부채꼴이 계속 반으로 쪼개지면 반지름만 커지므로 하한을 둔다
      visit(
        child,
        childWorldPos,
        { id: node.id, worldPos },
        angle,
        Math.max(slice, MIN_CHILD_SPREAD),
      );
    });
  };

  visit(input, new Vector3(0, 0, 0), undefined, 0, TAU);

  return { rootId: input.id, order, byType, edges };
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
