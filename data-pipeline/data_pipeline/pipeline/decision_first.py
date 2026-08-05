"""Decision-first scheduling for one meeting.

Initial review creates every Node immediately, but analysis is released in two
phases: DECISION first, then ACTION/ISSUE after every Decision has received a
user final decision. The caller owns the transaction; no worker or provider is
invoked here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select

from data_pipeline.jobs import (
    ANALYSIS_QUEUED,
    emit_outbox_event,
    enqueue_analysis_job,
)
from data_pipeline.storage import AnalysisJob, Meeting, Node

from .errors import DependentAnalysisBlockedError, NodeStateError
from .parent_hint import _canonical


@dataclass(frozen=True)
class DecisionFirstReleaseResult:
    phase: str
    queued_node_ids: tuple[uuid.UUID, ...]

    @property
    def queued_count(self) -> int:
        return len(self.queued_node_ids)


def _lock_meeting(
    session,
    *,
    project_id: str,
    meeting_id: str,
) -> Meeting | None:
    """Serialize every Decision-first phase transition for one meeting."""

    return session.execute(
        select(Meeting)
        .where(
            Meeting.project_id == project_id,
            Meeting.external_meeting_id == meeting_id,
        )
        .with_for_update()
    ).scalar_one_or_none()


def _decision_is_final(session, node: Node, *, project_id: str) -> bool:
    if node.graph_state == "ACTIVE" and node.merged_into_node_id is None:
        return True
    if node.graph_state != "MERGED" or node.merged_into_node_id is None:
        return False
    canonical = _canonical(session, node, project_id=project_id)
    return (
        canonical is not None
        and canonical.node_type == "DECISION"
        and canonical.graph_state == "ACTIVE"
        and canonical.merged_into_node_id is None
    )


def _meeting_decisions(
    session,
    *,
    project_id: str,
    meeting_id: str,
) -> list[Node]:
    return session.execute(
        select(Node).where(
            Node.project_id == project_id,
            Node.source_meeting_id == meeting_id,
            Node.source_candidate_id.is_not(None),
            Node.node_type == "DECISION",
        )
    ).scalars().all()


def assert_node_analysis_phase_allowed(session, node: Node) -> None:
    """Lock the meeting and reject dependent analysis before any side effect."""

    meeting = _lock_meeting(
        session,
        project_id=node.project_id,
        meeting_id=node.source_meeting_id,
    )
    if meeting is None:
        raise NodeStateError(
            "the Node's source meeting is not available for analysis"
        )
    if node.node_type == "DECISION":
        return
    if node.node_type not in {"ACTION", "ISSUE"}:
        raise NodeStateError(f"unsupported analysis Node type: {node.node_type}")

    decisions = _meeting_decisions(
        session,
        project_id=node.project_id,
        meeting_id=node.source_meeting_id,
    )
    if any(
        not _decision_is_final(session, decision, project_id=node.project_id)
        for decision in decisions
    ):
        raise DependentAnalysisBlockedError(
            "Action/Issue analysis is blocked until every Decision in the "
            "meeting is finally ACTIVE or MERGED"
        )


def release_pending_dependent_nodes_if_ready(
    session,
    *,
    project_id: str,
    meeting_id: str,
) -> DecisionFirstReleaseResult:
    """Queue the currently eligible analysis phase, idempotently.

    The meeting row is the serialization boundary for concurrent Decision
    approvals. ``AnalysisJob.node_id`` remains the database-level last line of
    defence, while the job-existence filter ensures an outbox event is emitted
    only when its logical job is first created.
    """

    # Production meetings always have this row. Keeping the helper tolerant of
    # older/directly-seeded test data avoids turning an absent orchestration row
    # into an unrelated graph-decision failure.
    _lock_meeting(
        session,
        project_id=project_id,
        meeting_id=meeting_id,
    )

    reviewed_nodes = session.execute(
        select(Node)
        .where(
            Node.project_id == project_id,
            Node.source_meeting_id == meeting_id,
            Node.source_candidate_id.is_not(None),
            Node.node_type.in_(("DECISION", "ACTION", "ISSUE")),
        )
        .order_by(Node.created_at, Node.id)
    ).scalars().all()

    decisions = [node for node in reviewed_nodes if node.node_type == "DECISION"]
    waiting_decisions = [
        node
        for node in decisions
        if not _decision_is_final(session, node, project_id=project_id)
    ]
    if waiting_decisions:
        eligible_types = {"DECISION"}
        phase = "DECISION"
    else:
        eligible_types = {"ACTION", "ISSUE"}
        phase = "DEPENDENT"

    existing_job_node_ids = set(
        session.execute(
            select(AnalysisJob.node_id).where(
                AnalysisJob.project_id == project_id,
                AnalysisJob.external_meeting_id == meeting_id,
            )
        ).scalars()
    )
    eligible = [
        node
        for node in reviewed_nodes
        if node.node_type in eligible_types
        and node.graph_state == "UNATTACHED"
        and node.merged_into_node_id is None
        and node.id not in existing_job_node_ids
    ]

    queued_ids: list[uuid.UUID] = []
    for node in eligible:
        enqueue_analysis_job(
            session,
            project_id=project_id,
            external_meeting_id=meeting_id,
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
                "meetingId": meeting_id,
                "nodeId": str(node.id),
                "analysisPhase": phase,
            },
        )
        queued_ids.append(node.id)

    return DecisionFirstReleaseResult(
        phase=phase,
        queued_node_ids=tuple(queued_ids),
    )


__all__ = [
    "DecisionFirstReleaseResult",
    "assert_node_analysis_phase_allowed",
    "release_pending_dependent_nodes_if_ready",
]
