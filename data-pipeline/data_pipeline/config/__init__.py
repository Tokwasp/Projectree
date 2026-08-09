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
    """Embedding/vector Retrieval settings."""

    decision_top_k: int = 3
    meeting_max_candidates: int = 5
    embedded_action_top_k: int = 5
    node_top_k: int = 5
    min_similarity: float | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_version: str = "node-embedding-v2-no-category"
    embedding_dim: int = 1536
    text_extension: str = "pg_bigm"
    config_version: str = "retrieval-v1"
    auto_merge_min_similarity: float | None = None
    auto_merge_min_margin: float | None = None


@dataclass(frozen=True)
class SttSettings:
    """Speech-to-text adapter settings."""

    adapter: str = "fake"
    fake_response_path: Path | None = None
    clova_invoke_url: str = ""
    clova_secret: str = ""
    clova_timeout_seconds: float = 900.0


@dataclass(frozen=True)
class DatabaseSettings:
    """Bounded PostgreSQL connection and statement execution settings."""

    pool_size: int = 5
    max_overflow: int = 5
    pool_timeout_seconds: float = 30.0
    pool_recycle_seconds: int = 1800
    connect_timeout_seconds: int = 10
    statement_timeout_ms: int = 30000


@dataclass(frozen=True)
class ApiSettings:
    """HTTP safety limits enforced by the internal FastAPI service."""

    max_request_body_bytes: int = 1_048_576
    internal_service_token: str = ""


@dataclass(frozen=True)
class Settings:
    database_url: str
    category_config_path: Path
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    api: ApiSettings = field(default_factory=ApiSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    stt: SttSettings = field(default_factory=SttSettings)


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _optional_float_env(name: str) -> float | None:
    value = os.environ.get(name)
    return None if value in (None, "") else float(value)


def _optional_path_env(name: str) -> Path | None:
    value = os.environ.get(name)
    return None if value in (None, "") else Path(value)


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
    stt_adapter = _env("STT_ADAPTER", "fake").strip().lower()
    if stt_adapter not in {"fake", "clova"}:
        raise ValueError("STT_ADAPTER must be either 'fake' or 'clova'")
    retrieval = RetrievalSettings(
        decision_top_k=int(_env("RETRIEVAL_DECISION_TOP_K", "3")),
        meeting_max_candidates=int(_env("RETRIEVAL_MEETING_MAX_CANDIDATES", "5")),
        embedded_action_top_k=int(_env("RETRIEVAL_EMBEDDED_ACTION_TOP_K", "5")),
        node_top_k=int(_env("RETRIEVAL_NODE_TOP_K", "5")),
        min_similarity=_optional_float_env("RETRIEVAL_MIN_SIMILARITY"),
        embedding_model=_env("RETRIEVAL_EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_version=_env(
            "RETRIEVAL_EMBEDDING_VERSION", "node-embedding-v2-no-category"
        ),
        embedding_dim=int(_env("RETRIEVAL_EMBEDDING_DIM", "1536")),
        text_extension=_env("RETRIEVAL_TEXT_EXTENSION", "pg_bigm"),
        config_version=_env("RETRIEVAL_CONFIG_VERSION", "retrieval-v1"),
        auto_merge_min_similarity=_optional_float_env(
            "AUTO_MERGE_MIN_SIMILARITY"
        ),
        auto_merge_min_margin=_optional_float_env(
            "AUTO_MERGE_MIN_MARGIN"
        ),
    )
    if (
        retrieval.auto_merge_min_similarity is not None
        and not 0.0 <= retrieval.auto_merge_min_similarity <= 1.0
    ):
        raise ValueError(
            "AUTO_MERGE_MIN_SIMILARITY must be between 0.0 and 1.0"
        )
    if (
        retrieval.auto_merge_min_margin is not None
        and not 0.0 <= retrieval.auto_merge_min_margin <= 2.0
    ):
        raise ValueError(
            "AUTO_MERGE_MIN_MARGIN must be between 0.0 and 2.0"
        )
    database = DatabaseSettings(
        pool_size=int(_env("DB_POOL_SIZE", "5")),
        max_overflow=int(_env("DB_MAX_OVERFLOW", "5")),
        pool_timeout_seconds=float(_env("DB_POOL_TIMEOUT_SECONDS", "30")),
        pool_recycle_seconds=int(_env("DB_POOL_RECYCLE_SECONDS", "1800")),
        connect_timeout_seconds=int(_env("DB_CONNECT_TIMEOUT_SECONDS", "10")),
        statement_timeout_ms=int(_env("DB_STATEMENT_TIMEOUT_MS", "30000")),
    )
    if database.pool_size < 1:
        raise ValueError("DB_POOL_SIZE must be at least 1")
    if database.max_overflow < 0:
        raise ValueError("DB_MAX_OVERFLOW must be at least 0")
    if database.pool_timeout_seconds <= 0:
        raise ValueError("DB_POOL_TIMEOUT_SECONDS must be greater than 0")
    if database.pool_recycle_seconds < 0:
        raise ValueError("DB_POOL_RECYCLE_SECONDS must be at least 0")
    if database.connect_timeout_seconds < 1:
        raise ValueError("DB_CONNECT_TIMEOUT_SECONDS must be at least 1")
    if database.statement_timeout_ms < 1:
        raise ValueError("DB_STATEMENT_TIMEOUT_MS must be at least 1")
    api = ApiSettings(
        max_request_body_bytes=int(
            _env("API_MAX_REQUEST_BODY_BYTES", "1048576")
        ),
        internal_service_token=_env("INTERNAL_API_TOKEN", ""),
    )
    if api.max_request_body_bytes < 1024:
        raise ValueError("API_MAX_REQUEST_BODY_BYTES must be at least 1024")

    return Settings(
        database_url=_env("DATABASE_URL", "postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline"),
        category_config_path=Path(_env("CATEGORY_CONFIG_PATH", str(_DEFAULT_CATEGORY_CONFIG))),
        database=database,
        api=api,
        retrieval=retrieval,
        stt=SttSettings(
            adapter=stt_adapter,
            fake_response_path=_optional_path_env("STT_FAKE_RESPONSE_PATH"),
            clova_invoke_url=_env("CLOVA_INVOKE_URL", ""),
            clova_secret=_env("CLOVA_SECRET", ""),
            clova_timeout_seconds=float(_env("CLOVA_TIMEOUT_SECONDS", "900")),
        ),
    )


DEFAULT_CATEGORY_CONFIG_PATH = _DEFAULT_CATEGORY_CONFIG
