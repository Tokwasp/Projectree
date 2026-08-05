from __future__ import annotations

import uuid

import pytest

from data_pipeline.pipeline import (
    AnalysisRunNotFoundError,
    CandidateNotFoundError,
    NodeNotFoundError,
    complete_initial_review,
    edit_candidate,
    edit_unattached_node,
    get_candidate,
    mark_analysis_run_completed,
    mark_analysis_run_failed,
    mark_analysis_run_running,
    reanalyze_unattached_node,
    reject_candidate,
)
from data_pipeline.storage import (
    CandidateReviewEvent,
    GraphChangeEvent,
    Node,
    NodeAnalysisRun,
    NodeCandidate,
)

from .test_candidate_review import _decision, _persist
from .test_unattached_node_edit import _initial_node


def test_candidate_uuid_cannot_cross_project_boundary(session_factory):
    candidate = _persist(
        session_factory,
        meeting_id="M-PROJECT-CANDIDATE",
        rows=[_decision()],
        project_id="project-a",
    )[0]

    with pytest.raises(CandidateNotFoundError):
        get_candidate(
            session_factory,
            candidate.candidate_id,
            project_id="project-b",
        )
    with pytest.raises(CandidateNotFoundError):
        edit_candidate(
            session_factory,
            candidate.candidate_id,
            project_id="project-b",
            actor_id="intruder",
            expected_version=1,
            title="cross-project edit",
        )
    with pytest.raises(CandidateNotFoundError):
        reject_candidate(
            session_factory,
            candidate.candidate_id,
            project_id="project-b",
            actor_id="intruder",
            expected_version=1,
        )
    with pytest.raises(CandidateNotFoundError):
        complete_initial_review(
            session_factory,
            candidate.candidate_id,
            project_id="project-b",
            actor_id="intruder",
            expected_version=1,
        )

    with session_factory() as session:
        stored = session.get(
            NodeCandidate,
            uuid.UUID(candidate.candidate_id),
        )
        assert stored.review_status == "PENDING"
        assert stored.version == 1
        assert session.query(Node).count() == 0
        assert session.query(CandidateReviewEvent).count() == 0
        assert session.query(GraphChangeEvent).count() == 0


def test_node_and_analysis_uuid_cannot_cross_project_boundary(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-PROJECT-NODE",
    )

    with pytest.raises(NodeNotFoundError):
        edit_unattached_node(
            session_factory,
            node_id,
            project_id="project-b",
            actor_id="intruder",
            expected_version=1,
            title="cross-project edit",
        )
    with pytest.raises(NodeNotFoundError):
        reanalyze_unattached_node(
            session_factory,
            node_id,
            project_id="project-b",
            actor_id="intruder",
            expected_version=1,
        )

    requested = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
    )
    run_id = requested.run.analysis_run_id

    with pytest.raises(AnalysisRunNotFoundError):
        mark_analysis_run_running(
            session_factory,
            run_id,
            project_id="project-b",
        )
    with pytest.raises(AnalysisRunNotFoundError):
        mark_analysis_run_completed(
            session_factory,
            run_id,
            project_id="project-b",
        )
    with pytest.raises(AnalysisRunNotFoundError):
        mark_analysis_run_failed(
            session_factory,
            run_id,
            project_id="project-b",
            failure_code="INTRUDER",
            failure_message="must not be stored",
        )

    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        run = session.get(NodeAnalysisRun, uuid.UUID(run_id))
        assert node.version == 1
        assert node.analysis_status == "PENDING"
        assert run.status == "PENDING"
        assert run.failure_code is None
        assert session.query(GraphChangeEvent).count() == 1
