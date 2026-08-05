from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event

from data_pipeline.retrieval.embedding import (
    EMBEDDING_CONTRACT_VERSION,
    build_embedding_text_from_parts,
    embedding_text_hash,
)
from data_pipeline.pipeline import (
    AnalysisCandidateNotFoundError,
    AnalysisCandidateStateError,
    AnalysisRunIncompleteError,
    AnalysisRunNotFoundError,
    AnalysisRunStateError,
    BModelResultValidationError,
    BModelExecutionError,
    approve_analysis_candidate,
    approve_create_new,
    approve_link_existing,
    approve_merge_existing,
    edit_unattached_node,
    execute_analysis_retrieval,
    execute_b_model,
    mark_analysis_run_completed,
    reanalyze_unattached_node,
    reject_analysis_candidate,
)
from data_pipeline.storage import (
    AnalysisCandidate,
    BModelResult,
    Node,
    NodeAnalysisRun,
    NodeEmbedding,
    NodeMergeHistory,
    NodeRevision,
    Relation,
)

from .test_analysis_retrieval import (
    FakeEmbeddingClient,
    _requested_run,
    _target,
    _vector,
)
from .test_unattached_node_edit import _initial_node


class FakeBModelClient:
    def __init__(self, result=None, *, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    def recommend(
        self,
        *,
        source_node: dict,
        retrieval_candidates: list[dict],
        model: str,
    ):
        self.calls.append(
            {
                "source_node": source_node,
                "retrieval_candidates": retrieval_candidates,
                "model": model,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


def _decision(kind: str, target_id=None, relation_type=None):
    return {
        "recommendation": kind,
        "targetNodeId": str(target_id) if target_id else None,
        "relationType": relation_type,
        "suggestedTitle": "사용자가 검토할 최종 제목",
        "suggestedContent": "사용자가 검토할 최종 본문",
        "reason": "fake B model recommendation",
        "metadata": {"promptVersion": "test-v1"},
    }


def _run_with_retrieval(
    session_factory,
    *,
    meeting_id: str,
    target_state: str = "ACTIVE",
):
    source_id, run_id = _requested_run(
        session_factory,
        meeting_id=meeting_id,
    )
    with session_factory() as session:
        target = _target(
            session,
            project_id="proj-01",
            source_item_id=f"{meeting_id}-target",
            graph_state=target_state,
            vector=_vector(1.0),
        )
        target_id = target.id
        session.commit()
    execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(),
    )
    return uuid.UUID(source_id), uuid.UUID(run_id), target_id


def _execute_decision(
    session_factory,
    *,
    run_id,
    decision,
    client=None,
):
    client = client or FakeBModelClient(decision)
    result = execute_b_model(
        session_factory,
        run_id,
        project_id="proj-01",
        client=client,
        model="fake-b",
        model_version="fake-b-v1",
    )
    return result, client


def _action_run_with_parent(session_factory, *, meeting_id: str):
    source_id, _, _ = _initial_node(
        session_factory,
        meeting_id=meeting_id,
    )
    with session_factory() as session:
        source = session.get(Node, uuid.UUID(source_id))
        source.node_type = "ACTION"
        parent = _target(
            session,
            project_id="proj-01",
            source_item_id=f"{meeting_id}-parent",
            graph_state="ACTIVE",
            vector=_vector(1.0),
        )
        parent_id = parent.id
        session.commit()
    requested = reanalyze_unattached_node(
        session_factory,
        source_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
        retrieval_config_version="retrieval-test-v1",
    )
    run_id = uuid.UUID(requested.run.analysis_run_id)
    execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(),
    )
    return uuid.UUID(source_id), run_id, parent_id


def test_zero_retrieval_skips_b_without_candidate_and_completes(
    session_factory,
):
    source_id, run_id = _requested_run(
        session_factory,
        meeting_id="M-B-ZERO",
    )
    execute_analysis_retrieval(
        session_factory,
        run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(),
    )
    client = FakeBModelClient(error=AssertionError("must not be called"))

    first = execute_b_model(
        session_factory,
        run_id,
        project_id="proj-01",
        client=client,
        model="fake-b",
        model_version="fake-b-v1",
    )
    replay = execute_b_model(
        session_factory,
        run_id,
        project_id="proj-01",
        client=client,
        model="fake-b",
        model_version="fake-b-v1",
    )

    assert client.calls == []
    assert first.run.status.value == "COMPLETED"
    assert first.run.b_model_status.value == "SKIPPED"
    assert first.run.b_model_skip_reason == "NO_RETRIEVAL_CANDIDATES"
    assert first.candidate is None
    assert replay.candidate is None
    with session_factory() as session:
        assert session.query(BModelResult).count() == 0
        assert session.query(AnalysisCandidate).count() == 0
        assert session.get(Node, uuid.UUID(source_id)).analysis_status == "ANALYZED"


@pytest.mark.parametrize(
    ("kind", "relation_type"),
    [
        ("CREATE_NEW", None),
        ("LINK", "RELATED_TO"),
        ("MERGE", None),
    ],
)
def test_valid_b_result_creates_one_candidate_and_completes(
    session_factory,
    kind,
    relation_type,
):
    _, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id=f"M-B-{kind}",
    )
    target = target_id if kind != "CREATE_NEW" else None
    result, client = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision(kind, target, relation_type),
    )
    replay, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision(kind, target, relation_type),
        client=client,
    )

    assert len(client.calls) == 1
    assert result.run.status.value == "COMPLETED"
    assert result.run.b_model_status.value == "SUCCEEDED"
    assert result.candidate.recommendation.value == kind
    assert replay.candidate.candidate_id == result.candidate.candidate_id
    with session_factory() as session:
        assert session.query(BModelResult).count() == 1
        assert session.query(AnalysisCandidate).count() == 1


@pytest.mark.parametrize(
    "invalid_target",
    ["random", "self", "changed", "other_project"],
)
def test_invalid_b_target_leaves_no_result_candidate_or_fake_completion(
    session_factory,
    invalid_target,
):
    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id=f"M-B-INVALID-{invalid_target}",
    )
    if invalid_target == "random":
        selected = uuid.uuid4()
    elif invalid_target == "self":
        selected = source_id
    else:
        with session_factory() as session:
            if invalid_target == "changed":
                selected = target_id
                target = session.get(Node, target_id)
                target.graph_state = "ARCHIVED"
            else:
                other = _target(
                    session,
                    project_id="other-project",
                    source_item_id="cross-project-b-target",
                    graph_state="ACTIVE",
                    vector=_vector(1.0),
                )
                selected = other.id
            session.commit()

    with pytest.raises(BModelResultValidationError):
        _execute_decision(
            session_factory,
            run_id=run_id,
            decision=_decision("MERGE", selected),
        )

    with session_factory() as session:
        run = session.get(NodeAnalysisRun, run_id)
        source = session.get(Node, source_id)
        assert run.status == "FAILED"
        assert run.b_model_status == "FAILED"
        assert source.analysis_status == "FAILED"
        assert session.query(BModelResult).count() == 0
        assert session.query(AnalysisCandidate).count() == 0


def test_link_target_outside_retrieval_is_rejected(session_factory):
    _, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-B-LINK-OUTSIDE",
    )
    with pytest.raises(BModelResultValidationError):
        _execute_decision(
            session_factory,
            run_id=run_id,
            decision=_decision(
                "LINK",
                uuid.uuid4(),
                "RELATED_TO",
            ),
        )
    with session_factory() as session:
        assert session.query(BModelResult).count() == 0
        assert session.query(AnalysisCandidate).count() == 0


def test_candidate_insert_failure_rolls_back_completed_b_result(
    session_factory,
):
    _, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-B-CANDIDATE-ROLLBACK",
    )

    def fail_candidate_insert(*args, **kwargs):
        raise RuntimeError("fake candidate persistence failure")

    event.listen(AnalysisCandidate, "before_insert", fail_candidate_insert)
    try:
        with pytest.raises(BModelExecutionError):
            _execute_decision(
                session_factory,
                run_id=run_id,
                decision=_decision("CREATE_NEW"),
            )
    finally:
        event.remove(
            AnalysisCandidate,
            "before_insert",
            fail_candidate_insert,
        )

    with session_factory() as session:
        run = session.get(NodeAnalysisRun, run_id)
        assert run.status == "FAILED"
        assert run.b_model_status == "FAILED"
        assert run.failure_code == "B_MODEL_PERSISTENCE_FAILED"
        assert session.query(BModelResult).count() == 0
        assert session.query(AnalysisCandidate).count() == 0


def test_invalid_b_shape_keeps_completion_guard_closed(session_factory):
    _, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-B-SHAPE",
    )
    malformed = _decision("LINK", target_id, None)
    with pytest.raises(BModelResultValidationError):
        _execute_decision(
            session_factory,
            run_id=run_id,
            decision=malformed,
        )
    with pytest.raises(AnalysisRunIncompleteError):
        mark_analysis_run_completed(
            session_factory,
            run_id,
            project_id="proj-01",
        )


def test_late_b_response_cannot_persist_after_source_edit(session_factory):
    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-B-LATE",
    )

    class EditingClient(FakeBModelClient):
        def recommend(self, **kwargs):
            edit_unattached_node(
                session_factory,
                source_id,
                project_id="proj-01",
                actor_id="editor",
                expected_version=1,
                title="B 호출 중 바뀐 제목",
            )
            return _decision("LINK", target_id, "RELATED_TO")

    with pytest.raises(AnalysisRunStateError):
        execute_b_model(
            session_factory,
            run_id,
            project_id="proj-01",
            client=EditingClient(),
            model="fake-b",
            model_version="fake-b-v1",
        )

    with session_factory() as session:
        assert session.get(NodeAnalysisRun, run_id).status == "SUPERSEDED"
        assert session.query(BModelResult).count() == 0
        assert session.query(AnalysisCandidate).count() == 0


def test_late_b_failure_cannot_overwrite_superseded_run(session_factory):
    source_id, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-B-LATE-FAILURE",
    )

    class EditingFailureClient(FakeBModelClient):
        def recommend(self, **kwargs):
            edit_unattached_node(
                session_factory,
                source_id,
                project_id="proj-01",
                actor_id="editor",
                expected_version=1,
                content="B 호출 중 바뀐 본문",
            )
            raise RuntimeError("late fake failure")

    with pytest.raises(BModelExecutionError):
        execute_b_model(
            session_factory,
            run_id,
            project_id="proj-01",
            client=EditingFailureClient(),
            model="fake-b",
            model_version="fake-b-v1",
        )

    with session_factory() as session:
        run = session.get(NodeAnalysisRun, run_id)
        source = session.get(Node, source_id)
        assert run.status == "SUPERSEDED"
        assert source.analysis_status == "STALE"
        assert session.query(BModelResult).count() == 0
        assert session.query(AnalysisCandidate).count() == 0


def test_b_execution_project_isolation_does_not_call_client(
    session_factory,
):
    _, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-B-PROJECT",
    )
    client = FakeBModelClient(_decision("CREATE_NEW"))
    with pytest.raises(AnalysisRunNotFoundError):
        execute_b_model(
            session_factory,
            run_id,
            project_id="other-project",
            client=client,
            model="fake-b",
            model_version="fake-b-v1",
        )
    assert client.calls == []
    with session_factory() as session:
        run = session.get(NodeAnalysisRun, run_id)
        assert run.status == "RUNNING"
        assert run.b_model_status == "PENDING"


def test_concurrent_b_execution_calls_client_once_and_creates_one_candidate(
    session_factory,
):
    _, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-B-CONCURRENT",
    )
    entered = Barrier(2)
    release = Barrier(2)

    class BlockingClient(FakeBModelClient):
        def recommend(self, **kwargs):
            self.calls.append(kwargs)
            entered.wait(timeout=10)
            release.wait(timeout=10)
            return _decision("LINK", target_id, "RELATED_TO")

    client = BlockingClient()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            execute_b_model,
            session_factory,
            run_id,
            project_id="proj-01",
            client=client,
            model="fake-b",
            model_version="fake-b-v1",
        )
        entered.wait(timeout=10)
        second = pool.submit(
            execute_b_model,
            session_factory,
            run_id,
            project_id="proj-01",
            client=client,
            model="fake-b",
            model_version="fake-b-v1",
        )
        second_result = second.result(timeout=10)
        release.wait(timeout=10)
        first_result = first.result(timeout=10)

    assert second_result.run.b_model_status.value == "RUNNING"
    assert first_result.run.status.value == "COMPLETED"
    assert len(client.calls) == 1
    with session_factory() as session:
        assert session.query(BModelResult).count() == 1
        assert session.query(AnalysisCandidate).count() == 1


def test_create_approval_and_rejection_are_idempotent(session_factory):
    source_id, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-APPROVE-CREATE",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("CREATE_NEW"),
    )
    candidate_id = result.candidate.candidate_id

    approved = approve_create_new(
        session_factory,
        candidate_id,
        project_id="proj-01",
        actor_id="approver",
        expected_version=1,
    )
    replay = approve_create_new(
        session_factory,
        candidate_id,
        project_id="proj-01",
        actor_id="approver",
        expected_version=1,
    )
    with pytest.raises(AnalysisCandidateStateError):
        reject_analysis_candidate(
            session_factory,
            candidate_id,
            project_id="proj-01",
            actor_id="reviewer",
            expected_version=2,
        )

    assert approved.candidate.status.value == "APPROVED"
    assert replay.candidate.status.value == "APPROVED"
    with session_factory() as session:
        source = session.get(Node, source_id)
        assert source.graph_state == "ACTIVE"
        assert source.confirmed_by == "approver"


def test_rejection_replay_is_idempotent_and_does_not_change_node(
    session_factory,
):
    source_id, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-REJECT-REPLAY",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("CREATE_NEW"),
    )
    candidate_id = result.candidate.candidate_id
    rejected = reject_analysis_candidate(
        session_factory,
        candidate_id,
        project_id="proj-01",
        actor_id="rejector",
        expected_version=1,
    )
    replay = reject_analysis_candidate(
        session_factory,
        candidate_id,
        project_id="proj-01",
        actor_id="rejector",
        expected_version=1,
    )

    assert rejected.candidate.status.value == "REJECTED"
    assert replay.candidate.version == rejected.candidate.version
    with session_factory() as session:
        assert session.get(Node, source_id).graph_state == "UNATTACHED"


def test_action_requires_attached_parent_and_attached_link_activates(
    session_factory,
):
    source_id, run_id, parent_id = _action_run_with_parent(
        session_factory,
        meeting_id="M-ACTION-PARENT",
    )
    create_result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("CREATE_NEW"),
    )
    with pytest.raises(AnalysisCandidateStateError):
        approve_analysis_candidate(
            session_factory,
            create_result.candidate.candidate_id,
            project_id="proj-01",
            actor_id="approver",
            expected_version=1,
        )
    reject_analysis_candidate(
        session_factory,
        create_result.candidate.candidate_id,
        project_id="proj-01",
        actor_id="rejector",
        expected_version=1,
    )

    # A fresh Analysis Run is required for a different recommendation.
    with session_factory() as session:
        source = session.get(Node, source_id)
        source.analysis_status = "STALE"
        source.analysis_input_hash = None
        source.current_analysis_run_id = None
        source.version += 1
        session.commit()
    rerun = reanalyze_unattached_node(
        session_factory,
        source_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=2,
        retrieval_config_version="retrieval-test-v2",
    )
    execute_analysis_retrieval(
        session_factory,
        rerun.run.analysis_run_id,
        project_id="proj-01",
        embedding_client=FakeEmbeddingClient(),
    )
    link_result, _ = _execute_decision(
        session_factory,
        run_id=rerun.run.analysis_run_id,
        decision=_decision("LINK", parent_id, "ATTACHED_TO"),
    )
    approved = approve_link_existing(
        session_factory,
        link_result.candidate.candidate_id,
        project_id="proj-01",
        actor_id="approver",
        expected_version=1,
    )

    assert approved.relation_id is not None
    with session_factory() as session:
        source = session.get(Node, source_id)
        assert source.graph_state == "ACTIVE"
        assert source.parent_id == parent_id


def test_cross_category_parent_link_is_refused_at_approval(session_factory):
    source_id, run_id, parent_id = _action_run_with_parent(
        session_factory,
        meeting_id="M-ACTION-CROSS-CATEGORY-PARENT",
    )
    with session_factory() as session:
        source = session.get(Node, source_id)
        parent = session.get(Node, parent_id)
        parent.category = (
            "INFRA" if source.category != "INFRA" else "BACKEND"
        )
        session.commit()

    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("LINK", parent_id, "ATTACHED_TO"),
    )
    with pytest.raises(AnalysisCandidateStateError):
        approve_link_existing(
            session_factory,
            result.candidate.candidate_id,
            project_id="proj-01",
            actor_id="approver",
            expected_version=1,
        )

    with session_factory() as session:
        source = session.get(Node, source_id)
        assert source.graph_state == "UNATTACHED"
        assert source.parent_id is None


def test_approve_reject_race_has_one_terminal_winner(session_factory):
    source_id, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-CANDIDATE-RACE",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("CREATE_NEW"),
    )
    candidate_id = result.candidate.candidate_id

    def approve():
        return approve_analysis_candidate(
            session_factory,
            candidate_id,
            project_id="proj-01",
            actor_id="approver",
            expected_version=1,
        )

    def reject():
        return reject_analysis_candidate(
            session_factory,
            candidate_id,
            project_id="proj-01",
            actor_id="rejector",
            expected_version=1,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(approve), pool.submit(reject)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=10))
            except AnalysisCandidateStateError:
                outcomes.append("state-error")

    assert sum(item == "state-error" for item in outcomes) == 1
    with session_factory() as session:
        candidate = session.get(
            AnalysisCandidate,
            uuid.UUID(candidate_id),
        )
        source = session.get(Node, source_id)
        assert candidate.status in {"APPROVED", "REJECTED"}
        assert (source.graph_state == "ACTIVE") == (
            candidate.status == "APPROVED"
        )


def test_candidate_project_isolation_is_not_found_and_unchanged(
    session_factory,
):
    source_id, run_id, _ = _run_with_retrieval(
        session_factory,
        meeting_id="M-CANDIDATE-PROJECT",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("CREATE_NEW"),
    )
    with pytest.raises(AnalysisCandidateNotFoundError):
        approve_analysis_candidate(
            session_factory,
            result.candidate.candidate_id,
            project_id="other-project",
            actor_id="intruder",
            expected_version=1,
        )
    with session_factory() as session:
        assert session.get(Node, source_id).graph_state == "UNATTACHED"
        assert (
            session.get(
                AnalysisCandidate,
                uuid.UUID(result.candidate.candidate_id),
            ).status
            == "PENDING"
        )


def test_link_approval_keeps_ready_embedding(session_factory):
    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-APPROVE-LINK",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("LINK", target_id, "RELATED_TO"),
    )
    approved = approve_link_existing(
        session_factory,
        result.candidate.candidate_id,
        project_id="proj-01",
        actor_id="approver",
        expected_version=1,
    )

    assert approved.relation_id is not None
    with session_factory() as session:
        assert session.get(Node, source_id).graph_state == "ACTIVE"
        embedding = session.get(
            NodeEmbedding,
            {"node_id": source_id, "embedding_version": EMBEDDING_CONTRACT_VERSION},
        )
        assert embedding.status == "READY"
        assert session.query(Relation).count() == 1


def test_merge_approval_stales_target_embedding_and_keeps_lineage(
    session_factory,
):
    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-APPROVE-MERGE",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("MERGE", target_id),
    )
    approved = approve_merge_existing(
        session_factory,
        result.candidate.candidate_id,
        project_id="proj-01",
        actor_id="approver",
        expected_version=1,
    )

    assert approved.merge_history_id is not None
    with session_factory() as session:
        source = session.get(Node, source_id)
        target = session.get(Node, target_id)
        target_embedding = session.get(
            NodeEmbedding,
            {"node_id": target_id, "embedding_version": EMBEDDING_CONTRACT_VERSION},
        )
        assert source.graph_state == "MERGED"
        assert source.merged_into_node_id == target_id
        source_embedding = session.get(
            NodeEmbedding,
            {"node_id": source_id, "embedding_version": EMBEDDING_CONTRACT_VERSION},
        )
        assert source_embedding.status == "STALE"
        assert target.graph_state == "ACTIVE"
        assert target_embedding.status == "STALE"
        revision = session.get(NodeRevision, target.current_revision_id)
        assert revision.title == "사용자가 검토할 최종 제목"
        assert revision.content == "사용자가 검토할 최종 본문"
        assert session.query(NodeMergeHistory).count() == 1


def test_merge_with_unchanged_target_meaning_keeps_embedding_ready(
    session_factory,
):
    _, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-APPROVE-MERGE-SAME-MEANING",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("MERGE", target_id),
    )
    with session_factory() as session:
        target = session.get(Node, target_id)
        title, content = target.title, target.content
        embedding = session.get(
            NodeEmbedding,
            {"node_id": target_id, "embedding_version": EMBEDDING_CONTRACT_VERSION},
        )
        embedding.embedded_text_hash = embedding_text_hash(
            build_embedding_text_from_parts(
                node_type=target.node_type,
                title=target.title,
                content=target.content,
                evidence_pairs=[],
            )
        )
        session.commit()

    approve_merge_existing(
        session_factory,
        result.candidate.candidate_id,
        project_id="proj-01",
        actor_id="approver",
        expected_version=1,
        merged_title=title,
        merged_content=content,
    )

    with session_factory() as session:
        target = session.get(Node, target_id)
        embedding = session.get(
            NodeEmbedding,
            {"node_id": target_id, "embedding_version": EMBEDDING_CONTRACT_VERSION},
        )
        assert embedding.status == "READY"
        assert session.get(NodeRevision, target.current_revision_id).title == title


def test_unattached_merge_target_is_excluded_before_approval(
    session_factory,
):
    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-APPROVE-MERGE-UNATTACHED",
        target_state="UNATTACHED",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("MERGE", target_id),
    )
    # The current contract admits only ACTIVE canonical MERGE targets, so an
    # UNATTACHED target is removed before a pending approval candidate exists.
    assert result.candidate is None
    with session_factory() as session:
        assert session.get(Node, source_id).graph_state == "UNATTACHED"
        assert session.get(Node, target_id).graph_state == "UNATTACHED"


def test_approval_failure_rolls_back_candidate_node_and_embedding(
    session_factory,
):
    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-APPROVE-ROLLBACK",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("MERGE", target_id),
    )
    with session_factory() as session:
        target = session.get(Node, target_id)
        target.version += 1
        session.commit()

    with pytest.raises(AnalysisCandidateStateError):
        approve_analysis_candidate(
            session_factory,
            result.candidate.candidate_id,
            project_id="proj-01",
            actor_id="approver",
            expected_version=1,
        )

    with session_factory() as session:
        source = session.get(Node, source_id)
        candidate = session.get(
            AnalysisCandidate,
            uuid.UUID(result.candidate.candidate_id),
        )
        embedding = session.get(
            NodeEmbedding,
            {"node_id": target_id, "embedding_version": EMBEDDING_CONTRACT_VERSION},
        )
        assert source.graph_state == "UNATTACHED"
        assert candidate.status == "PENDING"
        assert embedding.status == "READY"
        assert session.query(NodeMergeHistory).count() == 0


def test_cross_category_merge_is_refused_at_approval(session_factory):
    """MERGE folds two Nodes into one identity, which cannot span categories.

    Every Retrieval path scopes MERGE by category. This test mutates the target
    after Retrieval to prove the apply transaction independently rejects a
    stale or forged cross-category candidate.
    """

    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-MERGE-CROSS-CATEGORY",
    )
    with session_factory() as session:
        source = session.get(Node, source_id)
        target = session.get(Node, target_id)
        assert target.category == source.category  # guard is the only difference
        target.category = "INFRA" if source.category != "INFRA" else "BACKEND"
        session.commit()

    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("MERGE", target_id),
    )

    with pytest.raises(AnalysisCandidateStateError):
        approve_merge_existing(
            session_factory,
            result.candidate.candidate_id,
            project_id="proj-01",
            actor_id="approver",
            expected_version=1,
            merged_title="병합된 제목",
            merged_content="병합된 본문",
        )

    with session_factory() as session:
        source = session.get(Node, source_id)
        candidate = session.get(
            AnalysisCandidate,
            uuid.UUID(result.candidate.candidate_id),
        )
        assert source.graph_state == "UNATTACHED"   # not absorbed
        assert candidate.status == "PENDING"        # still decidable
        assert session.query(NodeMergeHistory).count() == 0


def test_same_category_merge_still_succeeds(session_factory):
    """The new guard must not block the ordinary same-category MERGE."""

    source_id, run_id, target_id = _run_with_retrieval(
        session_factory,
        meeting_id="M-MERGE-SAME-CATEGORY",
    )
    result, _ = _execute_decision(
        session_factory,
        run_id=run_id,
        decision=_decision("MERGE", target_id),
    )
    approved = approve_merge_existing(
        session_factory,
        result.candidate.candidate_id,
        project_id="proj-01",
        actor_id="approver",
        expected_version=1,
        merged_title="병합된 제목",
        merged_content="병합된 본문",
    )

    assert approved.candidate.status.value == "APPROVED"
    with session_factory() as session:
        assert session.get(Node, source_id).graph_state == "MERGED"
        assert session.query(NodeMergeHistory).count() == 1
