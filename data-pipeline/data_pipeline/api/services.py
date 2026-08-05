"""Orchestration that sits between routers and the pipeline services.

Kept out of the routers so HTTP concerns stay thin and this logic is testable
without a client.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select

from data_pipeline.api.schemas import (
    AnalysisCandidateView,
    AnalysisJobView,
    AnalysisStatusResponse,
    FinalReviewResponse,
    InitialReviewCompleteResponse,
    PipelineStatusResponse,
)
from data_pipeline.contracts import (
    AnalysisRunStatus,
    ReanalyzeUnattachedNodeResult,
)
from data_pipeline.jobs import (
    ANALYSIS_QUEUED,
    INITIAL_REVIEW_READY,
    MANUAL_DECISION_COMPLETED,
    emit_outbox_event,
    enqueue_analysis_job,
)
from data_pipeline.pipeline import (
    complete_initial_review,
    list_candidates,
    release_pending_dependent_nodes_if_ready,
)
from data_pipeline.pipeline.analysis import (
    reanalyze_unattached_node_in_session,
)
from data_pipeline.pipeline.decision_first import (
    assert_node_analysis_phase_allowed,
)
from data_pipeline.pipeline.errors import NodeNotFoundError
from data_pipeline.storage import (
    AnalysisCandidate,
    AnalysisJob,
    Meeting,
    Node,
    NodeCandidate,
    Request,
)


@dataclass(frozen=True)
class QueueAnalysisForNodeResult:
    requested: ReanalyzeUnattachedNodeResult
    queued_count: int


def complete_meeting_initial_review(
    session_factory,
    *,
    project_id: str,
    meeting_id: str,
    actor_id: str,
    candidate_ids: list[str] | None = None,
) -> InitialReviewCompleteResponse:
    """Approve outstanding candidates, then queue analysis for the new Nodes.

    Node creation happens per candidate inside complete_initial_review's own
    transaction. Queueing then runs as one transaction over every UNATTACHED
    Node of the meeting that has no job yet, together with the outbox events.
    That makes the endpoint idempotent and self-healing: a crash between the two
    steps leaves Nodes without jobs, and simply calling it again enqueues them.
    """

    targets = list(candidate_ids or [])
    if not targets:
        targets = [
            view.candidate_id
            for view in list_candidates(
                session_factory,
                project_id=project_id,
                external_meeting_id=meeting_id,
                review_status="PENDING",
            )
        ]

    reviewed = 0
    created_node_ids: list[str] = []
    try:
        for candidate_id in targets:
            result = complete_initial_review(
                session_factory,
                candidate_id,
                project_id=project_id,
                actor_id=actor_id,
            )
            reviewed += 1
            created_node_ids.extend(result.created_node_ids)
    finally:
        # Each approval commits on its own, so a later candidate failing would
        # otherwise strand the Nodes already created with no job and no event.
        # Queueing is idempotent, so running it even on the failure path is safe
        # and leaves the meeting recoverable by simply retrying.
        queued = _queue_analysis_for_meeting(
            session_factory, project_id=project_id, meeting_id=meeting_id
        )

    return InitialReviewCompleteResponse(
        meetingId=meeting_id,
        status="ANALYSIS_PENDING",
        reviewedCandidateCount=reviewed,
        createdNodeCount=len(created_node_ids),
        queuedAnalysisJobCount=queued,
        createdNodeIds=created_node_ids,
    )


def _queue_analysis_for_meeting(
    session_factory, *, project_id: str, meeting_id: str
) -> int:
    """Release the meeting's currently eligible Decision-first phase."""

    session = session_factory()
    try:
        released = release_pending_dependent_nodes_if_ready(
            session,
            project_id=project_id,
            meeting_id=meeting_id,
        )
        if released.queued_count == 0:
            session.rollback()
            return 0

        # One meeting-level event so Spring can move the review screen on.
        emit_outbox_event(
            session,
            event_type=INITIAL_REVIEW_READY,
            aggregate_type="meeting",
            aggregate_id=meeting_id,
            project_id=project_id,
            payload={
                "meetingId": meeting_id,
                "queuedNodeCount": released.queued_count,
                "analysisPhase": released.phase,
            },
        )
        session.commit()
        return released.queued_count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def queue_analysis_for_node(
    session_factory,
    *,
    project_id: str,
    node_id: uuid.UUID,
    actor_id: str,
    expected_version: int,
) -> QueueAnalysisForNodeResult:
    """Guard, request, and enqueue one Node analysis atomically."""

    session = session_factory()
    try:
        # Read only immutable routing fields first. The phase guard acquires the
        # meeting lock before reanalyze_unattached_node_in_session locks the
        # dependent Node, preventing inversion with final approval's
        # meeting-lock-then-dependent-job insertion.
        node = session.execute(
            select(Node).where(Node.id == node_id, Node.project_id == project_id)
        ).scalar_one_or_none()
        if node is None:
            session.rollback()
            raise NodeNotFoundError(f"node not found: {node_id}")

        # The meeting lock and phase decision happen before a Run, Job, Outbox,
        # or Node analysis-status mutation is allowed.
        assert_node_analysis_phase_allowed(session, node)
        requested = reanalyze_unattached_node_in_session(
            session,
            node.id,
            project_id=project_id,
            actor_id=actor_id,
            expected_version=expected_version,
        )

        should_queue = requested.run.status in {
            AnalysisRunStatus.PENDING,
            AnalysisRunStatus.RUNNING,
        }
        existing_job = session.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.node_id == node.id,
                AnalysisJob.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        already_active = (
            existing_job is not None
            and existing_job.node_version == node.version
            and existing_job.status in {"PENDING", "RUNNING"}
        )
        queued_count = 0
        if should_queue and not already_active:
            enqueue_analysis_job(
                session,
                project_id=project_id,
                external_meeting_id=node.source_meeting_id,
                node_id=node.id,
                node_version=node.version,
            )
            emit_outbox_event(
                session,
                event_type=ANALYSIS_QUEUED,
                aggregate_type="node",
                aggregate_id=str(node.id),
                project_id=project_id,
                payload={
                    "meetingId": node.source_meeting_id,
                    "nodeId": str(node.id),
                    "analysisRunId": requested.run.analysis_run_id,
                    "trigger": "REANALYZE",
                },
            )
            queued_count = 1
        session.commit()
        return QueueAnalysisForNodeResult(
            requested=requested,
            queued_count=queued_count,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def build_pipeline_status(
    session_factory, *, project_id: str, meeting_id: str
) -> PipelineStatusResponse:
    with session_factory() as session:
        meeting = session.execute(
            select(Meeting).where(
                Meeting.project_id == project_id,
                Meeting.external_meeting_id == meeting_id,
            )
        ).scalar_one_or_none()
        request = session.execute(
            select(Request)
            .where(
                Request.project_id == project_id,
                Request.external_meeting_id == meeting_id,
            )
            .order_by(Request.created_at.desc())
        ).scalars().first()

        candidate_counts = dict(
            session.execute(
                select(NodeCandidate.review_status, func.count())
                .where(
                    NodeCandidate.project_id == project_id,
                    NodeCandidate.external_meeting_id == meeting_id,
                )
                .group_by(NodeCandidate.review_status)
            ).all()
        )
        node_counts = dict(
            session.execute(
                select(Node.graph_state, func.count())
                .where(
                    Node.project_id == project_id,
                    Node.source_meeting_id == meeting_id,
                )
                .group_by(Node.graph_state)
            ).all()
        )
        job_counts = dict(
            session.execute(
                select(AnalysisJob.status, func.count())
                .where(
                    AnalysisJob.project_id == project_id,
                    AnalysisJob.external_meeting_id == meeting_id,
                )
                .group_by(AnalysisJob.status)
            ).all()
        )
        effective_job_counts = dict(
            session.execute(
                select(AnalysisJob.status, func.count())
                .where(
                    AnalysisJob.project_id == project_id,
                    AnalysisJob.external_meeting_id == meeting_id,
                    or_(
                        AnalysisJob.status != "FAILED",
                        AnalysisJob.failure_code.is_(None),
                        AnalysisJob.failure_code
                        != MANUAL_DECISION_COMPLETED,
                    ),
                )
                .group_by(AnalysisJob.status)
            ).all()
        )

    return PipelineStatusResponse(
        meetingId=meeting_id,
        projectId=project_id,
        meetingStatus=meeting.status if meeting else None,
        requestStatus=request.status if request else None,
        candidateCounts={str(k): int(v) for k, v in candidate_counts.items()},
        nodeCounts={str(k): int(v) for k, v in node_counts.items()},
        analysisJobCounts={str(k): int(v) for k, v in job_counts.items()},
        pipelineStage=_stage(candidate_counts, effective_job_counts),
    )


def _stage(candidate_counts: dict, job_counts: dict) -> str:
    if candidate_counts.get("PENDING"):
        return "INITIAL_REVIEW_PENDING"
    if job_counts.get("PENDING") or job_counts.get("RUNNING"):
        return "ANALYZING"
    if job_counts.get("FAILED"):
        return "FAILED"
    if job_counts.get("SUCCEEDED"):
        return "FINAL_REVIEW_PENDING"
    if candidate_counts:
        return "REVIEW_COMPLETED"
    return "UNKNOWN"


def build_analysis_status(
    session_factory, *, project_id: str, meeting_id: str
) -> AnalysisStatusResponse:
    with session_factory() as session:
        jobs = session.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.project_id == project_id,
                AnalysisJob.external_meeting_id == meeting_id,
            )
            .order_by(AnalysisJob.created_at)
        ).scalars().all()
        views = [
            AnalysisJobView(
                jobId=str(job.id),
                nodeId=str(job.node_id),
                status=job.status,
                attemptCount=job.attempt_count,
                maxAttempts=job.max_attempts,
                failureCode=job.failure_code,
                availableAt=job.available_at,
                updatedAt=job.updated_at,
            )
            for job in jobs
        ]

    effective_statuses = {
        job.status
        for job in jobs
        if not (
            job.status == "FAILED"
            and job.failure_code == MANUAL_DECISION_COMPLETED
        )
    }
    if not views:
        overall = "NOT_QUEUED"
    elif not effective_statuses:
        overall = "REVIEW_COMPLETED"
    elif effective_statuses & {"PENDING", "RUNNING"}:
        overall = "ANALYZING"
    elif effective_statuses == {"SUCCEEDED"}:
        overall = "FINAL_REVIEW_PENDING"
    elif "FAILED" in effective_statuses:
        overall = "FAILED"
    else:
        overall = "ANALYZING"

    return AnalysisStatusResponse(
        meetingId=meeting_id, status=overall, jobs=views
    )


def build_final_review(
    session_factory, *, project_id: str, meeting_id: str, status_filter: str = "PENDING"
) -> FinalReviewResponse:
    """List analysis candidates awaiting final approval for one meeting.

    There is no service function for this, so the query lives here rather than
    in a router.
    """

    with session_factory() as session:
        rows = session.execute(
            select(AnalysisCandidate)
            .join(Node, Node.id == AnalysisCandidate.source_node_id)
            .where(
                AnalysisCandidate.project_id == project_id,
                AnalysisCandidate.status == status_filter,
                Node.source_meeting_id == meeting_id,
                # Only the candidate of the node's CURRENT analysis run is
                # actionable. After a reanalysis the superseded run's candidate
                # stays PENDING in the DB (auditable, rejectable) but showing it
                # here sent reviewers into guaranteed 409s — live-E2E finding.
                AnalysisCandidate.analysis_run_id == Node.current_analysis_run_id,
            )
            .order_by(AnalysisCandidate.created_at)
        ).scalars().all()
        views = [
            AnalysisCandidateView(
                analysisCandidateId=str(row.id),
                projectId=row.project_id,
                analysisRunId=str(row.analysis_run_id),
                sourceNodeId=str(row.source_node_id),
                sourceNodeVersion=row.source_node_version,
                targetNodeId=(
                    str(row.target_node_id) if row.target_node_id else None
                ),
                targetNodeVersion=row.target_node_version,
                recommendation=row.recommendation,
                relationType=row.relation_type,
                suggestedTitle=row.suggested_title,
                suggestedContent=row.suggested_content,
                reason=row.reason,
                status=row.status,
                version=row.version,
                createdAt=row.created_at,
            )
            for row in rows
        ]

    return FinalReviewResponse(
        meetingId=meeting_id, total=len(views), analysisCandidates=views
    )


__all__ = [
    "build_analysis_status",
    "build_final_review",
    "build_pipeline_status",
    "complete_meeting_initial_review",
    "queue_analysis_for_node",
]
