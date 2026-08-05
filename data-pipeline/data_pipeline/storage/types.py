"""방언 인지 컬럼 타입.

정본 DB 는 PostgreSQL(토폴로지 A)이지만, 로컬/CI 테스트는 Docker 없이 SQLite 로도 돌아가야
한다. 같은 ORM·같은 마이그레이션이 두 방언에서 모두 뜨도록 아래 타입이 흡수한다.
  - JSONB : PostgreSQL 은 JSONB, 그 외는 JSON
  - Vector: PostgreSQL 은 vector(dim) (pgvector), 그 외는 JSON (M1 은 임베딩 미사용)
UUID PK 는 SQLAlchemy 기본 Uuid 타입(PG=uuid, 그 외=CHAR(32))을 그대로 쓴다.
"""

from __future__ import annotations

import json

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, UserDefinedType

# PostgreSQL 에서는 JSONB, 그 외 방언에서는 JSON.
JSONB_or_JSON = JSON().with_variant(JSONB(), "postgresql")


class _PGVector(UserDefinedType):
    """pgvector 패키지 의존 없이 vector(dim) DDL 만 방출하는 최소 타입."""

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dim})"


class Vector(TypeDecorator):
    """PostgreSQL=vector(dim), other dialects=JSON."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        vector = [float(item) for item in value]
        if dialect.name == "postgresql":
            return "[" + ",".join(format(item, ".17g") for item in vector) + "]"
        return vector

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            parsed = json.loads(value)
            return [float(item) for item in parsed]
        return [float(item) for item in value]
