from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError

from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
from data_pipeline.pipeline import (
    AnalysisRunIncompleteError,
    edit_unattached_node,
    mark_analysis_run_completed,
    mark_analysis_run_failed,
    mark_analysis_run_running,
    reanalyze_unattached_node,
    seed_node,
)
from data_pipeline.storage import Node, NodeAnalysisRun, RetrievalResult

from .test_unattached_node_edit import _initial_node


def test_reanalyze_is_idempotent_for_same_node_version_and_hash(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-IDEMPOTENT",
    )

    created = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    repeated = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="other-reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )

    assert created.created is True
    assert repeated.created is False
    assert repeated.run.analysis_run_id == created.run.analysis_run_id
    assert repeated.run.attempt == 1
    assert repeated.run.status.value == "PENDING"
    assert repeated.run.embedding_model == "text-embedding-3-small"
    assert repeated.run.embedding_version == EMBEDDING_CONTRACT_VERSION
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        assert node.version == 1
        assert node.analysis_status == "PENDING"
        assert str(node.current_analysis_run_id) == created.run.analysis_run_id
        assert session.query(NodeAnalysisRun).count() == 1
        assert session.query(RetrievalResult).count() == 0


def test_concurrent_reanalyze_returns_one_run_on_postgresql(
    session_factory,
):
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL row locks and partial indexes")

    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-CONCURRENT",
    )
    barrier = Barrier(2)

    def request_run(actor_id: str):
        barrier.wait(timeout=5)
        return reanalyze_unattached_node(
            session_factory,
            node_id,
            project_id="proj-01",
            actor_id=actor_id,
            expected_version=1,
            retrieval_config_version="retrieval-test-v1",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(request_run, ["reviewer-1", "reviewer-2"])
        )

    assert sorted(result.created for result in results) == [False, True]
    assert len(
        {result.run.analysis_run_id for result in results}
    ) == 1
    with session_factory() as session:
        assert session.query(NodeAnalysisRun).count() == 1


def test_database_rejects_duplicate_active_run_for_same_node_and_hash(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-ACTIVE-UNIQUE",
    )
    first = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )

    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(
                NodeAnalysisRun(
                    source_node_id=uuid.UUID(node_id),
                    source_node_version=1,
                    analysis_input_hash=first.run.analysis_input_hash,
                    analysis_input_hash_version=(
                        first.run.analysis_input_hash_version
                    ),
                    retrieval_config_version="retrieval-test-v1",
                    embedding_model=first.run.embedding_model,
                    embedding_version=first.run.embedding_version,
                    attempt=2,
                    status="RUNNING",
                    requested_by="duplicate-worker",
                )
            )
            session.commit()


def test_reanalyze_prefers_existing_active_run_over_newer_failed_attempt(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-ACTIVE-BEFORE-FAILED",
    )
    active = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    with session_factory() as session:
        session.add(
            NodeAnalysisRun(
                source_node_id=uuid.UUID(node_id),
                source_node_version=1,
                analysis_input_hash=active.run.analysis_input_hash,
                analysis_input_hash_version=(
                    active.run.analysis_input_hash_version
                ),
                retrieval_config_version="retrieval-test-v1",
                embedding_model=active.run.embedding_model,
                embedding_version=active.run.embedding_version,
                attempt=2,
                status="FAILED",
                requested_by="legacy-worker",
                failure_code="LEGACY_FAILURE",
            )
        )
        session.commit()

    repeated = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )

    assert repeated.created is False
    assert repeated.run.analysis_run_id == active.run.analysis_run_id
    assert repeated.run.status.value == "PENDING"
    with session_factory() as session:
        assert session.query(NodeAnalysisRun).count() == 2


def test_analysis_status_change_updates_run_timestamp(session_factory):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-UPDATED-AT",
    )
    requested = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    with session_factory() as session:
        before = session.get(
            NodeAnalysisRun,
            uuid.UUID(requested.run.analysis_run_id),
        ).updated_at

    mark_analysis_run_running(
        session_factory,
        requested.run.analysis_run_id,
        project_id="proj-01",
    )
    with session_factory() as session:
        after = session.get(
            NodeAnalysisRun,
            uuid.UUID(requested.run.analysis_run_id),
        ).updated_at

    assert after > before


def test_database_rejects_non_positive_retrieval_target_version(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-TARGET-VERSION",
    )
    requested = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            target = seed_node(
                session,
                project_id="proj-01",
                source_meeting_id="M-TARGET",
                source_item_id="target",
                node_type="DECISION",
                category="BACKEND",
                title="검색 대상",
            )
            session.flush()
            session.add(
                RetrievalResult(
                    analysis_run_id=uuid.UUID(
                        requested.run.analysis_run_id
                    ),
                    target_node_id=target.id,
                    target_node_version=0,
                    rank=1,
                    similarity=0.9,
                )
            )
            session.commit()


def test_analysis_execution_transitions_without_incrementing_node_version(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-TRANSITIONS",
    )
    requested = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )

    running = mark_analysis_run_running(
        session_factory,
        requested.run.analysis_run_id,
        project_id="proj-01",
    )
    assert running.status.value == "RUNNING"
    with pytest.raises(AnalysisRunIncompleteError):
        mark_analysis_run_completed(
            session_factory,
            requested.run.analysis_run_id,
            project_id="proj-01",
        )
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        assert node.analysis_status == "ANALYZING"
        assert node.version == 1
        assert session.query(NodeAnalysisRun).count() == 1


def test_only_failed_run_creates_retry_attempt(session_factory):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-RETRY",
    )
    first = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    mark_analysis_run_running(
        session_factory,
        first.run.analysis_run_id,
        project_id="proj-01",
    )
    failed = mark_analysis_run_failed(
        session_factory,
        first.run.analysis_run_id,
        project_id="proj-01",
        failure_code="RETRIEVAL_FAILED",
        failure_message="temporary failure",
    )
    assert failed.status.value == "FAILED"

    retry = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    repeated_retry = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )

    assert retry.created is True
    assert retry.run.attempt == 2
    assert retry.run.status.value == "PENDING"
    assert repeated_retry.created is False
    assert repeated_retry.run.analysis_run_id == retry.run.analysis_run_id
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        assert node.analysis_status == "PENDING"
        assert node.version == 1
        assert session.query(NodeAnalysisRun).count() == 2


def test_edit_supersedes_current_run_and_new_version_gets_new_run(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-SUPERSEDE",
    )
    first = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    mark_analysis_run_running(
        session_factory,
        first.run.analysis_run_id,
        project_id="proj-01",
    )

    edited = edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="editor",
        expected_version=1,
        title="분석 입력이 달라진 제목",
    )
    assert edited.node.version == 2
    assert edited.node.analysis_status == "STALE"

    second = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=2,
        retrieval_config_version="retrieval-test-v1",
    )
    assert second.created is True
    assert second.run.source_node_version == 2
    assert second.run.attempt == 1
    assert second.run.analysis_run_id != first.run.analysis_run_id
    with session_factory() as session:
        old_run = session.get(
            NodeAnalysisRun,
            uuid.UUID(first.run.analysis_run_id),
        )
        node = session.get(Node, uuid.UUID(node_id))
        assert old_run.status == "SUPERSEDED"
        assert node.analysis_status == "PENDING"
        assert node.version == 2


def test_new_config_hash_supersedes_pending_run_without_node_version_change(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-ANALYSIS-CONFIG",
    )
    first = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    second = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v2",
    )

    assert second.created is True
    assert second.run.analysis_input_hash != first.run.analysis_input_hash
    with session_factory() as session:
        old_run = session.get(
            NodeAnalysisRun,
            uuid.UUID(first.run.analysis_run_id),
        )
        node = session.get(Node, uuid.UUID(node_id))
        assert old_run.status == "SUPERSEDED"
        assert node.current_analysis_run_id == uuid.UUID(
            second.run.analysis_run_id
        )
        assert node.version == 1
