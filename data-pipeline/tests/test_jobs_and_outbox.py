"""Analysis job queue and transactional outbox."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from data_pipeline.jobs import (
    DEAD,
    PUBLISHED,
    FakeOutboxTransport,
    backoff_delay,
    claim_next_analysis_job,
    complete_analysis_job,
    emit_outbox_event,
    enqueue_analysis_job,
    fail_analysis_job,
    publish_pending_events,
)
from data_pipeline.jobs.outbox import (
    ANALYSIS_QUEUED,
    FINAL_REVIEW_READY,
    INITIAL_REVIEW_READY,
    PENDING,
    PUBLISHING,
    SCHEMA_VERSION,
)
from data_pipeline.jobs.claiming import utcnow
from data_pipeline.storage import AnalysisJob, OutboxEvent


def _node(session_factory, *, project="proj-1", meeting="meet-1", title="n"):
    from data_pipeline.pipeline import seed_node

    with session_factory() as session:
        node = seed_node(
            session,
            project_id=project,
            source_meeting_id=meeting,
            source_item_id=f"item-{uuid.uuid4().hex[:8]}",
            node_type="DECISION",
            category="INFRA",
            title=title,
            content="c",
            graph_state="UNATTACHED",
            evidence=[{"segmentId": "s1", "quote": "q"}],
        )
        session.commit()
        return node.id, node.version


# ------------------------------------------------------------ analysis job ---


def test_enqueue_creates_one_pending_job(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()

    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.status == "PENDING"
        assert job.attempt_count == 0
        assert job.node_id == node_id


def test_enqueue_is_idempotent_for_the_same_node(session_factory) -> None:
    """Re-enqueueing must never create a second job for one Node."""

    node_id, version = _node(session_factory)
    for _ in range(3):
        with session_factory() as session:
            enqueue_analysis_job(
                session,
                project_id="proj-1",
                external_meeting_id="meet-1",
                node_id=node_id,
                node_version=version,
            )
            session.commit()

    with session_factory() as session:
        assert len(session.execute(select(AnalysisJob)).scalars().all()) == 1


def test_claim_marks_running_and_increments_attempt(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()

    claimed = claim_next_analysis_job(session_factory)
    assert claimed is not None
    assert claimed.attempt == 1
    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.status == "RUNNING"
        assert job.claim_token == claimed.claim_token


def test_claim_returns_none_when_queue_is_empty(session_factory) -> None:
    assert claim_next_analysis_job(session_factory) is None


def test_a_running_job_is_not_claimed_twice(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()

    first = claim_next_analysis_job(session_factory)
    second = claim_next_analysis_job(session_factory)
    assert first is not None
    assert second is None


def test_complete_marks_succeeded_and_clears_the_claim(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    assert complete_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=claimed.claim_token,
        analysis_run_id=None,
    ) is True

    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.status == "SUCCEEDED"
        assert job.claim_token is None


def test_a_stale_claim_token_cannot_complete_a_job(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    assert complete_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=uuid.uuid4(),
        analysis_run_id=None,
    ) is False


def test_retryable_failure_returns_to_pending_with_backoff(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    status = fail_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=claimed.claim_token,
        failure_code="EmbeddingTransportError",
        error="boom",
        retryable=True,
    )

    assert status == "PENDING"
    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        assert job.attempt_count == 1
        assert job.failure_code == "EmbeddingTransportError"
        # Not immediately claimable again.
        assert claim_next_analysis_job(session_factory) is None


def test_non_retryable_failure_goes_straight_to_failed(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    status = fail_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=claimed.claim_token,
        failure_code="NodeStateError",
        error="wrong state",
        retryable=False,
    )
    assert status == "FAILED"


def test_failure_stops_retrying_at_max_attempts(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        job = enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        job.max_attempts = 1
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    status = fail_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=claimed.claim_token,
        failure_code="EmbeddingTransportError",
        error="boom",
        retryable=True,
    )
    assert status == "FAILED"


def test_backoff_grows_and_is_capped() -> None:
    assert backoff_delay(0).total_seconds() == 0
    assert backoff_delay(1) < backoff_delay(2) < backoff_delay(3)
    assert backoff_delay(50).total_seconds() <= 3600


# ------------------------------------------------------------------ outbox ---


def _emit(session_factory, event_type=INITIAL_REVIEW_READY, aggregate_id="meet-1"):
    with session_factory() as session:
        emit_outbox_event(
            session,
            event_type=event_type,
            aggregate_type="meeting",
            aggregate_id=aggregate_id,
            project_id="proj-1",
            payload={"meetingId": "meet-1"},
        )
        session.commit()


def test_emit_rejects_an_unknown_event_type(session_factory) -> None:
    with session_factory() as session:
        with pytest.raises(ValueError):
            emit_outbox_event(
                session,
                event_type="NOT_A_REAL_EVENT",
                aggregate_type="meeting",
                aggregate_id="m",
                project_id="p",
                payload={},
            )


def test_outbox_event_rolls_back_with_the_domain_change(session_factory) -> None:
    """The whole point of the outbox: no event without the state change."""

    node_id, version = _node(session_factory)
    session = session_factory()
    try:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        emit_outbox_event(
            session,
            event_type=ANALYSIS_QUEUED,
            aggregate_type="node",
            aggregate_id=str(node_id),
            project_id="proj-1",
            payload={"nodeId": str(node_id)},
        )
        session.rollback()
    finally:
        session.close()

    with session_factory() as session:
        assert session.execute(select(AnalysisJob)).scalars().all() == []
        assert session.execute(select(OutboxEvent)).scalars().all() == []


def test_outbox_event_commits_with_the_domain_change(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        emit_outbox_event(
            session,
            event_type=ANALYSIS_QUEUED,
            aggregate_type="node",
            aggregate_id=str(node_id),
            project_id="proj-1",
            payload={"nodeId": str(node_id)},
        )
        session.commit()

    with session_factory() as session:
        assert len(session.execute(select(AnalysisJob)).scalars().all()) == 1
        event = session.execute(select(OutboxEvent)).scalar_one()
        assert event.event_type == ANALYSIS_QUEUED
        assert event.status == PENDING


def test_publisher_delivers_and_marks_published(session_factory) -> None:
    _emit(session_factory)
    transport = FakeOutboxTransport()

    result = publish_pending_events(session_factory, transport)

    assert result.claimed == 1
    assert result.published == 1
    assert len(transport.published) == 1
    message = transport.published[0]
    assert message.event_type == INITIAL_REVIEW_READY
    assert message.event_id  # eventId is what consumers deduplicate on
    with session_factory() as session:
        row = session.execute(select(OutboxEvent)).scalar_one()
        assert row.status == PUBLISHED
        assert row.published_at is not None
        assert row.attempt_count == 1


def test_publisher_is_a_no_op_when_nothing_is_pending(session_factory) -> None:
    result = publish_pending_events(session_factory, FakeOutboxTransport())
    assert result.claimed == 0
    assert result.published == 0


def test_publisher_records_failure_and_backs_off(session_factory) -> None:
    _emit(session_factory)
    transport = FakeOutboxTransport(fail_times=1)

    first = publish_pending_events(session_factory, transport)

    assert first.published == 0
    assert first.failed == 1
    with session_factory() as session:
        row = session.execute(select(OutboxEvent)).scalar_one()
        assert row.status == PENDING
        assert row.attempt_count == 1
        assert "simulated transport failure" in row.last_error
        # Backoff pushed it into the future, so an immediate retry finds nothing.
        assert publish_pending_events(session_factory, transport).claimed == 0


def test_poison_event_is_parked_as_dead(session_factory) -> None:
    """One permanently bad row must not stall the relay forever."""

    with session_factory() as session:
        event = emit_outbox_event(
            session,
            event_type=INITIAL_REVIEW_READY,
            aggregate_type="meeting",
            aggregate_id="meet-1",
            project_id="proj-1",
            payload={},
        )
        event.max_attempts = 1
        session.commit()

    result = publish_pending_events(
        session_factory, FakeOutboxTransport(fail_forever=True)
    )

    assert result.dead == 1
    with session_factory() as session:
        assert session.execute(select(OutboxEvent)).scalar_one().status == DEAD


def test_publisher_publishes_a_batch(session_factory) -> None:
    for index in range(5):
        _emit(session_factory, aggregate_id=f"meet-{index}")
    transport = FakeOutboxTransport()

    result = publish_pending_events(session_factory, transport, batch_size=3)

    assert result.claimed == 3
    assert result.published == 3
    assert publish_pending_events(session_factory, transport).published == 2


def test_publisher_can_isolate_result_event_v3_rows(session_factory) -> None:
    _emit(session_factory, aggregate_id="legacy")
    with session_factory() as session:
        row = OutboxEvent(
            event_type="PROJECT_GRAPH_CHANGED",
            aggregate_type="project",
            aggregate_id="15",
            project_id="15",
            schema_version="3",
            payload={
                "meetingId": 35,
                "commandId": str(uuid.uuid4()),
                "payload": {"graphVersion": 1, "snapshotArtifactId": str(uuid.uuid4())},
            },
            status=PENDING,
            attempt_count=0,
            available_at=utcnow(),
            created_at=utcnow(),
        )
        session.add(row)
        session.commit()

    transport = FakeOutboxTransport()
    result = publish_pending_events(
        session_factory,
        transport,
        schema_versions=("3",),
    )

    assert result.claimed == 1
    assert transport.published[0].schema_version == "3"
    with session_factory() as session:
        statuses = {
            row.schema_version: row.status
            for row in session.execute(select(OutboxEvent)).scalars()
        }
    assert statuses["3"] == PUBLISHED
    assert statuses[SCHEMA_VERSION] == PENDING


def test_a_claimed_event_is_not_re_claimed_before_the_stall_timeout(
    session_factory,
) -> None:
    _emit(session_factory)
    session = session_factory()
    try:
        from data_pipeline.jobs.claiming import utcnow
        from datetime import timedelta

        row = session.execute(select(OutboxEvent)).scalar_one()
        row.status = PUBLISHING
        row.claim_token = uuid.uuid4()
        row.claimed_at = utcnow()
        row.available_at = utcnow() + timedelta(seconds=300)
        session.commit()
    finally:
        session.close()

    assert publish_pending_events(session_factory, FakeOutboxTransport()).claimed == 0


def test_a_stalled_publishing_row_is_reclaimed(session_factory) -> None:
    """A relay that died mid-delivery must not strand the event."""

    _emit(session_factory)
    session = session_factory()
    try:
        from data_pipeline.jobs.claiming import utcnow
        from datetime import timedelta

        row = session.execute(select(OutboxEvent)).scalar_one()
        row.status = PUBLISHING
        row.claim_token = uuid.uuid4()
        row.claimed_at = utcnow() - timedelta(seconds=301)
        row.available_at = utcnow() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    result = publish_pending_events(session_factory, FakeOutboxTransport())
    assert result.claimed == 1
    assert result.published == 1


def test_event_envelope_carries_the_documented_fields(session_factory) -> None:
    _emit(session_factory, event_type=FINAL_REVIEW_READY)
    transport = FakeOutboxTransport()
    publish_pending_events(session_factory, transport)

    envelope = transport.published[0].as_dict()
    assert set(envelope) == {
        "eventId",
        "eventType",
        "aggregateType",
        "aggregateId",
        "projectId",
        "schemaVersion",
        "occurredAt",
        "payload",
    }
    assert envelope["eventType"] == FINAL_REVIEW_READY


# ------------------------------------------------- code-review regressions ---


def test_claiming_a_job_moves_it_out_of_the_claimable_window(session_factory) -> None:
    """RUNNING rows must not starve the queue.

    Before this fix a claimed row kept its original available_at, so in-flight
    rows sorted ahead of new work and filled the claim limit.
    """

    ids = []
    for index in range(12):
        node_id, version = _node(session_factory, title=f"n{index}")
        with session_factory() as session:
            enqueue_analysis_job(
                session,
                project_id="proj-1",
                external_meeting_id="meet-1",
                node_id=node_id,
                node_version=version,
            )
            session.commit()
        ids.append(node_id)

    claimed = []
    for _ in range(12):
        job = claim_next_analysis_job(session_factory)
        if job is None:
            break
        claimed.append(job)

    assert len(claimed) == 12, f"starved after {len(claimed)} claims"
    assert len({job.node_id for job in claimed}) == 12


def test_completion_and_its_event_share_one_transaction(session_factory) -> None:
    """A failing event write must roll the job completion back with it."""

    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    def _boom(session):
        raise RuntimeError("event write failed")

    with pytest.raises(RuntimeError):
        complete_analysis_job(
            session_factory,
            job_id=claimed.job_id,
            claim_token=claimed.claim_token,
            analysis_run_id=None,
            on_session=_boom,
        )

    with session_factory() as session:
        job = session.execute(select(AnalysisJob)).scalar_one()
        # Still RUNNING and still owned, so the job remains recoverable.
        assert job.status == "RUNNING"
        assert job.claim_token == claimed.claim_token
        assert session.execute(select(OutboxEvent)).scalars().all() == []


def test_completion_commits_its_event_together(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    complete_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=claimed.claim_token,
        analysis_run_id=None,
        on_session=lambda session: emit_outbox_event(
            session,
            event_type=FINAL_REVIEW_READY,
            aggregate_type="node",
            aggregate_id=str(node_id),
            project_id="proj-1",
            payload={"nodeId": str(node_id)},
        ),
    )

    with session_factory() as session:
        assert session.execute(select(AnalysisJob)).scalar_one().status == "SUCCEEDED"
        assert (
            session.execute(select(OutboxEvent)).scalar_one().event_type
            == FINAL_REVIEW_READY
        )


def test_terminal_failure_event_commits_with_the_failed_status(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        job = enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        job.max_attempts = 1
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    staged = []
    status = fail_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=claimed.claim_token,
        failure_code="Boom",
        error="boom",
        retryable=True,
        on_terminal_failure=lambda session: staged.append(
            emit_outbox_event(
                session,
                event_type="PIPELINE_FAILED",
                aggregate_type="node",
                aggregate_id=str(node_id),
                project_id="proj-1",
                payload={"nodeId": str(node_id)},
            )
        ),
    )

    assert status == "FAILED"
    assert len(staged) == 1
    with session_factory() as session:
        assert (
            session.execute(select(OutboxEvent)).scalar_one().event_type
            == "PIPELINE_FAILED"
        )


def test_a_retryable_failure_emits_no_terminal_event(session_factory) -> None:
    node_id, version = _node(session_factory)
    with session_factory() as session:
        enqueue_analysis_job(
            session,
            project_id="proj-1",
            external_meeting_id="meet-1",
            node_id=node_id,
            node_version=version,
        )
        session.commit()
    claimed = claim_next_analysis_job(session_factory)

    called = []
    status = fail_analysis_job(
        session_factory,
        job_id=claimed.job_id,
        claim_token=claimed.claim_token,
        failure_code="Boom",
        error="boom",
        retryable=True,
        on_terminal_failure=lambda session: called.append(1),
    )

    assert status == "PENDING"
    assert called == []


def test_a_reclaimed_event_cannot_be_resurrected_by_the_old_worker(
    session_factory,
) -> None:
    """A slow worker must not flip an already-PUBLISHED row back to PENDING."""

    from data_pipeline.jobs.outbox import _record_failure, _record_success

    _emit(session_factory)
    with session_factory() as session:
        event_id = session.execute(select(OutboxEvent)).scalar_one().id

    # Worker B finished the row while worker A was still in flight.
    with session_factory() as session:
        row = session.get(OutboxEvent, event_id)
        row.status = PUBLISHED
        session.commit()

    _record_failure(
        session_factory,
        event_id,
        uuid.uuid4(),
        RuntimeError("late failure"),
    )

    with session_factory() as session:
        row = session.get(OutboxEvent, event_id)
        assert row.status == PUBLISHED  # not resurrected
        assert row.attempt_count == 0   # budget not double-burned


def test_a_late_success_write_is_also_ignored(session_factory) -> None:
    from data_pipeline.jobs.outbox import _record_success

    _emit(session_factory)
    with session_factory() as session:
        event_id = session.execute(select(OutboxEvent)).scalar_one().id
        row = session.get(OutboxEvent, event_id)
        row.status = DEAD
        session.commit()

    _record_success(session_factory, event_id, uuid.uuid4())

    with session_factory() as session:
        assert session.get(OutboxEvent, event_id).status == DEAD


def test_reclaimed_publishing_event_rejects_the_old_claim_owner(
    session_factory,
) -> None:
    """Status=PUBLISHING alone is not ownership after a lease is reclaimed."""

    from data_pipeline.jobs.outbox import _record_failure, _record_success
    from data_pipeline.jobs.claiming import utcnow

    _emit(session_factory)
    old_token = uuid.uuid4()
    new_token = uuid.uuid4()
    with session_factory() as session:
        row = session.execute(select(OutboxEvent)).scalar_one()
        event_id = row.id
        row.status = PUBLISHING
        row.claim_token = new_token
        row.claimed_at = utcnow()
        session.commit()

    assert _record_success(session_factory, event_id, old_token) is False
    assert (
        _record_failure(
            session_factory,
            event_id,
            old_token,
            RuntimeError("old worker failed late"),
        )
        is None
    )

    with session_factory() as session:
        row = session.get(OutboxEvent, event_id)
        assert row.status == PUBLISHING
        assert row.claim_token == new_token
        assert row.attempt_count == 0

    assert _record_success(session_factory, event_id, new_token) is True
    with session_factory() as session:
        row = session.get(OutboxEvent, event_id)
        assert row.status == PUBLISHED
        assert row.claim_token is None
        assert row.attempt_count == 1


def test_postgresql_reclaimed_outbox_claim_wins_over_slow_worker(
    session_factory,
) -> None:
    """Exercise two real publisher transactions against PostgreSQL."""

    import threading
    from datetime import timedelta

    from data_pipeline.jobs.claiming import utcnow

    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL row locking")

    class BlockingTransport:
        def __init__(self):
            self.entered = threading.Event()
            self.release = threading.Event()
            self.published = []

        def publish(self, message):
            self.published.append(message)
            self.entered.set()
            if not self.release.wait(timeout=10):
                raise TimeoutError("test did not release the slow transport")

    _emit(session_factory)
    slow_transport = BlockingTransport()
    slow_result = {}
    slow_error = {}

    def publish_slowly():
        try:
            slow_result["value"] = publish_pending_events(
                session_factory,
                slow_transport,
                stall_timeout_seconds=300,
            )
        except Exception as exc:  # surfaced in the parent test thread
            slow_error["value"] = exc

    thread = threading.Thread(target=publish_slowly, daemon=True)
    thread.start()
    assert slow_transport.entered.wait(timeout=10)

    # Simulate the first worker exceeding its lease while its transport call is
    # still in flight. Worker B must replace the claim token before publishing.
    with session_factory() as session:
        row = session.execute(select(OutboxEvent)).scalar_one()
        first_token = row.claim_token
        row.available_at = utcnow() - timedelta(seconds=1)
        session.commit()

    fast_transport = FakeOutboxTransport()
    fast_result = publish_pending_events(session_factory, fast_transport)
    assert fast_result.published == 1

    slow_transport.release.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert slow_error == {}
    assert slow_result["value"].published == 0

    with session_factory() as session:
        row = session.execute(select(OutboxEvent)).scalar_one()
        assert row.status == PUBLISHED
        assert row.claim_token is None
        assert row.attempt_count == 1
        assert row.claimed_at is not None
        assert first_token is not None
