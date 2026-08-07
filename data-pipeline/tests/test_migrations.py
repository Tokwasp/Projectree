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
    Node,
    NodeCandidate,
    NodeCandidateEvidence,
    Relation,
    Request,
    active_category_values,
)
from data_pipeline.storage.evidence import build_evidence_key
from data_pipeline.storage.db import make_engine
from .conftest import (
    _create_isolated_postgresql_database,
    _drop_isolated_postgresql_database,
)

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "meeting", "request", "node", "node_embedding", "transcript_segment",
    "node_evidence", "node_candidate", "node_candidate_evidence",
    "candidate_review_event", "relation", "graph_change_event", "outbox_event", "category",
    "node_analysis_run", "retrieval_result",
    "b_model_result", "analysis_candidate", "node_merge_history",
    "audio_upload_event",
    "analysis_job",
    "generation_run",
    "meeting_summary",
    "project_graph_state",
    "analysis_delivery_state",
    "node_revision",
    "evidence",
    "node_revision_evidence",
    "merge_operation",
    "merge_operation_dependency",
    "recording_ready_event",
    "meeting_analysis_command",
    "meeting_analysis_task",
    "graph_snapshot_artifact",
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


def test_outbox_has_durable_claim_ownership(session_factory):
    inspector = inspect(_engine(session_factory))
    columns = {
        column["name"] for column in inspector.get_columns("outbox_event")
    }
    indexes = {
        index["name"]: index
        for index in inspector.get_indexes("outbox_event")
    }

    assert {"claim_token", "claimed_at"} <= columns
    assert indexes["ix_outbox_event_claimable"]["column_names"] == [
        "status",
        "available_at",
    ]
    if inspector.bind.dialect.name == "postgresql":
        checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("outbox_event")
        }
        assert {
            "ck_outbox_event_status",
            "ck_outbox_event_attempt_count",
            "ck_outbox_event_max_attempts",
            "ck_outbox_event_claim_owner",
        } <= checks


def test_postgresql_alembic_metadata_has_no_schema_drift(
    session_factory,
    monkeypatch,
):
    engine = _engine(session_factory)
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL is canonical for the Alembic metadata check")
    database_url = engine.url.render_as_string(hide_password=False)
    _set_database_url(monkeypatch, database_url)

    command.check(_alembic_config())


def test_postgresql_engine_has_bounded_pool_and_statement_timeout(
    session_factory,
):
    engine = _engine(session_factory)
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only runtime connection settings")
    settings = load_settings().database

    assert engine.pool._pre_ping is True
    assert engine.pool.size() == settings.pool_size
    assert engine.pool._max_overflow == settings.max_overflow
    assert engine.pool.timeout() == settings.pool_timeout_seconds
    assert engine.pool._recycle == settings.pool_recycle_seconds
    with engine.connect() as connection:
        timeout_ms = connection.execute(
            text(
                "SELECT EXTRACT(EPOCH FROM "
                "current_setting('statement_timeout')::interval) * 1000"
            )
        ).scalar_one()
    assert int(timeout_ms) == settings.statement_timeout_ms


def test_postgresql_runtime_upgrade_downgrade_reupgrade(
    session_factory,
    monkeypatch,
):
    engine = _engine(session_factory)
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only additive migration verification")
    database_url = engine.url.render_as_string(hide_password=False)
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()

    command.downgrade(config, "0003_review_analysis")
    assert "claim_token" not in {
        column["name"] for column in inspect(engine).get_columns("outbox_event")
    }
    assert "analysis_job" not in inspect(engine).get_table_names()

    command.upgrade(config, "head")
    assert {"claim_token", "claimed_at"} <= {
        column["name"] for column in inspect(engine).get_columns("outbox_event")
    }
    assert "analysis_job" in inspect(engine).get_table_names()

    command.downgrade(config, "0003_review_analysis")
    command.upgrade(config, "head")


def test_postgresql_node_and_relation_integrity_constraints(session_factory):
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL-only database integrity constraints")
        inspector = inspect(session.get_bind())
        expected_project_fks = {
            "node": {
                "fk_node_parent_project",
                "fk_node_merged_into_project",
            },
            "relation": {
                "fk_relation_from_project",
                "fk_relation_to_project",
            },
            "b_model_result": {
                "fk_b_model_result_source_project",
                "fk_b_model_result_target_project",
            },
            "analysis_candidate": {
                "fk_analysis_candidate_source_project",
                "fk_analysis_candidate_target_project",
            },
            "node_merge_history": {
                "fk_merge_history_source_project",
                "fk_merge_history_target_project",
            },
            "analysis_job": {"fk_analysis_job_node_project"},
        }
        for table_name, expected in expected_project_fks.items():
            actual = {
                foreign_key["name"]
                for foreign_key in inspector.get_foreign_keys(table_name)
            }
            assert expected <= actual

        first = Node(
            project_id="project-a",
            source_meeting_id="meeting-a",
            source_item_id="node-a",
            node_type="DECISION",
            category="BACKEND",
            title="A",
            content="A",
            graph_state="ACTIVE",
        )
        second = Node(
            project_id="project-b",
            source_meeting_id="meeting-b",
            source_item_id="node-b",
            node_type="DECISION",
            category="BACKEND",
            title="B",
            content="B",
            graph_state="ACTIVE",
        )
        session.add_all([first, second])
        session.flush()

        session.add(
            Relation(
                project_id="project-a",
                from_node_id=first.id,
                to_node_id=second.id,
                relation_type="RELATED_TO",
                status="CONFIRMED",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_postgresql_rejects_invalid_node_state_at_the_database(session_factory):
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL-only database integrity constraints")
        session.add(
            Node(
                project_id="project-a",
                source_meeting_id="meeting-a",
                source_item_id="invalid-node",
                node_type="ACTION",
                category="BACKEND",
                title="invalid",
                content="invalid",
                graph_state="UNKNOWN",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


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
            == "0011_node_content_update_command"
    )


def test_node_update_command_schema_generalizes_existing_inbox(session_factory):
    inspector = inspect(_engine(session_factory))
    command_columns = {
        column["name"]: column
        for column in inspector.get_columns("meeting_analysis_command")
    }
    assert {
        "command_type",
        "target_node_id",
        "expected_node_version",
        "requested_by_member_id",
        "failure_code",
        "failure_message",
    } <= set(command_columns)
    assert command_columns["meeting_id"]["nullable"] is True
    assert command_columns["room_name"]["nullable"] is True
    artifact_columns = {
        column["name"]: column
        for column in inspector.get_columns("graph_snapshot_artifact")
    }
    assert artifact_columns["meeting_id"]["nullable"] is True


def test_0008_to_0009_upgrade_preserves_meeting_and_adds_graph_contract(
    tmp_path,
    monkeypatch,
):
    database_url = f"sqlite:///{tmp_path / '0008-to-0009.db'}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.upgrade(config, "0008_meeting_summary")
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO meeting "
                "(id, project_id, external_meeting_id, status, created_at, updated_at) "
                "VALUES (:id, '10', '501', 'COMPLETED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": uuid.uuid4().hex},
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = make_engine(database_url)
    inspector = inspect(engine)
    assert {"project_graph_state", "analysis_delivery_state"} <= set(
        inspector.get_table_names()
    )
    assert "deleted_by" in {
        column["name"] for column in inspector.get_columns("node")
    }
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM meeting WHERE project_id='10'")
        ).scalar_one() == 1
    engine.dispose()


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
        "retrieval_status",
        "retrieval_result_count",
        "retrieval_completed_at",
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
        "ck_analysis_run_retrieval_status",
        "ck_analysis_run_retrieval_count_non_negative",
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


def test_0004_backfills_existing_run_retrieval_stage(
    tmp_path,
    monkeypatch,
):
    database_url = f"sqlite:///{tmp_path / 'retrieval-stage.db'}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.upgrade(config, "0003_review_analysis")
    engine = make_engine(database_url)
    node_id = uuid.uuid4()
    run_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO node ("
                "id, project_id, source_meeting_id, source_item_id, "
                "node_type, category, title, content, graph_state, "
                "analysis_status, lifecycle_status, version"
                ") VALUES ("
                ":id, 'project-a', 'meeting-a', 'item-a', "
                "'DECISION', 'BACKEND', 'title', '', 'UNATTACHED', "
                "'ANALYZING', 'ACTIVE', 1"
                ")"
            ),
            {"id": node_id.hex},
        )
        connection.execute(
            text(
                "INSERT INTO node_analysis_run ("
                "id, source_node_id, source_node_version, "
                "analysis_input_hash, analysis_input_hash_version, "
                "retrieval_config_version, embedding_model, "
                "embedding_version, attempt, status, requested_by"
                ") VALUES ("
                ":id, :node_id, 1, :input_hash, 'analysis-input-v2', "
                "'retrieval-v1', 'text-embedding-3-small', 'v1', "
                "1, 'COMPLETED', 'reviewer'"
                ")"
            ),
            {
                "id": run_id.hex,
                "node_id": node_id.hex,
                "input_hash": "a" * 64,
            },
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = make_engine(database_url)
    with engine.connect() as connection:
        stored = connection.execute(
            text(
                "SELECT retrieval_status, retrieval_result_count, "
                "retrieval_completed_at FROM node_analysis_run "
                "WHERE id = :id"
            ),
            {"id": run_id.hex},
        ).one()
    engine.dispose()
    assert stored.retrieval_status == "PENDING"
    assert stored.retrieval_result_count is None
    assert stored.retrieval_completed_at is None


def test_0004_rejects_an_unowned_legacy_publishing_event(
    tmp_path,
    monkeypatch,
):
    database_url = f"sqlite:///{tmp_path / 'legacy-outbox-claim.db'}"
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.upgrade(config, "0003_review_analysis")
    event_id = uuid.uuid4().hex
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO outbox_event ("
                "id, event_type, aggregate_type, aggregate_id, project_id, "
                "schema_version, payload, status, created_at"
                ") VALUES ("
                ":id, 'ANALYSIS_QUEUED', 'node', 'node-1', 'project-a', "
                "'v2.2', '{}', 'PUBLISHING', CURRENT_TIMESTAMP"
                ")"
            ),
            {"id": event_id},
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match="legacy PUBLISHING"):
        command.upgrade(config, "head")

    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE outbox_event SET status = 'PENDING' WHERE id = :id"
            ),
            {"id": event_id},
        )
    engine.dispose()

    command.upgrade(config, "head")


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRESQL_URL"),
    reason="TEST_POSTGRESQL_URL is not configured for a disposable database",
)
def test_postgresql_0004_preserves_legacy_completed_run(monkeypatch):
    database_url = os.environ["TEST_POSTGRESQL_URL"]
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.upgrade(config, "0003_review_analysis")
    node_id = uuid.uuid4()
    run_id = uuid.uuid4()
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO node ("
                "id, project_id, source_meeting_id, source_item_id, "
                "node_type, category, title, content, graph_state, "
                "analysis_status, lifecycle_status, version"
                ") VALUES ("
                ":id, 'project-a', 'meeting-a', 'item-a', "
                "'DECISION', 'BACKEND', 'title', '', 'UNATTACHED', "
                "'ANALYZED', 'ACTIVE', 1"
                ")"
            ),
            {"id": node_id},
        )
        connection.execute(
            text(
                "INSERT INTO node_analysis_run ("
                "id, source_node_id, source_node_version, "
                "analysis_input_hash, analysis_input_hash_version, "
                "retrieval_config_version, embedding_model, "
                "embedding_version, attempt, status, requested_by, "
                "completed_at"
                ") VALUES ("
                ":id, :node_id, 1, :input_hash, 'analysis-input-v2', "
                "'retrieval-v1', 'text-embedding-3-small', 'v1', "
                "1, 'COMPLETED', 'reviewer', CURRENT_TIMESTAMP"
                ")"
            ),
            {
                "id": run_id,
                "node_id": node_id,
                "input_hash": "c" * 64,
            },
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = make_engine(database_url)
    with engine.connect() as connection:
        stored = connection.execute(
            text(
                "SELECT status, retrieval_status, "
                "retrieval_result_count FROM node_analysis_run "
                "WHERE id = :id"
            ),
            {"id": run_id},
        ).one()
    engine.dispose()
    assert stored.status == "COMPLETED"
    assert stored.retrieval_status == "PENDING"
    assert stored.retrieval_result_count is None


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
    steps = ROOT / "data_pipeline" / "storage" / "migrations" / "steps"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for folder in (revisions, steps)
        for path in sorted(folder.glob("*.py"))
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
        "0004_runtime_pipeline.py",
        "0005_manual_user_decisions.py",
        "0006_automatic_node_merge.py",
        "0007_drop_lifecycle_status.py",
        "0008_meeting_summary.py",
        "0009_graph_event_contract_v1.py",
        "0010_meeting_analysis_join_and_result_v3.py",
        "0011_node_content_update_command.py",
    }


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL_TEST", "").startswith("postgresql"),
    reason="requires a disposable PostgreSQL base URL",
)
def test_0010_postgresql_upgrade_downgrade_reupgrade(monkeypatch):
    database_url, admin_engine = _create_isolated_postgresql_database(
        os.environ["DATABASE_URL_TEST"]
    )
    try:
        _set_database_url(monkeypatch, database_url)
        config = _alembic_config()
        command.upgrade(config, "0009_graph_event_contract_v1")
        command.upgrade(config, "head")
        engine = make_engine(database_url)
        assert {
            "recording_ready_event",
            "meeting_analysis_command",
            "meeting_analysis_task",
            "graph_snapshot_artifact",
        } <= set(inspect(engine).get_table_names())
        engine.dispose()

        command.downgrade(config, "0009_graph_event_contract_v1")
        engine = make_engine(database_url)
        assert not {
            "recording_ready_event",
            "meeting_analysis_command",
            "meeting_analysis_task",
            "graph_snapshot_artifact",
        } & set(inspect(engine).get_table_names())
        engine.dispose()

        command.upgrade(config, "head")
        engine = make_engine(database_url)
        assert {
            "recording_ready_event",
            "meeting_analysis_command",
            "meeting_analysis_task",
            "graph_snapshot_artifact",
        } <= set(inspect(engine).get_table_names())
        engine.dispose()
    finally:
        _drop_isolated_postgresql_database(database_url, admin_engine)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL_TEST", "").startswith("postgresql"),
    reason="requires a disposable PostgreSQL base URL",
)
def test_0006_honestly_backfills_legacy_revision_and_evidence(monkeypatch):
    database_url, admin_engine = _create_isolated_postgresql_database(
        os.environ["DATABASE_URL_TEST"]
    )
    try:
        _set_database_url(monkeypatch, database_url)
        config = _alembic_config()
        command.upgrade(config, "0005_manual_user_decisions")
        engine = make_engine(database_url)
        project = "legacy-project"
        meeting = "legacy-meeting"
        node_id = uuid.uuid4()
        segment_db_id = uuid.uuid4()
        quote = "legacy evidence"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO meeting ("
                    "id, project_id, external_meeting_id, status, created_at, updated_at"
                    ") VALUES (:id, :project, :meeting, 'COMPLETED', now(), now())"
                ),
                {"id": uuid.uuid4(), "project": project, "meeting": meeting},
            )
            connection.execute(
                text(
                    "INSERT INTO node ("
                    "id, project_id, source_meeting_id, source_item_id, node_type, "
                    "category, title, content, graph_state, analysis_status, "
                    "lifecycle_status, version, created_at, updated_at"
                    ") VALUES ("
                    ":id, :project, :meeting, 'legacy-item', 'DECISION', "
                    "'BACKEND', 'legacy title', 'legacy content', 'ACTIVE', "
                    "'ANALYZED', 'ACTIVE', 3, now(), now())"
                ),
                {"id": node_id, "project": project, "meeting": meeting},
            )
            connection.execute(
                text(
                    "INSERT INTO transcript_segment ("
                    "id, project_id, external_meeting_id, segment_id, sequence_no, "
                    "text, raw_text, normalized_text"
                    ") VALUES ("
                    ":id, :project, :meeting, 's1', 0, :quote, :quote, :quote)"
                ),
                {
                    "id": segment_db_id,
                    "project": project,
                    "meeting": meeting,
                    "quote": quote,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO node_evidence ("
                    "id, node_id, evidence_key, segment_id, quote, quote_start, "
                    "quote_end, evidence_type, source_meeting_id"
                    ") VALUES ("
                    ":id, :node_id, :key, 's1', :quote, 0, :quote_end, "
                    "'MEETING', :meeting)"
                ),
                {
                    "id": uuid.uuid4(),
                    "node_id": node_id,
                    "key": uuid.uuid4().hex + uuid.uuid4().hex,
                    "quote": quote,
                    "quote_end": len(quote),
                    "meeting": meeting,
                },
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = make_engine(database_url)
        with engine.connect() as connection:
            node = connection.execute(
                text(
                    "SELECT current_revision_id, origin_type "
                    "FROM node WHERE id = :id"
                ),
                {"id": node_id},
            ).mappings().one()
            revision = connection.execute(
                text(
                    "SELECT version, requires_evidence, legacy_imported "
                    "FROM node_revision WHERE id = :id"
                ),
                {"id": node["current_revision_id"]},
            ).mappings().one()
            evidence = connection.execute(
                text(
                    "SELECT source_type, quoted_text, transcript_segment_id "
                    "FROM evidence"
                )
            ).mappings().one()
            assert node["origin_type"] == "LEGACY"
            assert revision["version"] == 3
            assert revision["requires_evidence"] is False
            assert revision["legacy_imported"] is True
            assert evidence["source_type"] == "TRANSCRIPT"
            assert evidence["quoted_text"] == quote
            assert evidence["transcript_segment_id"] == segment_db_id
        engine.dispose()
    finally:
        _drop_isolated_postgresql_database(database_url, admin_engine)


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRESQL_URL"),
    reason="TEST_POSTGRESQL_URL is not configured for a disposable database",
)
def test_disposable_postgresql_migration_round_trip(monkeypatch):
    database_url = os.environ["TEST_POSTGRESQL_URL"]
    _set_database_url(monkeypatch, database_url)
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "0003_review_analysis")

    node_id = uuid.uuid4()
    run_id = uuid.uuid4()
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO node ("
                "id, project_id, source_meeting_id, source_item_id, "
                "node_type, category, title, content, graph_state, "
                "analysis_status, lifecycle_status, version"
                ") VALUES ("
                ":id, 'project-a', 'meeting-a', 'item-a', "
                "'DECISION', 'BACKEND', 'title', '', 'UNATTACHED', "
                "'ANALYZING', 'ACTIVE', 1"
                ")"
            ),
            {"id": node_id},
        )
        connection.execute(
            text(
                "INSERT INTO node_analysis_run ("
                "id, source_node_id, source_node_version, "
                "analysis_input_hash, analysis_input_hash_version, "
                "retrieval_config_version, embedding_model, "
                "embedding_version, attempt, status, requested_by"
                ") VALUES ("
                ":id, :node_id, 1, :input_hash, 'analysis-input-v2', "
                "'retrieval-v1', 'text-embedding-3-small', 'v1', "
                "1, 'RUNNING', 'reviewer'"
                ")"
            ),
            {
                "id": run_id,
                "node_id": node_id,
                "input_hash": "b" * 64,
            },
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = make_engine(database_url)
    with engine.connect() as connection:
        stored = connection.execute(
            text(
                "SELECT retrieval_status, retrieval_result_count "
                "FROM node_analysis_run WHERE id = :id"
            ),
            {"id": run_id},
        ).one()
    engine.dispose()
    assert stored.retrieval_status == "PENDING"
    assert stored.retrieval_result_count is None

    # 0006 intentionally blocks physical Revision/Evidence deletion. First
    # downgrade only that revision so its immutable trigger and additive tables
    # are removed, then clear this disposable fixture before exercising the
    # historical base round trip. A populated production DB must be backed up
    # and migrated forward; head->base is not a data-preserving operation.
    command.downgrade(config, "0005_manual_user_decisions")
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM node_analysis_run WHERE id = :id"),
            {"id": run_id},
        )
        connection.execute(
            text("DELETE FROM node WHERE id = :id"),
            {"id": node_id},
        )
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
