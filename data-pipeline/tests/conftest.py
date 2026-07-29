"""테스트 하네스. 각 테스트 DB 를 alembic upgrade head 로 구축한다 (완료 기준 1 을 문자 그대로 충족).

Docker/PostgreSQL 없이도 돌도록 기본은 임시 SQLite 파일. 실제 PG 로 돌리려면
DATABASE_URL_TEST=postgresql+psycopg://... 를 주면 그 DB 에 대해 동일하게 검증한다.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest
from alembic import command
from alembic.config import Config

from data_pipeline.config import load_settings
from data_pipeline.storage.db import make_engine, make_session_factory

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_alembic_upgrade(db_url: str) -> None:
    os.environ["DATABASE_URL"] = db_url
    load_settings.cache_clear()  # env.py 가 최신 URL 을 읽도록 캐시 초기화
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "data_pipeline" / "storage" / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture()
def session_factory():
    override = os.environ.get("DATABASE_URL_TEST")
    tmp = None
    if override:
        db_url = override
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_url = f"sqlite:///{tmp.name}"

    _run_alembic_upgrade(db_url)
    engine = make_engine(db_url)
    yield make_session_factory(engine)

    engine.dispose()
    if tmp is not None:
        os.unlink(tmp.name)
    load_settings.cache_clear()
