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
