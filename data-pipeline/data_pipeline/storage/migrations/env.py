"""alembic env. DB URL 은 data_pipeline.config(환경변수 DATABASE_URL)에서 읽는다."""

from __future__ import annotations

from alembic import context
from sqlalchemy import pool

from data_pipeline.config import load_settings
from data_pipeline.storage.db import make_engine
from data_pipeline.storage.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # -x db_url=... 로 override 가능, 없으면 설정(환경변수).
    x_args = context.get_x_argument(as_dictionary=True)
    return x_args.get("db_url") or load_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            poolclass=pool.NullPool,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
