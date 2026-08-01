"""엔진/세션 팩토리. 정본은 PostgreSQL, 테스트는 SQLite 도 가능(같은 ORM)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from data_pipeline.config import load_settings


def make_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    settings = load_settings()
    database_url = url or settings.database_url
    connect_args: dict = {}
    engine_options: dict = {
        "echo": echo,
        "future": True,
        "connect_args": connect_args,
    }
    if make_url(database_url).get_backend_name() == "postgresql":
        database = settings.database
        connect_args.update(
            {
                "connect_timeout": database.connect_timeout_seconds,
                "options": (
                    f"-c statement_timeout={database.statement_timeout_ms}"
                ),
            }
        )
        engine_options.update(
            {
                "pool_pre_ping": True,
                "pool_size": database.pool_size,
                "max_overflow": database.max_overflow,
                "pool_timeout": database.pool_timeout_seconds,
                "pool_recycle": database.pool_recycle_seconds,
            }
        )
    engine = create_engine(database_url, **engine_options)
    if engine.dialect.name == "sqlite":
        # SQLite 는 기본적으로 외래키를 강제하지 않는다 — 켠다 (부모 규칙/무결성 테스트용).
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
