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

function ringRadius(parentType: NodeType, childCount: number): number {
  const extra = Math.max(0, childCount - 3) * CHILD_RING_RADIUS_PER_EXTRA_CHILD;
  return CHILD_RING_BASE_RADIUS + NODE_VISUALS[parentType].radius + extra;
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
