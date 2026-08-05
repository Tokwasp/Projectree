"""Analysis Worker: claim, run, retry, restart recovery, no duplicate analysis."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from data_pipeline.analysis_worker import AnalysisWorker
from data_pipeline.jobs import enqueue_analysis_job
from data_pipeline.pipeline import seed_node
from data_pipeline.pipeline.errors import NodeStateError
from data_pipeline.retrieval.errors import EmbeddingGenerationError
from data_pipeline.storage import AnalysisJob, NodeEmbedding, OutboxEvent

PROJECT = "proj-worker"
MEETING = "meet-worker"
DIM = 1536


class _Embedding:
    def __init__(self, *, fail: Exception | None = None):
        self._fail = fail
        self.calls = 0

    def embed(self, *, text: str, model: str, dimensions: int):
        del text, model
        self.calls += 1
        if self._fail is not None:
            raise self._fail
        return [1.0, *([0.0] * (dimensions - 1))]


class _BModel:
    def __init__(self):
        self.calls = 0

    def recommend(self, *, source_node, retrieval_candidates, model):
        del source_node, retrieval_candidates, model
        self.calls += 1
        raise AssertionError("should not be called without retrieval candidates")


def _seed(session_factory, *, item="w1", state="UNATTACHED"):
    with session_factory() as session:
        node = seed_node(
            session,
            project_id=PROJECT,
            source_meeting_id=MEETING,
            source_item_id=item,
            node_type="DECISION",
            category="INFRA",
            title="배포 기준",
            content="배포 기준을 정한다",
            graph_state=state,
            evidence=[{"segmentId": "s1", "quote": "배포 기준을 정한다"}],
        )
        session.commit()
        return node.id, node.version


def _queue(session_factory, node_id, version):
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id=PROJECT,
            external_meeting_id=MEETING,
            node_id=node_id,
            node_version=version,
        )
        session.commit()


def _worker(session_factory, *, embedding=None, b_model=None) -> AnalysisWorker:
    return AnalysisWorker(
        session_factory=session_factory,
        embedding_client=embedding or _Embedding(),
        b_model_client=b_model or _BModel(),
    )


def test_worker_is_idle_when_there_is_no_job(session_factory) -> None:
    result = _worker(session_factory).run_once()
    assert result.claimed == 0


def test_worker_runs_a_job_to_success(session_factory) -> None:
    """With no other embedded Node, Retrieval finds nothing and B is skipped."""

    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)
    embedding = _Embedding()
    b_model = _BModel()

    result = _worker(session_factory, embedding=embedding, b_model=b_model).run_once()

    assert result.claimed == 1
    assert result.succeeded == 1
    assert embedding.calls == 1
    assert b_model.calls == 0  # skipped: no retrieval candidates
    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.status == "SUCCEEDED"
        assert job.analysis_run_id is not None
        assert job.claim_token is None


def test_worker_persists_the_embedding(session_factory) -> None:
    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)

    _worker(session_factory).run_once()

    with session_factory() as session:
        embedding = session.execute(select(NodeEmbedding)).scalar_one()
        assert embedding.node_id == node_id
        assert embedding.status == "READY"
        assert embedding.dimension == DIM


def test_worker_emits_only_final_review_ready(session_factory) -> None:
    """ANALYSIS_QUEUED belongs to the enqueue transaction, not the worker.

    Emitting it again here would give the same logical event a second eventId,
    which consumer-side deduplication cannot collapse.
    """

    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)

    _worker(session_factory).run_once()

    with session_factory() as session:
        types = [
            row.event_type
            for row in session.execute(select(OutboxEvent)).scalars().all()
        ]
    assert types == ["FINAL_REVIEW_READY"]


def test_a_retryable_embedding_failure_requeues_the_job(session_factory) -> None:
    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)
    embedding = _Embedding(fail=EmbeddingGenerationError("provider down"))

    result = _worker(session_factory, embedding=embedding).run_once()

    assert result.failed == 1
    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.status == "PENDING"  # will be retried after backoff
        assert job.attempt_count == 1
        assert job.failure_code


def test_a_non_retryable_failure_fails_the_job_immediately(session_factory) -> None:
    """An ACTIVE node can never be analysed; retrying cannot help."""

    node_id, version = _seed(session_factory, state="ACTIVE")
    _queue(session_factory, node_id, version)

    result = _worker(session_factory).run_once()

    assert result.failed == 1
    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.status == "FAILED"
        assert job.failure_code == "NodeStateError"


def test_a_permanently_failed_job_emits_pipeline_failed(session_factory) -> None:
    node_id, version = _seed(session_factory, state="ACTIVE")
    _queue(session_factory, node_id, version)

    _worker(session_factory).run_once()

    with session_factory() as session:
        types = [
            row.event_type
            for row in session.execute(select(OutboxEvent)).scalars().all()
        ]
    assert "PIPELINE_FAILED" in types


def test_the_same_node_is_never_analysed_twice_concurrently(session_factory) -> None:
    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)
    embedding = _Embedding()
    worker = _worker(session_factory, embedding=embedding)

    first = worker.run_once()
    second = worker.run_once()

    assert first.succeeded == 1
    assert second.claimed == 0  # nothing left to claim
    assert embedding.calls == 1


def test_a_job_left_running_by_a_dead_worker_is_recovered(session_factory) -> None:
    """Process restart must not strand the job."""

    from datetime import timedelta

    from data_pipeline.jobs.claiming import utcnow

    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)

    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        job.status = "RUNNING"
        job.claim_token = uuid.uuid4()
        job.claimed_at = utcnow() - timedelta(seconds=7200)  # older than the timeout
        session.commit()

    result = _worker(session_factory).run_once()

    assert result.claimed == 1
    assert result.succeeded == 1


def test_a_freshly_running_job_is_not_stolen(session_factory) -> None:
    from data_pipeline.jobs.claiming import utcnow

    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)
    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        job.status = "RUNNING"
        job.claim_token = uuid.uuid4()
        job.claimed_at = utcnow()
        session.commit()

    assert _worker(session_factory).run_once().claimed == 0


def test_worker_reports_skipped_when_completion_claim_was_lost(
    session_factory,
    monkeypatch,
) -> None:
    """A late worker must not report success after another worker took over."""

    import data_pipeline.analysis_worker.runner as runner

    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)
    monkeypatch.setattr(runner, "complete_analysis_job", lambda *args, **kwargs: False)

    result = _worker(session_factory).run_once()

    assert result.claimed == 1
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.skipped == 1
    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.status == "RUNNING"
        assert session.execute(select(OutboxEvent)).scalars().all() == []


def test_worker_reports_skipped_when_failure_claim_was_lost(
    session_factory,
    monkeypatch,
) -> None:
    import data_pipeline.analysis_worker.runner as runner

    node_id, version = _seed(session_factory)
    _queue(session_factory, node_id, version)
    embedding = _Embedding(fail=EmbeddingGenerationError("provider down"))
    monkeypatch.setattr(
        runner,
        "fail_analysis_job",
        lambda *args, **kwargs: "UNOWNED",
    )

    result = _worker(session_factory, embedding=embedding).run_once()

    assert result.claimed == 1
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.skipped == 1


def test_worker_never_reads_a_node_through_another_project(
    session_factory,
) -> None:
    node_id, version = _seed(session_factory)
    with session_factory() as session:
        with pytest.raises(ValueError, match="requested project"):
            enqueue_analysis_job(
                session,
                project_id="another-project",
                external_meeting_id=MEETING,
                node_id=node_id,
                node_version=version,
            )

    with session_factory() as session:
        assert session.execute(select(AnalysisJob)).scalars().all() == []
        assert session.execute(select(NodeEmbedding)).scalars().all() == []
