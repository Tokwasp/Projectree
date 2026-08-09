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

    baseColor: "#d97706",
    bandColor: "#fde68a",
    glowColor: "#fbbf24",
  },
  category: {
    radius: 1.0,
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

/**
 * 처음부터 라벨을 붙이는 타입. 작업·이슈까지 라벨을 다 띄우면 DOM이 감당하지 못하므로,
 * 그 둘은 결정 노드를 선택했을 때 해당 가지만 붙는다.
 */
export const ALWAYS_LABELED_TYPES: NodeType[] = [
  "root",
  "category",
  "decision",
];

/** 결정을 선택했을 때 연관 노드와 나머지 노드에 곱하는 밝기. */
export const SELECTION_BRIGHTNESS = {
  HIGHLIGHT: 1.35,
  DIM: 0.22,
  /** 마우스를 올린 결정 노드 — 어둡게 깔린 상태에서도 눈에 들어와야 한다. */
  HOVER: 1.8,
};

/** 마우스를 올린 결정 노드를 키우는 배율. 누를 수 있다는 신호는 커서만으로는 약하다. */
export const HOVER_SCALE = 1.3;

/** 노드를 고르는 모드. null이면 평소대로 결정 노드만 클릭 대상이다. */
export type PickMode = "delete" | "edit";

/**
 * 노드 고르기 모드에서 전체 노드에 곱하는 밝기. 화면이 통째로 살짝 밝아지는 것으로
 * "지금은 아무 노드나 고를 수 있다"를 알린다.
 */
export const PICK_MODE_BRIGHTNESS = 1.45;

/**
 * 수정 대상으로 고른 노드의 밝기. 삭제는 고른 노드를 셰이더에서 회색으로 죽이지만,
 * 수정은 지우는 게 아니라 반대로 더 밝혀서 "이 노드를 고쳤다"를 알린다.
 */
export const PICKED_BRIGHTNESS = 2.2;

/** 연관 없는 노드의 라벨에 곱하는 투명도. 아예 감추면 트리 모양이 읽히지 않는다. */
export const SELECTION_LABEL_DIM = 0.3;

/**
 * 강조된 라벨이 버티는 거리. 작업·이슈 라벨은 원래 가까이서만 보이는데,
 * 멀리서 결정을 클릭했을 때 아무것도 안 나타나면 선택이 먹은 줄 모른다.
 */
export const highlightFadeRange = (type: NodeType): LabelFadeRange =>
  LABEL_FADE_DISTANCE[type].end < LABEL_FADE_DISTANCE.decision.end
    ? LABEL_FADE_DISTANCE.decision
    : LABEL_FADE_DISTANCE[type];

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
