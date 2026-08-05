"""설정 파일 기반 카테고리 (하드코딩 enum 아님).

§T 미확정 — 값 교체가 마이그레이션 한 번으로 끝나야 하므로 Python enum 으로 박지 않는다.
정본은 `category` reference 테이블(마이그레이션이 config 로 시딩)이고, 계약 검증은 config
파일에서 읽은 값 집합으로 수행한다. 둘은 같은 소스(config/categories.json)를 본다.
"""

from __future__ import annotations

from pathlib import Path

from data_pipeline.config import load_category_schema_version, load_category_values


class CategorySet:
    """config 로부터 로드된 유효 카테고리 값 집합. 런타임 검증에 사용."""

    def __init__(self, values: list[str], schema_version: str) -> None:
        self._values = list(values)
        self._set = frozenset(values)
        self.schema_version = schema_version

    @classmethod
    def load(cls, path: Path | str | None = None) -> "CategorySet":
        return cls(load_category_values(path), load_category_schema_version(path))

    def __contains__(self, value: object) -> bool:
        return value in self._set

    def is_valid(self, value: str) -> bool:
        return value in self._set

    @property
    def values(self) -> list[str]:
        return list(self._values)

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)
