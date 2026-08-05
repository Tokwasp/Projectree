from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from data_pipeline.config import load_settings
from data_pipeline.pipeline import (
    AnalysisRunIncompleteError,
    AnalysisRunStateError,
    CrossProjectRetrievalError,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    AnalysisRunNotFoundError,
    RetrievalExecutionError,
    edit_unattached_node,
    execute_analysis_retrieval,
    mark_analysis_run_completed,
    reanalyze_unattached_node,
    seed_node,
)
from data_pipeline.retrieval import RetrievedNode
from data_pipeline.storage import (
    Node,
    NodeAnalysisRun,
    NodeEmbedding,
    RetrievalResult,
)

from .test_unattached_node_edit import _initial_node
from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION

DIMENSION = 1536


def _vector(first: float, second: float = 0.0) -> list[float]:
    return [first, second, *([0.0] * (DIMENSION - 2))]


class FakeEmbeddingClient:
    def __init__(self, vector=None, error: Exception | None = None):
        self.vector = vector or _vector(1.0)
        self.error = error
        self.calls: list[dict] = []

    def embed(self, *, text: str, model: str, dimensions: int):
        self.calls.append(
            {
                "text": text,
                "model": model,
                "dimensions": dimensions,
            }
        )
        if self.error is not None:
            raise self.error
        return self.vector


def _requested_run(session_factory, *, meeting_id: str):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id=meeting_id,
    )
    requested = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    return node_id, requested.run.analysis_run_id


def _target(
    session,
    *,
    project_id: str,
    source_item_id: str,
    graph_state: str,
    vector: list[float],
):
    node = seed_node(
        session,
        project_id=project_id,
        source_meeting_id=f"M-{source_item_id}",
        source_item_id=source_item_id,
        node_type="DECISION",
        category="BACKEND",
        title=source_item_id,
        graph_state=graph_state,
    )
    session.add(
        NodeEmbedding(
            node_id=node.id,
            embedding_version=EMBEDDING_CONTRACT_VERSION,
            embedding_model="text-embedding-3-small",
            dimension=DIMENSION,
            embedded_text_hash="target-hash",
            embedding=vector,
            status="READY",
        )
    )
    session.flush()
    return node


def test_completion_is_rejected_before_and_after_retrieval(
    session_factory,
):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-COMPLETION-GUARD",
    )

    with pytest.raises(AnalysisRunIncompleteError) as before:
        mark_analysis_run_completed(
            session_factory,
            run_id,
            project_id="proj-01",
        )
    assert before.value.missing_results == (
        "EMBEDDING",
        "RETRIEVAL",
        "B_MODEL_OR_FINAL_CANDIDATE",
    )

    result = execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(),
    )
    assert result.run.status.value == "RUNNING"
    assert result.run.retrieval_status.value == "COMPLETED"
    assert result.node_analysis_status.value == "ANALYZING"

    with pytest.raises(AnalysisRunIncompleteError) as after:
        mark_analysis_run_completed(
            session_factory,
            run_id,
            project_id="proj-01",
        )
    assert after.value.missing_results == (
        "B_MODEL_SKIPPED_RESULT",
    )
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert node.analysis_status == "ANALYZING"
        assert run.status == "RUNNING"
        assert run.completed_at is None


def test_embedding_is_stored_and_same_run_is_idempotent(session_factory):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-EMBEDDING-IDEMPOTENT",
    )
    client = FakeEmbeddingClient()

    first = execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=client,
    )
    repeated = execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=client,
    )

    assert first.embedding_created is True
    assert repeated.embedding_created is False
    assert len(client.calls) == 1
    assert client.calls[0]["dimensions"] == DIMENSION
    assert first.run.retrieval_result_count == 0
    assert repeated.retrieval_results == []
    with session_factory() as session:
        stored = session.get(
            NodeEmbedding,
            {
                "node_id": uuid.UUID(node_id),
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        )
        assert stored.status == "READY"
        assert stored.dimension == DIMENSION
        assert stored.embedding == _vector(1.0)
        assert stored.embedded_text_hash
        assert session.query(NodeEmbedding).count() == 1
        assert session.query(NodeAnalysisRun).count() == 1


def test_embedding_failure_marks_run_failed_without_partial_results(
    session_factory,
):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-EMBEDDING-FAILURE",
    )

    with pytest.raises(EmbeddingGenerationError):
        execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="proj-01",
            embedding_client=FakeEmbeddingClient(
                error=RuntimeError("offline fake failure")
            ),
        )

    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert node.analysis_status == "FAILED"
        assert run.status == "FAILED"
        assert run.failure_code == "EMBEDDING_FAILED"
        assert session.query(NodeEmbedding).count() == 0
        assert session.query(RetrievalResult).count() == 0


def test_invalid_embedding_dimension_marks_run_failed(session_factory):
    _, run_id = _requested_run(
        session_factory,
        meeting_id="M-EMBEDDING-DIMENSION",
    )

    with pytest.raises(EmbeddingValidationError):
        execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="proj-01",
            embedding_client=FakeEmbeddingClient([1.0, 0.0]),
        )

    with session_factory() as session:
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert run.status == "FAILED"
        assert run.failure_code == "EMBEDDING_INVALID"
        assert session.query(NodeEmbedding).count() == 0


def test_retrieval_filters_scope_state_self_threshold_and_top_k(
    monkeypatch,
    session_factory,
):
    monkeypatch.setenv("RETRIEVAL_NODE_TOP_K", "2")
    monkeypatch.setenv("RETRIEVAL_MIN_SIMILARITY", "0.5")
    load_settings.cache_clear()
    try:
        _, run_id = _requested_run(
            session_factory,
            meeting_id="M-RETRIEVAL-FILTERS",
        )
        with session_factory() as session:
            closest = _target(
                session,
                project_id="proj-01",
                source_item_id="closest",
                graph_state="ACTIVE",
                vector=_vector(1.0),
            )
            unattached = _target(
                session,
                project_id="proj-01",
                source_item_id="unattached",
                graph_state="UNATTACHED",
                vector=_vector(0.8, 0.6),
            )
            third_eligible = _target(
                session,
                project_id="proj-01",
                source_item_id="third-eligible",
                graph_state="ACTIVE",
                vector=_vector(0.6, 0.8),
            )
            _target(
                session,
                project_id="proj-01",
                source_item_id="below-threshold",
                graph_state="ACTIVE",
                vector=_vector(0.0, 1.0),
            )
            _target(
                session,
                project_id="project-b",
                source_item_id="other-project",
                graph_state="ACTIVE",
                vector=_vector(1.0),
            )
            seed_node(
                session,
                project_id="proj-01",
                source_meeting_id="M-no-embedding",
                source_item_id="no-embedding",
                node_type="DECISION",
                category="BACKEND",
                title="no-embedding",
                graph_state="ACTIVE",
            )
            _target(
                session,
                project_id="proj-01",
                source_item_id="archived",
                graph_state="ARCHIVED",
                vector=_vector(1.0),
            )
            _target(
                session,
                project_id="proj-01",
                source_item_id="excluded",
                graph_state="EXCLUDED",
                vector=_vector(1.0),
            )
            merged = _target(
                session,
                project_id="proj-01",
                source_item_id="merged",
                graph_state="ACTIVE",
                vector=_vector(1.0),
            )
            merged.graph_state = "MERGED"
            merged.merged_into_node_id = closest.id
            expected_ids = [str(closest.id), str(third_eligible.id)]
            session.commit()

        result = execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="proj-01",
            embedding_client=FakeEmbeddingClient(_vector(1.0)),
        )

        assert [
            row.target_node_id for row in result.retrieval_results
        ] == expected_ids
        assert [
            row.similarity for row in result.retrieval_results
        ] == pytest.approx([1.0, 0.6])
        assert [row.rank for row in result.retrieval_results] == [1, 2]
    finally:
        load_settings.cache_clear()


def test_equal_similarity_uses_node_uuid_as_stable_tie_break(
    session_factory,
):
    _, run_id = _requested_run(
        session_factory,
        meeting_id="M-RETRIEVAL-TIE",
    )
    with session_factory() as session:
        first = _target(
            session,
            project_id="proj-01",
            source_item_id="tie-a",
            graph_state="ACTIVE",
            vector=_vector(1.0),
        )
        second = _target(
            session,
            project_id="proj-01",
            source_item_id="tie-b",
            graph_state="ACTIVE",
            vector=_vector(1.0),
        )
        expected = sorted([str(first.id), str(second.id)])
        session.commit()

    result = execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(),
    )

    assert [
        row.target_node_id for row in result.retrieval_results
    ] == expected


def test_retrieval_failure_rolls_back_embedding_and_results(
    monkeypatch,
    session_factory,
):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-RETRIEVAL-FAILURE",
    )

    def fail_search(*args, **kwargs):
        raise RetrievalExecutionError("offline retrieval failure")

    monkeypatch.setattr(
        "data_pipeline.pipeline.analysis.search_scoped_candidates",
        fail_search,
    )
    with pytest.raises(RetrievalExecutionError):
        execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="proj-01",
            embedding_client=FakeEmbeddingClient(),
        )

    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert node.analysis_status == "FAILED"
        assert run.status == "FAILED"
        assert run.retrieval_status == "FAILED"
        assert run.failure_code == "RETRIEVAL_FAILED"
        assert session.query(NodeEmbedding).count() == 0
        assert session.query(RetrievalResult).count() == 0


def test_cross_project_retrieval_leak_fails_and_rolls_back(
    monkeypatch,
    session_factory,
):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-RETRIEVAL-CROSS-PROJECT",
    )

    def leak_cross_project(*args, **kwargs):
        raise CrossProjectRetrievalError("cross-project candidate")

    monkeypatch.setattr(
        "data_pipeline.pipeline.analysis.search_scoped_candidates",
        leak_cross_project,
    )
    with pytest.raises(CrossProjectRetrievalError):
        execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="proj-01",
            embedding_client=FakeEmbeddingClient(),
        )

    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert node.project_id == "proj-01"
        assert node.analysis_status == "FAILED"
        assert run.status == "FAILED"
        assert session.query(NodeEmbedding).count() == 0
        assert session.query(RetrievalResult).count() == 0


def test_execute_analysis_retrieval_wrong_project_is_not_found_and_unchanged(
    session_factory,
):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-EXECUTE-WRONG-PROJECT",
    )
    client = FakeEmbeddingClient()

    with pytest.raises(AnalysisRunNotFoundError):
        execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="project-b",
            embedding_client=client,
        )

    assert client.calls == []
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert node.analysis_status == "PENDING"
        assert run.status == "PENDING"
        assert run.retrieval_status == "PENDING"
        assert session.query(NodeEmbedding).count() == 0
        assert session.query(RetrievalResult).count() == 0


def test_postgresql_stores_real_pgvector_value(session_factory):
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL pgvector")

    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-PGVECTOR-STORAGE",
    )
    execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(),
    )

    with session_factory() as session:
        stored = session.execute(
            text(
                "SELECT embedding::text FROM node_embedding "
                "WHERE node_id = :node_id"
            ),
            {"node_id": uuid.UUID(node_id)},
        ).scalar_one()
        assert stored.startswith("[1,")
        assert stored.endswith("]")


def test_legacy_completed_run_is_reused_without_new_completion_checks(
    session_factory,
):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-LEGACY-COMPLETED",
    )
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        node.analysis_status = "ANALYZED"
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        session.commit()

    replayed = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    completed = mark_analysis_run_completed(
        session_factory,
        run_id,
        project_id="proj-01",
    )
    client = FakeEmbeddingClient()
    with pytest.raises(AnalysisRunStateError):
        execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="proj-01",
            embedding_client=client,
        )

    assert replayed.created is False
    assert replayed.run.analysis_run_id == run_id
    assert replayed.run.status.value == "COMPLETED"
    assert completed.status.value == "COMPLETED"
    assert completed.retrieval_status.value == "PENDING"
    assert client.calls == []
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert node.analysis_status == "ANALYZED"
        assert run.status == "COMPLETED"
        assert run.retrieval_status == "PENDING"
        assert session.query(NodeAnalysisRun).count() == 1


def test_embedding_invalidation_is_changed_only_and_project_scoped(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-EMBEDDING-INVALIDATION",
    )
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        other = seed_node(
            session,
            project_id="project-b",
            source_meeting_id="M-OTHER-PROJECT",
            source_item_id="other-node",
            node_type="DECISION",
            category="BACKEND",
            title="other",
        )
        for target in (node, other):
            session.add(
                NodeEmbedding(
                    node_id=target.id,
                    embedding_version=EMBEDDING_CONTRACT_VERSION,
                    embedding_model="text-embedding-3-small",
                    dimension=DIMENSION,
                    embedded_text_hash="ready-hash",
                    embedding=_vector(1.0),
                    status="READY",
                )
            )
        other_id = other.id
        session.commit()

    replayed = edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="editor",
        expected_version=1,
        title="Redis 캐시 결정",
    )
    assert replayed.analysis_invalidated is False
    with session_factory() as session:
        source_embedding = session.get(
            NodeEmbedding,
            {
                "node_id": uuid.UUID(node_id),
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        )
        assert source_embedding.status == "READY"

    changed = edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="editor",
        expected_version=1,
        title="변경된 Redis 캐시 결정",
    )
    assert changed.analysis_invalidated is True
    with session_factory() as session:
        source_embedding = session.get(
            NodeEmbedding,
            {
                "node_id": uuid.UUID(node_id),
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        )
        other_embedding = session.get(
            NodeEmbedding,
            {
                "node_id": other_id,
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        )
        assert source_embedding.status == "STALE"
        assert other_embedding.status == "READY"


def test_embedding_invalidation_rolls_back_with_node_edit(session_factory):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-EMBEDDING-ROLLBACK",
    )
    with session_factory() as session:
        session.add(
            NodeEmbedding(
                node_id=uuid.UUID(node_id),
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=DIMENSION,
                embedded_text_hash="ready-hash",
                embedding=_vector(1.0),
                status="READY",
            )
        )
        session.commit()

    def fail_commit(session):
        raise RuntimeError("forced transaction rollback")

    event.listen(Session, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="forced transaction rollback"):
            edit_unattached_node(
                session_factory,
                node_id,
                project_id="proj-01",
                actor_id="editor",
                expected_version=1,
                title="rollback title",
            )
    finally:
        event.remove(Session, "before_commit", fail_commit)

    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        embedding = session.get(
            NodeEmbedding,
            {
                "node_id": uuid.UUID(node_id),
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        )
        assert node.title == "Redis 캐시 결정"
        assert node.version == 1
        assert embedding.status == "READY"


def test_database_rejects_duplicate_embedding_and_retrieval_target(
    session_factory,
):
    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-DB-DUPLICATES",
    )
    with session_factory() as session:
        target = seed_node(
            session,
            project_id="proj-01",
            source_meeting_id="M-DUPLICATE-TARGET",
            source_item_id="duplicate-target",
            node_type="DECISION",
            category="BACKEND",
            title="target",
        )
        target_id = target.id
        session.add(
            RetrievalResult(
                analysis_run_id=uuid.UUID(run_id),
                target_node_id=target.id,
                target_node_version=target.version,
                rank=1,
                similarity=0.9,
            )
        )
        session.commit()

    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(
                RetrievalResult(
                    analysis_run_id=uuid.UUID(run_id),
                    target_node_id=target_id,
                    target_node_version=1,
                    rank=2,
                    similarity=0.8,
                )
            )
            session.commit()

    with session_factory() as session:
        session.add(
            NodeEmbedding(
                node_id=uuid.UUID(node_id),
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=DIMENSION,
                embedded_text_hash="same-input-hash",
                embedding=_vector(1.0),
                status="READY",
            )
        )
        session.commit()
    with pytest.raises(IntegrityError):
        with session_factory() as session:
            session.add(
                NodeEmbedding(
                    node_id=uuid.UUID(node_id),
                    embedding_version=EMBEDDING_CONTRACT_VERSION,
                    embedding_model="text-embedding-3-small",
                    dimension=DIMENSION,
                    embedded_text_hash="same-input-hash",
                    embedding=_vector(1.0),
                    status="READY",
                )
            )
            session.commit()

    with session_factory() as session:
        assert session.query(RetrievalResult).count() == 1
        assert session.query(NodeEmbedding).count() == 1


@pytest.mark.parametrize("client_fails", [False, True])
def test_obsolete_run_cannot_overwrite_new_run(
    session_factory,
    client_fails,
):
    node_id, run_a_id = _requested_run(
        session_factory,
        meeting_id=f"M-OBSOLETE-{client_fails}",
    )
    run_b_id = None

    class SupersedingClient:
        def embed(self, *, text: str, model: str, dimensions: int):
            nonlocal run_b_id
            edit_unattached_node(
                session_factory,
                node_id,
                project_id="proj-01",
                actor_id="editor",
                expected_version=1,
                title="new analysis input",
            )
            run_b = reanalyze_unattached_node(
                session_factory,
                node_id,
                project_id="proj-01",
                actor_id="reviewer",
                expected_version=2,
                retrieval_config_version="retrieval-test-v1",
            )
            run_b_id = run_b.run.analysis_run_id
            if client_fails:
                raise RuntimeError("old worker failed late")
            return _vector(1.0)

    expected_error = (
        EmbeddingGenerationError if client_fails else AnalysisRunStateError
    )
    with pytest.raises(expected_error):
        execute_analysis_retrieval(
            session_factory,
            run_a_id,
            project_id="proj-01",
            embedding_client=SupersedingClient(),
        )

    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run_a = session.get(NodeAnalysisRun, uuid.UUID(run_a_id))
        run_b = session.get(NodeAnalysisRun, uuid.UUID(run_b_id))
        assert node.version == 2
        assert node.analysis_status == "PENDING"
        assert str(node.current_analysis_run_id) == run_b_id
        assert run_a.status == "SUPERSEDED"
        assert run_b.status == "PENDING"
        assert run_b.failure_code is None
        assert session.query(NodeEmbedding).count() == 0
        assert session.query(RetrievalResult).count() == 0


def test_stale_embedding_is_regenerated_through_operating_service(
    session_factory,
):
    node_id, first_run_id = _requested_run(
        session_factory,
        meeting_id="M-STALE-REGENERATE",
    )
    execute_analysis_retrieval(
        session_factory,
        first_run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(_vector(1.0)),
    )
    with session_factory() as session:
        before_hash = session.get(
            NodeEmbedding,
            {
                "node_id": uuid.UUID(node_id),
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        ).embedded_text_hash

    edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="editor",
        expected_version=1,
        title="regenerated input",
    )
    second = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=2,
        retrieval_config_version="retrieval-test-v1",
    )
    client = FakeEmbeddingClient(_vector(0.0, 1.0))
    result = execute_analysis_retrieval(
        session_factory,
        second.run.analysis_run_id,
        project_id="proj-01",
        embedding_client=client,
    )

    assert result.embedding_created is True
    assert len(client.calls) == 1
    with session_factory() as session:
        embedding = session.get(
            NodeEmbedding,
            {
                "node_id": uuid.UUID(node_id),
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        )
        assert embedding.status == "READY"
        assert embedding.embedded_text_hash != before_hash
        assert embedding.embedding == _vector(0.0, 1.0)


def test_concurrent_analysis_service_keeps_one_embedding_and_result_set(
    session_factory,
):
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL row locks")

    node_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-CONCURRENT-ANALYSIS-SERVICE",
    )
    with session_factory() as session:
        _target(
            session,
            project_id="proj-01",
            source_item_id="concurrent-target",
            graph_state="ACTIVE",
            vector=_vector(1.0),
        )
        session.commit()

    barrier = Barrier(2)

    class ConcurrentClient:
        def embed(self, *, text: str, model: str, dimensions: int):
            barrier.wait(timeout=5)
            return _vector(1.0)

    def execute(_):
        return execute_analysis_retrieval(
            session_factory,
            run_id,
            project_id="proj-01",
            embedding_client=ConcurrentClient(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(execute, range(2)))

    assert all(result.run.retrieval_result_count == 1 for result in results)
    with session_factory() as session:
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        source_embeddings = session.query(NodeEmbedding).filter(
            NodeEmbedding.node_id == uuid.UUID(node_id)
        ).count()
        actual_results = session.query(RetrievalResult).filter(
            RetrievalResult.analysis_run_id == uuid.UUID(run_id)
        ).count()
        assert source_embeddings == 1
        assert actual_results == 1
        assert run.retrieval_result_count == actual_results
