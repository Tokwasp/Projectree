import type { Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

export type NodeType = "root" | "category" | "decision" | "task" | "issue";

export const CATEGORY_NAMES = [
  "Frontend",
  "Backend",
  "AI",
  "Infra",
  "Design",
  "Planning",
] as const;

export interface TreeNodeInput {
  id: string;
  type: NodeType;
  title: string;
  children?: TreeNodeInput[];
}

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

export type OrbitControlsRef = React.RefObject<OrbitControlsImpl | null>;

export interface NodeVisual {
  radius: number;
  baseColor: string;
  bandColor: string;
  glowColor: string;
}

export const NODE_VISUALS: Record<NodeType, NodeVisual> = {
  root: {
    radius: 1.2,
    baseColor: "#a855f7",
    bandColor: "#f5d0fe",
    glowColor: "#e879f9",
  },
  category: {
    radius: 1.0,
    baseColor: "#d97706",
    bandColor: "#fde68a",
    glowColor: "#fbbf24",
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

export const SPRING_BY_TYPE: Record<NodeType, SpringConfig> = {
  root: { stiffness: 130, damping: 16 },
  category: { stiffness: 95, damping: 12 },
  decision: { stiffness: 70, damping: 9 },
  task: { stiffness: 48, damping: 7 },
  issue: { stiffness: 34, damping: 5.5 },
};

export const CHILD_RING_BASE_RADIUS = 2.4;

/**
 * 루트를 뺀 노드는 "부모에서 자기까지의 방향"을 중심으로 이 각도 안에서만 자식을 뻗는다.
 * 360도로 퍼뜨리면 자식이 루트 쪽으로 되돌아와 이웃 가지와 겹친다.
 */
export const MAX_CHILD_SPREAD = Math.PI * (2 / 3);
/** 부채꼴이 계속 좁아지면 반지름만 커지므로 하한을 둔다. */
export const MIN_CHILD_SPREAD = Math.PI * (2 / 9);
/** 형제 노드 표면 사이 최소 여유. 방향이 촘촘하면 거리를 키워 이만큼을 확보한다. */
export const MIN_SIBLING_GAP = 0.7;
/**
 * 자식이 물려받는 원뿔 각도를 "형제 사이 각도"의 몇 배로 할지.
 * 1보다 작아야 아래 가지가 이웃 가지 영역으로 넘어가지 않는다.
 */
export const SIBLING_CONE_RATIO = 0.8;

export const EDGE_COLOR = "#7fd8ff";

export interface LabelFadeRange {
  start: number;
  end: number;
}

export const LABEL_FADE_DISTANCE: Record<NodeType, LabelFadeRange> = {
  issue: { start: 27, end: 35 },
  task: { start: 35, end: 43 },
  decision: { start: 43, end: 51 },
  category: { start: 51, end: 58 },
  root: { start: 58, end: 64 },
};

export const CAMERA = {
  INITIAL_POSITION: [10, 8, 22] as [number, number, number],
  FOV: 50,
  MIN_DISTANCE: 6,
  MAX_DISTANCE: 70,
  ZOOM_STEP: 2,
};

export const SPACE = {
  BACKGROUND_COLOR: "#000006",
  FOG_DENSITY: 0.006,
  STAR_COUNT: 6000,
  STAR_INNER_RADIUS: 60,
  STAR_OUTER_RADIUS: 400,
};

export const UI_FONT =
  "'Pretendard', 'Segoe UI', system-ui, -apple-system, sans-serif";

export const UI_SURFACE = {
  border: "1px solid rgba(127, 216, 255, 0.4)",
  background: "rgba(6, 8, 20, 0.55)",
  backdropFilter: "blur(3px)",
  color: "#f2f4ff",
};
