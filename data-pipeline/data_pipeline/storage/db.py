"""엔진/세션 팩토리. 정본은 PostgreSQL, 테스트는 SQLite 도 가능(같은 ORM)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from data_pipeline.config import load_settings


def make_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    database_url = url or load_settings().database_url
    connect_args: dict = {}
    engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)
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
