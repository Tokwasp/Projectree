import { useEffect, useRef, useState } from "react";
import style from "./ProjectRoleFilter.module.css";

export type RoleFilter = "ALL" | "OWNER" | "MEMBER";

interface ProjectRoleFilterProps {
  value: RoleFilter;
  onChange: (value: RoleFilter) => void;
}

const ROLE_OPTIONS: { value: RoleFilter; label: string }[] = [
  { value: "ALL", label: "전체 역할" },
  { value: "OWNER", label: "Owner" },
  { value: "MEMBER", label: "Member" },
];

export default function ProjectRoleFilter({
  value,
  onChange,
}: ProjectRoleFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);
  const selectedOption = ROLE_OPTIONS.find((option) => option.value === value);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!filterRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleSelect = (nextValue: RoleFilter) => {
    onChange(nextValue);
    setIsOpen(false);
  };

  return (
    <div className={style.filter} ref={filterRef}>
      <button
        className={style.trigger}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        <span>{selectedOption?.label}</span>
        <span
          className={`${style.chevron} ${isOpen ? style.open : ""}`}
          aria-hidden="true"
        />
      </button>

      {isOpen && (
        <ul className={style.optionList} role="listbox" aria-label="팀원 역할 필터">
          {ROLE_OPTIONS.map((option) => {
            const isSelected = option.value === value;

            return (
              <li
                className={`${style.option} ${isSelected ? style.selected : ""}`}
                key={option.value}
                role="option"
                aria-selected={isSelected}
                tabIndex={0}
                onClick={() => handleSelect(option.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    handleSelect(option.value);
                  }
                }}
              >
                {option.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
