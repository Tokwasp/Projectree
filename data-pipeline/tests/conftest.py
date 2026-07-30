"""테스트 하네스. 각 테스트 DB 를 alembic upgrade head 로 구축한다 (완료 기준 1 을 문자 그대로 충족).

Docker/PostgreSQL 없이도 돌도록 기본은 임시 SQLite 파일. 실제 PG 로 돌리려면
DATABASE_URL_TEST=postgresql+psycopg://... 를 주면 그 DB 에 대해 동일하게 검증한다.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from data_pipeline.config import load_settings
from data_pipeline.storage.db import make_engine, make_session_factory

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_alembic_upgrade(db_url: str) -> None:
    os.environ["DATABASE_URL"] = db_url
    load_settings.cache_clear()  # env.py 가 최신 URL 을 읽도록 캐시 초기화
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "data_pipeline" / "storage" / "migrations"))
    command.upgrade(cfg, "head")


def _create_isolated_postgresql_database(base_url: str) -> tuple[str, object]:
    """Create one disposable PostgreSQL database for one test."""

    url = make_url(base_url)
    database_name = f"dp_test_{os.getpid()}_{uuid.uuid4().hex[:16]}"
    admin_url = url.set(database="postgres")
    admin_engine = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    quoted_name = admin_engine.dialect.identifier_preparer.quote(database_name)
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
    return url.set(database=database_name).render_as_string(
        hide_password=False
    ), admin_engine


def _drop_isolated_postgresql_database(
    database_url: str,
    admin_engine,
) -> None:
    database_name = make_url(database_url).database
    assert database_name is not None
    quoted_name = admin_engine.dialect.identifier_preparer.quote(database_name)
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(
            "SELECT pg_terminate_backend(pid) "
            "FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        connection.exec_driver_sql(f"DROP DATABASE {quoted_name}")
    admin_engine.dispose()


@pytest.fixture()
def session_factory():
    override = os.environ.get("DATABASE_URL_TEST")
    tmp = None
    admin_engine = None
    engine = None
    db_url = None
    previous_database_url = os.environ.get("DATABASE_URL")
    try:
        if override:
            parsed_url = make_url(override)
            if parsed_url.get_backend_name() == "postgresql":
                db_url, admin_engine = _create_isolated_postgresql_database(
                    override
                )
            else:
                db_url = override
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            db_url = f"sqlite:///{tmp.name}"

        _run_alembic_upgrade(db_url)
        engine = make_engine(db_url)
        yield make_session_factory(engine)
    finally:
        if engine is not None:
            engine.dispose()
        if admin_engine is not None and db_url is not None:
            _drop_isolated_postgresql_database(db_url, admin_engine)
        if tmp is not None:
            os.unlink(tmp.name)
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        load_settings.cache_clear()
