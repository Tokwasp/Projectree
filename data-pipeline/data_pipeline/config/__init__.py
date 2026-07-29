"""설정 로딩. 모든 튜너블 값은 환경변수/설정파일에서 온다 (코드 상수 금지)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent
_DEFAULT_CATEGORY_CONFIG = _CONFIG_DIR / "categories.json"


@dataclass(frozen=True)
class RetrievalSettings:
    """검색기 설정 스텁 (M1 은 구현 없음 — 값만 보관). 코드 상수로 박지 않는다."""

    decision_top_k: int = 3
    meeting_max_candidates: int = 5
    embedded_action_top_k: int = 5
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    text_extension: str = "pg_bigm"


@dataclass(frozen=True)
class Settings:
    database_url: str
    category_config_path: Path
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def load_category_values(path: Path | str | None = None) -> list[str]:
    """카테고리 값 목록을 설정 파일에서 읽는다. §T 미확정 — 교체는 파일 + 마이그레이션 1개."""
    config_path = Path(path) if path else Path(_env("CATEGORY_CONFIG_PATH", str(_DEFAULT_CATEGORY_CONFIG)))
    data = json.loads(config_path.read_text(encoding="utf-8"))
    values = data.get("values")
    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
        raise ValueError(f"카테고리 설정이 비어있거나 형식이 잘못됨: {config_path}")
    if len(set(values)) != len(values):
        raise ValueError(f"카테고리 값에 중복이 있음: {config_path}")
    return list(values)


def load_category_schema_version(path: Path | str | None = None) -> str:
    config_path = Path(path) if path else Path(_env("CATEGORY_CONFIG_PATH", str(_DEFAULT_CATEGORY_CONFIG)))
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return str(data.get("schemaVersion", "unknown"))


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    retrieval = RetrievalSettings(
        decision_top_k=int(_env("RETRIEVAL_DECISION_TOP_K", "3")),
        meeting_max_candidates=int(_env("RETRIEVAL_MEETING_MAX_CANDIDATES", "5")),
        embedded_action_top_k=int(_env("RETRIEVAL_EMBEDDED_ACTION_TOP_K", "5")),
        embedding_model=_env("RETRIEVAL_EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_dim=int(_env("RETRIEVAL_EMBEDDING_DIM", "1536")),
        text_extension=_env("RETRIEVAL_TEXT_EXTENSION", "pg_bigm"),
    )
    return Settings(
        database_url=_env("DATABASE_URL", "postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline"),
        category_config_path=Path(_env("CATEGORY_CONFIG_PATH", str(_DEFAULT_CATEGORY_CONFIG))),
        retrieval=retrieval,
    )


DEFAULT_CATEGORY_CONFIG_PATH = _DEFAULT_CATEGORY_CONFIG
