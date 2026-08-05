import style from "./NodeTypeLegend.module.css";
import { NODE_VISUALS } from "../SpaceTree";
import {
  FILTERABLE_NODE_TYPES,
  NODE_TYPE_LABELS,
  type FilterableNodeType,
  type NodeTypeVisibility,
} from "./nodeTypeVisibility";

interface NodeTypeLegendProps {
  visibility: NodeTypeVisibility;
  onChange: (visibility: NodeTypeVisibility) => void;
}

export default function NodeTypeLegend({
  visibility,
  onChange,
}: NodeTypeLegendProps) {
  /**
   * 계층이 카테고리 → 결정 → 작업 → 이슈 순이라 아래 단계는 위 단계 없이 존재할 수 없다.
   * 끄면 아래도 같이 끄고, 켜면 위도 같이 켜서 체크 상태가 실제 화면과 어긋나지 않게 한다.
   */
  const toggle = (type: FilterableNodeType) => {
    const index = FILTERABLE_NODE_TYPES.indexOf(type);
    const turningOn = !visibility[type];
    const next = { ...visibility };

    if (turningOn) {
      for (let i = 0; i <= index; i++) next[FILTERABLE_NODE_TYPES[i]] = true;
    } else {
      for (let i = index; i < FILTERABLE_NODE_TYPES.length; i++) {
        next[FILTERABLE_NODE_TYPES[i]] = false;
      }
    }

    onChange(next);
  };

  return (
    <div className={style.container}>
      <span className={style.title}>노드 종류</span>

      <div className={style.rowFixed}>
        <span
          className={style.dot}
          style={{ background: NODE_VISUALS.root.glowColor }}
        />
        <span className={style.name}>{NODE_TYPE_LABELS.root}</span>
      </div>

      {FILTERABLE_NODE_TYPES.map((type) => (
        <label className={style.row} key={type}>
          <input
            className={style.checkbox}
            type="checkbox"
            checked={visibility[type]}
            onChange={() => toggle(type)}
          />
          <span
            className={style.dot}
            style={{ background: NODE_VISUALS[type].glowColor }}
          />
          <span className={visibility[type] ? style.name : style.nameOff}>
            {NODE_TYPE_LABELS[type]}
          </span>
        </label>
      ))}

      {/* 결정 노드를 누를 수 있다는 걸 마우스를 올려보기 전에도 알아야 한다 */}
      <p className={style.hint}>
        <span
          className={style.dot}
          style={{ background: NODE_VISUALS.decision.glowColor }}
        />
        결정 노드를 클릭하면 하위 작업·이슈가 보입니다
      </p>
    </div>
  );
}
