"""alembic 마이그레이션 검증 (완료 기준 1). session_factory fixture 가 이미 upgrade head 를 돌린다."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from data_pipeline.config import load_settings
from data_pipeline.storage import (
    NodeCandidate,
    NodeCandidateEvidence,
    Request,
    active_category_values,
)
from data_pipeline.storage.evidence import build_evidence_key
from data_pipeline.storage.db import make_engine

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "meeting", "request", "node", "node_embedding", "transcript_segment",
    "node_evidence", "node_candidate", "node_candidate_evidence",
    "candidate_review_event", "relation", "graph_change_event", "outbox_event", "category",
    "node_analysis_run", "retrieval_result",
    "alembic_version",
}


def _engine(session_factory):
    with session_factory() as s:
        return s.get_bind()


def test_all_tables_created(session_factory):
    tables = set(inspect(_engine(session_factory)).get_table_names())
    assert EXPECTED_TABLES <= tables, EXPECTED_TABLES - tables


def test_categories_seeded_from_config(session_factory):
    with _engine(session_factory).connect() as conn:
        values = active_category_values(conn)
    assert values == ["PLANNING", "DESIGN", "FRONTEND", "BACKEND", "AI", "INFRA", "ETC"]


def test_node_has_no_embedding_column(session_factory):
    """node 에는 embedding 컬럼이 없어야 한다 (별도 node_embedding 테이블)."""
    insp = inspect(_engine(session_factory))
    node_cols = {c["name"] for c in insp.get_columns("node")}
    assert "embedding" not in node_cols
    emb_cols = {c["name"] for c in insp.get_columns("node_embedding")}
    assert "embedding" in emb_cols


def test_node_source_is_candidate_scoped_and_legacy_compatible(session_factory):
    insp = inspect(_engine(session_factory))
    node_columns = {
        column["name"]: column for column in insp.get_columns("node")
    }
    assert "source_candidate_id" in node_columns
    assert node_columns["source_candidate_id"]["nullable"] is True

    unique_names = {
        constraint["name"]
        for constraint in insp.get_unique_constraints("node")
    }
    assert "uq_node_source_candidate" in unique_names
    assert "uq_node_source" not in unique_names

    foreign_keys = {
        constraint["name"]: constraint
        for constraint in insp.get_foreign_keys("node")
    }
    source_fk = foreign_keys["fk_node_source_candidate"]
    assert source_fk["referred_table"] == "node_candidate"
    assert source_fk["constrained_columns"] == ["source_candidate_id"]


def test_candidate_schema_and_request_metadata_constraints(session_factory):
    insp = inspect(_engine(session_factory))
    request_columns = {column["name"] for column in insp.get_columns("request")}
    assert {
        "external_request_id", "input_hash", "input_hash_version", "payload_hash",
        "lineage", "usage", "raw_extraction", "raw_judgment", "warnings",
        "failure_stage", "failure_code", "failure_message", "completed_at",
    } <= request_columns
    request_unique = {
        constraint["name"] for constraint in insp.get_unique_constraints("request")
    }
    request_checks = {
        constraint["name"] for constraint in insp.get_check_constraints("request")
    }
    request_indexes = {index["name"] for index in insp.get_indexes("request")}
    assert "uq_request_generation_input" in request_unique
    assert {"ck_request_status", "ck_request_failure_stage"} <= request_checks
    assert "ix_request_status" in request_indexes

    candidate_columns = {column["name"] for column in insp.get_columns("node_candidate")}
    assert {
        "request_id", "raw_item", "raw_judgment", "suggested_disposition",
        "suggested_parent_candidate_id", "suggested_parent_node_id",
        "reviewed_parent_mode", "review_status", "confirmed_node_id",
        "initial_review_node_id", "version",
    } <= candidate_columns

    unique_names = {constraint["name"] for constraint in insp.get_unique_constraints("node_candidate")}
    check_names = {constraint["name"] for constraint in insp.get_check_constraints("node_candidate")}
    fk_names = {constraint["name"] for constraint in insp.get_foreign_keys("node_candidate")}
    assert "uq_candidate_request_item" in unique_names
    assert {
        "ck_candidate_version_positive",
        "ck_candidate_suggested_parent_exclusive",
        "ck_candidate_reviewed_parent_exclusive",
        "ck_candidate_reviewed_parent_mode",
        "ck_candidate_review_status",
        "ck_candidate_suggested_node_type",
    } <= check_names
    assert {
        "fk_candidate_request",
        "fk_candidate_suggested_parent_candidate",
        "fk_candidate_suggested_parent_node",
    } <= fk_names
    assert "uq_candidate_confirmed_node" in unique_names
    candidate_indexes = {
        index["name"]: index for index in insp.get_indexes("node_candidate")
    }
    assert candidate_indexes["uq_candidate_initial_review_node"]["unique"] == 1

    evidence_fks = insp.get_foreign_keys("node_candidate_evidence")
    candidate_fk = next(fk for fk in evidence_fks if fk["name"] == "fk_candidate_evidence_candidate")
    assert candidate_fk["options"].get("ondelete") == "CASCADE"

    review_columns = {
        column["name"]
        for column in insp.get_columns("candidate_review_event")
    }
    assert {
        "candidate_id",
        "request_id",
        "actor_id",
        "action",
        "before_json",
        "after_json",
        "created_at",
    } <= review_columns
    review_checks = {
        constraint["name"]
        for constraint in insp.get_check_constraints("candidate_review_event")
    }
    assert "ck_candidate_review_event_action" in review_checks


def test_transcript_segment_keeps_raw_and_normalized_text(session_factory):
    insp = inspect(_engine(session_factory))
    segment_columns = {
        column["name"]
        for column in insp.get_columns("transcript_segment")
    }

    assert {
        "text",
        "text_hash",
        "raw_text",
        "raw_text_hash",
        "normalized_text",
        "normalization_metadata",
    } <= segment_columns


def test_node_has_initial_review_and_analysis_boundary_columns(session_factory):
    node_columns = {
        column["name"]
        for column in inspect(_engine(session_factory)).get_columns("node")
    }

    assert {
        "merged_into_node_id",
        "analysis_status",
        "analysis_input_hash",
        "current_analysis_run_id",
        "initial_reviewed_by",
        "initial_reviewed_at",
        "confirmed_by",
        "confirmed_at",
    } <= node_columns


def test_node_evidence_key_and_merge_lookup_indexes(session_factory):
    insp = inspect(_engine(session_factory))
    evidence_columns = {
        column["name"]: column
        for column in insp.get_columns("node_evidence")
    }
    evidence_indexes = {
        index["name"]: index
        for index in insp.get_indexes("node_evidence")
    }
    node_indexes = {
        index["name"]: index
        for index in insp.get_indexes("node")
    }

    assert evidence_columns["evidence_key"]["nullable"] is False
    assert evidence_indexes["uq_node_evidence_node_key"]["unique"] == 1
    assert evidence_indexes["uq_node_evidence_node_key"]["column_names"] == [
        "node_id",
        "evidence_key",
    ]
    assert node_indexes["ix_node_merged_into_node_id"]["unique"] == 0
    assert node_indexes["ix_node_merged_into_node_id"]["column_names"] == [
        "merged_into_node_id"
    ]


def _request() -> Request:
    return Request(
        project_id="proj",
        external_meeting_id="meeting",
        external_request_id="request",
        pipeline_version="pipeline",
        run_type="NODE_GENERATION",
        input_hash="input-hash",
        input_hash_version="generation-input-v1",
        payload_hash="hash",
        status="PROCESSING",
    )


def _candidate(request_id, *, source_item_id="m1", review_status="PENDING") -> NodeCandidate:
    return NodeCandidate(
        request_id=request_id,
        project_id="proj",
        external_meeting_id="meeting",
        source_item_id=source_item_id,
        raw_item={"id": source_item_id},
        suggested_node_type="DECISION",
        suggested_title="title",
        suggested_content="content",
        suggested_disposition="NEW_DECISION",
        review_status=review_status,
    )


def test_candidate_unique_and_check_constraints_are_enforced(session_factory):
    with session_factory() as session:
        request = _request()
        session.add(request)
        session.flush()
        session.add_all([_candidate(request.id), _candidate(request.id)])
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    with session_factory() as session:
        request = _request()
        session.add(request)
        session.flush()
        session.add(_candidate(request.id, review_status="UNKNOWN"))
        with pytest.raises(IntegrityError):
            session.flush()


def test_candidate_evidence_foreign_key_is_enforced(session_factory):
    with session_factory() as session:
        session.add(NodeCandidateEvidence(
            candidate_id=uuid.uuid4(),
            segment_id="s1",
            quote="존재하지 않는 후보를 참조하는 충분히 긴 근거입니다.",
        ))
        with pytest.raises(IntegrityError):
            session.flush()


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location", str(ROOT / "data_pipeline" / "storage" / "migrations")
    )
    return config


def _insert_legacy_evidence(
    database_url: str,
    *,
    duplicate: bool = False,
) -> tuple[str, str]:
    engine = make_engine(database_url)
    node_id = uuid.uuid4().hex
    quote = "Redis를 캐시 저장소로 사용하기로 결정했습니다."
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO node ("
                "id, project_id, source_meeting_id, source_item_id, "
                "node_type, category, title, content, graph_state, "
                "lifecycle_status, version"
                ") VALUES ("
                ":id, 'proj', 'meeting', 'item', 'DECISION', 'BACKEND', "
                "'결정', '본문', 'UNATTACHED', 'ACTIVE', 1"
                ")"
            ),
            {"id": node_id},
        )
        evidence_rows = [
            {
                "id": uuid.uuid4().hex,
                "node_id": node_id,
                "quote": quote,
            }
        ]
        if duplicate:
            evidence_rows.append(
                {
                    "id": uuid.uuid4().hex,
                    "node_id": node_id,
                    "quote": quote,
                }
            )
        connection.execute(
            text(
                "INSERT INTO node_evidence ("
                "id, node_id, segment_id, quote, quote_start, quote_end, "
                "evidence_type, source_meeting_id"
                ") VALUES ("
                ":id, :node_id, 's1', :quote, 0, 24, 'MEETING', 'meeting'"
                ")"
            ),
            evidence_rows,
        )
    engine.dispose()
    return node_id, quote


def _set_database_url(monkeypatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    load_settings.cache_clear()


def test_clean_alembic_baseline_round_trip(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()

    command.upgrade(config, "head")
    engine = make_engine(database_url)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "base")
    engine = make_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()

    command.upgrade(config, "head")
    engine = make_engine(database_url)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()
    assert (
        ScriptDirectory.from_config(config).get_current_head()
        == "0003_review_analysis"
    )


def test_analysis_execution_schema(session_factory):
    insp = inspect(_engine(session_factory))
    node_checks = {
        constraint["name"]
        for constraint in insp.get_check_constraints("node")
    }
    run_columns = {
        column["name"] for column in insp.get_columns("node_analysis_run")
    }
    result_columns = {
        column["name"] for column in insp.get_columns("retrieval_result")
    }
    run_checks = {
        constraint["name"]
        for constraint in insp.get_check_constraints("node_analysis_run")
    }
    run_unique = {
        constraint["name"]
        for constraint in insp.get_unique_constraints("node_analysis_run")
    }
    result_unique = {
        constraint["name"]
        for constraint in insp.get_unique_constraints("retrieval_result")
    }

    assert {
        "source_node_id",
        "source_node_version",
        "analysis_input_hash",
        "analysis_input_hash_version",
        "retrieval_config_version",
        "embedding_model",
        "embedding_version",
        "attempt",
        "status",
        "requested_by",
        "failure_code",
        "failure_message",
        "started_at",
        "completed_at",
    } <= run_columns
    assert {
        "analysis_run_id",
        "target_node_id",
        "target_node_version",
        "rank",
        "similarity",
    } <= result_columns
    assert {
        "ck_analysis_run_status",
        "ck_analysis_run_node_version_positive",
        "ck_analysis_run_attempt_positive",
    } <= run_checks
    assert "uq_analysis_run_node_version_hash_attempt" in run_unique
    run_indexes = {
        index["name"]: index
        for index in insp.get_indexes("node_analysis_run")
    }
    assert run_indexes["uq_analysis_run_active_node_hash"]["unique"] == 1
    assert {
        "uq_retrieval_result_run_rank",
        "uq_retrieval_result_run_target",
    } <= result_unique
    result_checks = {
        constraint["name"]
        for constraint in insp.get_check_constraints("retrieval_result")
    }
    assert "ck_retrieval_result_target_version_positive" in result_checks
    if insp.bind.dialect.name != "sqlite":
        assert "ck_node_analysis_status" in node_checks
        assert "uq_analysis_run_source_node_id" in run_unique
        current_fk = next(
            foreign_key
            for foreign_key in insp.get_foreign_keys("node")
            if foreign_key["name"] == "fk_node_current_analysis_run"
        )
        assert current_fk["constrained_columns"] == [
            "id",
            "current_analysis_run_id",
        ]
        assert current_fk["referred_columns"] == ["source_node_id", "id"]
    else:
        assert "uq_analysis_run_source_node_id" in run_unique


def test_0003_backfills_existing_evidence_key(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'evidence-backfill.db'}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.upgrade(config, "0002_seed_categories")
    _, quote = _insert_legacy_evidence(database_url)

    command.upgrade(config, "head")

    engine = make_engine(database_url)
    with engine.connect() as connection:
        stored_key = connection.execute(
            text("SELECT evidence_key FROM node_evidence")
        ).scalar_one()
    engine.dispose()
    assert stored_key == build_evidence_key(
        segment_id="s1",
        quote=quote,
        quote_start=0,
        quote_end=24,
        evidence_type="MEETING",
        source_meeting_id="meeting",
    )


def test_0003_rejects_existing_duplicate_evidence(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'evidence-duplicate.db'}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.upgrade(config, "0002_seed_categories")
    _insert_legacy_evidence(database_url, duplicate=True)

    with pytest.raises(RuntimeError, match="duplicate row"):
        command.upgrade(config, "head")


def test_revision_files_do_not_use_live_orm_metadata():
    revisions = ROOT / "data_pipeline" / "storage" / "migrations" / "versions"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(revisions.glob("*.py"))
    )
    assert "data_pipeline.storage.models" not in source
    assert "Base.metadata" not in source
    assert ".create_all(" not in source
    assert ".drop_all(" not in source
    assert not (revisions / "0003_proposed_candidates.py").exists()
    assert {
        path.name for path in revisions.glob("*.py")
    } == {
        "0001_initial.py",
        "0002_seed_categories.py",
        "0003_review_analysis.py",
    }


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRESQL_URL"),
    reason="TEST_POSTGRESQL_URL is not configured for a disposable database",
)
def test_disposable_postgresql_migration_round_trip(monkeypatch):
    database_url = os.environ["TEST_POSTGRESQL_URL"]
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
