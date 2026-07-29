from __future__ import annotations

import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError

from data_pipeline.contracts import Lineage
from data_pipeline.pipeline import (
    CandidateStateError,
    CandidateValidationError,
    CandidateVersionConflict,
    approve_candidate,
    bulk_approve_candidates,
    edit_candidate,
    get_candidate,
    list_candidates,
    persist_generation_candidates,
    reject_candidate,
    seed_node,
)
from data_pipeline.storage import (
    CandidateReviewEvent,
    Category,
    GraphChangeEvent,
    Node,
    NodeCandidate,
    NodeEvidence,
    Relation,
    Request,
    session_scope,
)

from .support import count, ev, item, judgment, request_payload, seg


def _persist(
    session_factory,
    *,
    meeting_id: str,
    rows: list[tuple[dict, dict]],
    project_id: str = "proj-01",
    request_id: str | None = None,
):
    segments = [
        seg(
            f"s{index}",
            f"{source_item['title']}에 관한 충분히 긴 회의 근거 문장입니다.",
            index * 1000,
        )
        for index, (source_item, _) in enumerate(rows, start=1)
    ]
    items = []
    judgments = []
    for index, (source_item, source_judgment) in enumerate(rows, start=1):
        current = copy.deepcopy(source_item)
        current["evidence"] = [ev(f"s{index}", segments[index - 1]["text"])]
        items.append(current)
        judgments.append(copy.deepcopy(source_judgment))
    payload = request_payload(
        meeting_id=meeting_id,
        project_id=project_id,
        segments=segments,
        items=items,
        judgments=judgments,
        request_id=request_id,
    )
    persist_generation_candidates(
        session_factory,
        payload,
        raw_extraction={"meetingId": meeting_id, "items": items},
        raw_judgment={"meetingId": meeting_id, "judgments": judgments},
        lineage=Lineage(generatedBy="AI"),
        usage={},
    )
    return list_candidates(
        session_factory,
        project_id=project_id,
        external_meeting_id=meeting_id,
    )


def _decision(item_id: str = "d1"):
    return (
        item(item_id, "DECISION", "아키텍처 결정", "결정 내용", []),
        judgment(item_id, "NEW_DECISION", category="BACKEND"),
    )


def _action(item_id: str = "a1", *, parent: str | None = None):
    return (
        item(item_id, "ACTION", "구현 작업", "작업 내용", []),
        judgment(
            item_id,
            "ATTACH" if parent else "UNATTACHED",
            attachTo=parent,
            reason=None if parent else "NO_RELATED_DECISION",
        ),
    )


def _issue(item_id: str = "i1", *, parent: str | None = None):
    return (
        item(item_id, "ISSUE", "운영 문제", "문제 내용", []),
        judgment(
            item_id,
            "ATTACH" if parent else "UNATTACHED",
            attachTo=parent,
            reason=None if parent else "NO_RELATED_DECISION",
        ),
    )


def _minutes(item_id: str = "m1"):
    return (
        item(item_id, "ISSUE", "참고 사항", "회의록 내용", []),
        judgment(item_id, "MINUTES_ONLY", reason="NOT_CONFIRMED"),
    )


def _by_source(views):
    return {view.source_item_id: view for view in views}


def test_list_effective_values_explicit_parent_none_and_filters(session_factory):
    views = _persist(
        session_factory,
        meeting_id="M-VIEW",
        rows=[_decision(), _action(parent="d1"), _minutes()],
    )
    candidates = _by_source(views)
    action = candidates["a1"]
    assert action.effective_type == action.suggested_type == "ACTION"
    assert action.effective_title == action.suggested_title
    assert action.effective_parent_candidate_id == candidates["d1"].candidate_id

    edited = edit_candidate(
        session_factory,
        action.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        title="수정된 구현 작업",
        content="수정된 작업 내용",
        parent_mode="NONE",
    ).candidates[0]
    assert edited.reviewed_title == edited.effective_title == "수정된 구현 작업"
    assert edited.effective_content == "수정된 작업 내용"
    assert edited.reviewed_parent_mode == "NONE"
    assert edited.effective_parent_candidate_id is None
    assert edited.effective_parent_node_id is None

    approve_candidate(
        session_factory,
        candidates["d1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    reject_candidate(
        session_factory,
        candidates["m1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    assert len(list_candidates(session_factory, project_id="proj-01", review_status="PENDING")) == 1
    assert len(list_candidates(session_factory, project_id="proj-01", review_status="APPROVED")) == 1
    assert len(list_candidates(session_factory, project_id="proj-01", review_status="REJECTED")) == 1
    assert len(list_candidates(session_factory, project_id="proj-01", node_type="ACTION")) == 1
    assert len(
        list_candidates(
            session_factory,
            project_id="proj-01",
            suggested_disposition="MINUTES_ONLY",
        )
    ) == 1


def test_edit_is_optimistic_idempotent_audited_and_preserves_suggestion(session_factory):
    raw_unknown = (
        item("u1", "ALIEN", "알 수 없는 후보", "원문", []),
        judgment("u1", "MINUTES_ONLY", reason="NOT_CONFIRMED"),
    )
    candidate = _persist(
        session_factory,
        meeting_id="M-EDIT",
        rows=[raw_unknown],
    )[0]
    assert candidate.suggested_type == candidate.effective_type == "UNKNOWN"

    edited = edit_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        node_type="ISSUE",
        title="검토된 후보",
    ).candidates[0]
    assert edited.version == 2
    assert edited.effective_type == "ISSUE"
    assert edited.suggested_type == "UNKNOWN"

    replayed = edit_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        node_type="ISSUE",
        title="검토된 후보",
    ).candidates[0]
    assert replayed.version == 2
    assert count(session_factory, CandidateReviewEvent) == 1

    with pytest.raises(CandidateVersionConflict):
        edit_candidate(
            session_factory,
            candidate.candidate_id,
            actor_id="other",
            expected_version=1,
            title="충돌 수정",
        )
    with session_factory() as session:
        row = session.get(NodeCandidate, uuid.UUID(candidate.candidate_id))
        assert row.raw_item["type"] == "ALIEN"
        assert row.suggested_node_type == "UNKNOWN"


def test_reject_is_idempotent_audited_and_never_changes_graph(session_factory):
    candidate = _persist(
        session_factory,
        meeting_id="M-REJECT",
        rows=[_decision()],
    )[0]
    rejected = reject_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
    ).candidates[0]
    assert rejected.review_status == "REJECTED"
    assert rejected.version == 2
    replayed = reject_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
    ).candidates[0]
    assert replayed.version == 2
    assert count(session_factory, CandidateReviewEvent) == 1
    assert count(session_factory, Node) == 0
    assert count(session_factory, NodeEvidence) == 0
    assert count(session_factory, Relation) == 0
    assert count(session_factory, GraphChangeEvent) == 0
    with pytest.raises(CandidateStateError):
        edit_candidate(
            session_factory,
            candidate.candidate_id,
            actor_id="reviewer",
            expected_version=rejected.version,
            title="거절 후 수정",
        )


def test_new_decision_approval_copies_effective_values_evidence_and_is_idempotent(
    session_factory,
):
    candidate = _persist(
        session_factory,
        meeting_id="M-DECISION",
        rows=[_decision()],
    )[0]
    edited = edit_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        title="사용자 확정 제목",
        content="사용자 확정 내용",
    ).candidates[0]
    approved = approve_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=edited.version,
    )
    view = approved.candidates[0]
    assert view.review_status == "APPROVED"
    assert view.confirmed_node_id
    assert len(approved.created_node_ids) == 1
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(view.confirmed_node_id))
        assert node.node_type == "DECISION"
        assert node.title == "사용자 확정 제목"
        assert node.content == "사용자 확정 내용"
        assert session.query(NodeEvidence).filter_by(node_id=node.id).count() == 1
        assert session.query(GraphChangeEvent).filter_by(change_type="CREATE").count() == 1

    replayed = approve_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="other",
        expected_version=1,
    )
    assert replayed.created_node_ids == []
    assert replayed.candidates[0].confirmed_node_id == view.confirmed_node_id
    assert count(session_factory, Node) == 1
    assert count(session_factory, GraphChangeEvent) == 1
    with pytest.raises(CandidateStateError):
        edit_candidate(
            session_factory,
            candidate.candidate_id,
            actor_id="reviewer",
            expected_version=view.version,
            title="승인 후 수정",
        )
    with pytest.raises(CandidateStateError):
        reject_candidate(
            session_factory,
            candidate.candidate_id,
            actor_id="reviewer",
        )


def test_bulk_attach_is_topological_and_creates_confirmed_relation(session_factory):
    candidates = _by_source(
        _persist(
            session_factory,
            meeting_id="M-ATTACH",
            rows=[_decision(), _action(parent="d1"), _issue(parent="a1")],
        )
    )
    result = bulk_approve_candidates(
        session_factory,
        [
            candidates["i1"].candidate_id,
            candidates["a1"].candidate_id,
            candidates["d1"].candidate_id,
        ],
        actor_id="reviewer",
        expected_versions={
            candidate.candidate_id: candidate.version
            for candidate in candidates.values()
        },
    )
    assert len(result.created_node_ids) == 3
    assert len(result.created_relation_ids) == 2
    with session_factory() as session:
        nodes = {node.source_item_id: node for node in session.query(Node).all()}
        relations = session.query(Relation).all()
        assert nodes["a1"].parent_id == nodes["d1"].id
        assert nodes["i1"].parent_id == nodes["a1"].id
        assert {
            (relation.from_node_id, relation.to_node_id, relation.relation_type, relation.status)
            for relation in relations
        } == {
            (nodes["a1"].id, nodes["d1"].id, "ATTACHED_TO", "CONFIRMED"),
            (nodes["i1"].id, nodes["a1"].id, "ATTACHED_TO", "CONFIRMED"),
        }
        assert session.query(GraphChangeEvent).filter_by(change_type="CREATE").count() == 3
        assert session.query(GraphChangeEvent).filter_by(change_type="ATTACH").count() == 2
        assert session.query(Request).one().status == "REVIEW_COMPLETED"

    replayed = bulk_approve_candidates(
        session_factory,
        [candidate.candidate_id for candidate in candidates.values()],
        actor_id="other",
    )
    assert replayed.created_node_ids == []
    assert replayed.created_relation_ids == []
    assert count(session_factory, Node) == 3
    assert count(session_factory, Relation) == 2


def test_unattached_and_minutes_only_policies(session_factory):
    candidates = _by_source(
        _persist(
            session_factory,
            meeting_id="M-NONGRAPH",
            rows=[_action(), _minutes()],
        )
    )
    unattached = approve_candidate(
        session_factory,
        candidates["a1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    assert len(unattached.created_node_ids) == 1
    assert unattached.created_relation_ids == []
    with session_factory() as session:
        assert session.query(Node).one().graph_state == "UNATTACHED"
        assert session.query(Request).one().status == "REVIEW_PENDING"

    minutes = approve_candidate(
        session_factory,
        candidates["m1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    assert minutes.created_node_ids == []
    assert minutes.candidates[0].review_status == "APPROVED"
    assert minutes.candidates[0].confirmed_node_id is None
    assert count(session_factory, Node) == 1
    assert count(session_factory, Relation) == 0
    assert count(session_factory, GraphChangeEvent) == 1
    assert count(session_factory, CandidateReviewEvent) == 2
    with session_factory() as session:
        assert session.query(Request).one().status == "REVIEW_COMPLETED"


def test_attach_to_existing_confirmed_node(session_factory):
    with session_scope(session_factory) as session:
        parent = seed_node(
            session,
            project_id="proj-01",
            source_meeting_id="M0",
            source_item_id="existing-decision",
            node_type="DECISION",
            category="BACKEND",
            title="기존 확정 결정",
        )
        parent_id = str(parent.id)
    action = _persist(
        session_factory,
        meeting_id="M-EXISTING-PARENT",
        rows=[_action()],
    )[0]
    edited = edit_candidate(
        session_factory,
        action.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        disposition="ATTACH",
        parent_mode="NODE",
        parent_node_id=parent_id,
    ).candidates[0]
    approved = approve_candidate(
        session_factory,
        action.candidate_id,
        actor_id="reviewer",
        expected_version=edited.version,
    )
    assert len(approved.created_node_ids) == 1
    assert len(approved.created_relation_ids) == 1
    with session_factory() as session:
        relation = session.query(Relation).one()
        assert str(relation.from_node_id) == approved.created_node_ids[0]
        assert str(relation.to_node_id) == parent_id
        assert relation.relation_type == "ATTACHED_TO"


def test_parent_validation_rejects_missing_rejected_minutes_cross_project_and_self(
    session_factory,
):
    candidates = _by_source(
        _persist(
            session_factory,
            meeting_id="M-PARENT-INVALID",
            rows=[_decision(), _action(parent="d1")],
        )
    )
    action = candidates["a1"]
    parent = candidates["d1"]

    edit_candidate(
        session_factory,
        action.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        parent_mode="NONE",
    )
    with pytest.raises(CandidateValidationError):
        approve_candidate(session_factory, action.candidate_id, actor_id="reviewer")

    edit_candidate(
        session_factory,
        action.candidate_id,
        actor_id="reviewer",
        expected_version=2,
        parent_mode="CANDIDATE",
        parent_candidate_id=parent.candidate_id,
    )
    reject_candidate(
        session_factory,
        parent.candidate_id,
        actor_id="reviewer",
    )
    with pytest.raises(CandidateValidationError):
        approve_candidate(session_factory, action.candidate_id, actor_id="reviewer")

    other = _persist(
        session_factory,
        meeting_id="M-OTHER-PROJECT",
        project_id="other-project",
        rows=[_decision("other-d")],
    )[0]
    edit_candidate(
        session_factory,
        action.candidate_id,
        actor_id="reviewer",
        expected_version=3,
        parent_mode="CANDIDATE",
        parent_candidate_id=other.candidate_id,
    )
    with pytest.raises(CandidateValidationError):
        approve_candidate(session_factory, action.candidate_id, actor_id="reviewer")

    with pytest.raises(CandidateValidationError):
        edit_candidate(
            session_factory,
            action.candidate_id,
            actor_id="reviewer",
            expected_version=4,
            parent_mode="CANDIDATE",
            parent_candidate_id=action.candidate_id,
        )
    assert count(session_factory, Node) == 0


def test_minutes_parent_and_cross_project_node_are_rejected(session_factory):
    candidates = _by_source(
        _persist(
            session_factory,
            meeting_id="M-PARENT-MINUTES",
            rows=[_decision(), _action(parent="d1")],
        )
    )
    edit_candidate(
        session_factory,
        candidates["d1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
        disposition="MINUTES_ONLY",
    )
    with pytest.raises(CandidateValidationError):
        bulk_approve_candidates(
            session_factory,
            [candidates["a1"].candidate_id, candidates["d1"].candidate_id],
            actor_id="reviewer",
        )

    with session_scope(session_factory) as session:
        other_node = seed_node(
            session,
            project_id="other-project",
            source_meeting_id="M0",
            source_item_id="other-parent",
            node_type="DECISION",
            category="BACKEND",
            title="다른 프로젝트 결정",
        )
        other_node_id = str(other_node.id)
    edit_candidate(
        session_factory,
        candidates["a1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
        parent_mode="NODE",
        parent_node_id=other_node_id,
    )
    with pytest.raises(CandidateValidationError):
        approve_candidate(
            session_factory,
            candidates["a1"].candidate_id,
            actor_id="reviewer",
        )
    assert count(session_factory, Relation) == 0


def test_cycle_and_bulk_failure_roll_back_every_review_and_graph_row(session_factory):
    cycle = _by_source(
        _persist(
            session_factory,
            meeting_id="M-CYCLE",
            rows=[_issue("i1"), _issue("i2")],
        )
    )
    with session_factory() as session:
        first = session.get(NodeCandidate, uuid.UUID(cycle["i1"].candidate_id))
        second = session.get(NodeCandidate, uuid.UUID(cycle["i2"].candidate_id))
        first.reviewed_disposition = second.reviewed_disposition = "ATTACH"
        first.reviewed_parent_mode = second.reviewed_parent_mode = "CANDIDATE"
        first.reviewed_parent_candidate_id = second.id
        second.reviewed_parent_candidate_id = first.id
        session.commit()
    with pytest.raises(CandidateValidationError, match="cycle"):
        bulk_approve_candidates(
            session_factory,
            [cycle["i1"].candidate_id, cycle["i2"].candidate_id],
            actor_id="reviewer",
        )
    assert count(session_factory, Node) == 0
    assert count(session_factory, Relation) == 0
    assert count(session_factory, GraphChangeEvent) == 0
    assert count(session_factory, CandidateReviewEvent) == 0
    with session_factory() as session:
        assert {row.review_status for row in session.query(NodeCandidate).all()} == {
            "PENDING"
        }

    atomic = _by_source(
        _persist(
            session_factory,
            meeting_id="M-ATOMIC-REVIEW",
            rows=[_decision("d2"), _action("a2")],
        )
    )
    edit_candidate(
        session_factory,
        atomic["a2"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
        disposition="ATTACH",
        parent_mode="NONE",
    )
    with pytest.raises(CandidateValidationError):
        bulk_approve_candidates(
            session_factory,
            [atomic["d2"].candidate_id, atomic["a2"].candidate_id],
            actor_id="reviewer",
        )
    assert count(session_factory, Node) == 0
    with session_factory() as session:
        rows = session.query(NodeCandidate).filter_by(
            external_meeting_id="M-ATOMIC-REVIEW"
        )
        assert {row.review_status for row in rows} == {"PENDING"}


def test_approval_version_conflict_and_request_partial_completion(session_factory):
    candidates = _by_source(
        _persist(
            session_factory,
            meeting_id="M-VERSION",
            rows=[_decision(), _minutes()],
        )
    )
    with pytest.raises(CandidateVersionConflict):
        approve_candidate(
            session_factory,
            candidates["d1"].candidate_id,
            actor_id="reviewer",
            expected_version=99,
        )
    assert count(session_factory, Node) == 0

    approve_candidate(
        session_factory,
        candidates["d1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    with session_factory() as session:
        assert session.query(Request).one().status == "REVIEW_PENDING"
    reject_candidate(
        session_factory,
        candidates["m1"].candidate_id,
        actor_id="reviewer",
    )
    with session_factory() as session:
        assert session.query(Request).one().status == "REVIEW_COMPLETED"


def test_concurrent_approval_creates_at_most_one_node_and_event(
    monkeypatch,
    session_factory,
):
    import data_pipeline.pipeline.review as review

    candidate = _persist(
        session_factory,
        meeting_id="M-CONCURRENT-APPROVAL",
        rows=[_decision()],
    )[0]
    barrier = Barrier(2)
    real_order = review._ordered_candidates

    def synchronize_after_both_callers_read(candidates, effective_by_id):
        ordered = real_order(candidates, effective_by_id)
        barrier.wait(timeout=5)
        return ordered

    monkeypatch.setattr(
        review,
        "_ordered_candidates",
        synchronize_after_both_callers_read,
    )

    def approve(actor):
        return approve_candidate(
            session_factory,
            candidate.candidate_id,
            actor_id=actor,
            expected_version=1,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(approve, ["reviewer-1", "reviewer-2"]))

    assert sorted(len(result.created_node_ids) for result in results) == [0, 1]
    assert count(session_factory, Node) == 1
    assert count(session_factory, GraphChangeEvent) == 1
    assert count(session_factory, CandidateReviewEvent) == 1


def test_get_candidate_scopes_project(session_factory):
    candidate = _persist(
        session_factory,
        meeting_id="M-GET",
        rows=[_decision()],
    )[0]
    assert (
        get_candidate(
            session_factory,
            candidate.candidate_id,
            project_id="proj-01",
        ).candidate_id
        == candidate.candidate_id
    )


def test_regenerated_same_source_item_candidates_each_create_their_own_node(
    session_factory,
):
    first = _persist(
        session_factory,
        meeting_id="M-REGENERATED-SOURCE",
        request_id="req-source-1",
        rows=[_decision("m1")],
    )[0]
    all_candidates = _persist(
        session_factory,
        meeting_id="M-REGENERATED-SOURCE",
        request_id="req-source-2",
        rows=[
            (
                item("m1", "DECISION", "재생성된 결정", "다른 생성 입력", []),
                judgment("m1", "NEW_DECISION", category="BACKEND"),
            )
        ],
    )
    second = next(
        candidate
        for candidate in all_candidates
        if candidate.candidate_id != first.candidate_id
    )

    first_result = approve_candidate(
        session_factory,
        first.candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    second_result = approve_candidate(
        session_factory,
        second.candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )

    assert len(first_result.created_node_ids) == 1
    assert len(second_result.created_node_ids) == 1
    with session_factory() as session:
        nodes = session.query(Node).order_by(Node.created_at).all()
        candidates = {
            row.id: row
            for row in session.query(NodeCandidate).all()
        }
        assert len(nodes) == 2
        assert {node.source_item_id for node in nodes} == {"m1"}
        assert {node.source_meeting_id for node in nodes} == {
            "M-REGENERATED-SOURCE"
        }
        assert len({node.source_candidate_id for node in nodes}) == 2
        for node in nodes:
            assert node.source_candidate_id is not None
            assert candidates[node.source_candidate_id].confirmed_node_id == node.id

        duplicate = Node(
            source_candidate_id=nodes[0].source_candidate_id,
            project_id="proj-01",
            source_meeting_id="other-meeting",
            source_item_id="other-item",
            node_type="DECISION",
            category="BACKEND",
            title="중복 candidate 출처",
            content="",
            graph_state="ACTIVE",
            lifecycle_status="ACTIVE",
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.flush()

    replay = approve_candidate(
        session_factory,
        first.candidate_id,
        actor_id="reviewer",
    )
    assert replay.created_node_ids == []
    assert count(session_factory, Node) == 2


def test_category_edit_uses_active_category_and_records_audit(session_factory):
    candidate = _persist(
        session_factory,
        meeting_id="M-CATEGORY-EDIT",
        rows=[_decision()],
    )[0]
    assert candidate.suggested_category == "BACKEND"
    assert candidate.effective_category == "BACKEND"

    edited = edit_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        category="FRONTEND",
    ).candidates[0]
    assert edited.reviewed_category == "FRONTEND"
    assert edited.effective_category == "FRONTEND"
    assert edited.suggested_category == "BACKEND"
    assert edited.version == 2
    with session_factory() as session:
        event = session.query(CandidateReviewEvent).one()
        assert event.before_json["reviewedCategory"] is None
        assert event.before_json["effectiveCategory"] == "BACKEND"
        assert event.after_json["reviewedCategory"] == "FRONTEND"
        assert event.after_json["effectiveCategory"] == "FRONTEND"

    replayed = edit_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        category="FRONTEND",
    ).candidates[0]
    assert replayed.version == 2
    assert count(session_factory, CandidateReviewEvent) == 1
    with pytest.raises(CandidateVersionConflict):
        edit_candidate(
            session_factory,
            candidate.candidate_id,
            actor_id="reviewer",
            expected_version=1,
            category="AI",
        )


def test_category_edit_rejects_missing_inactive_and_non_pending_candidates(
    session_factory,
):
    candidates = _by_source(
        _persist(
            session_factory,
            meeting_id="M-CATEGORY-VALIDATION",
            rows=[_decision("d1"), _minutes("m1")],
        )
    )
    with session_factory() as session:
        session.add(
            Category(
                value="DISABLED",
                position=99,
                is_active=False,
                schema_version="cat-test",
            )
        )
        session.commit()

    with pytest.raises(CandidateValidationError, match="not active"):
        edit_candidate(
            session_factory,
            candidates["d1"].candidate_id,
            actor_id="reviewer",
            expected_version=1,
            category="DOES_NOT_EXIST",
        )
    with pytest.raises(CandidateValidationError, match="not active"):
        edit_candidate(
            session_factory,
            candidates["d1"].candidate_id,
            actor_id="reviewer",
            expected_version=1,
            category="DISABLED",
        )

    approve_candidate(
        session_factory,
        candidates["d1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    reject_candidate(
        session_factory,
        candidates["m1"].candidate_id,
        actor_id="reviewer",
        expected_version=1,
    )
    with pytest.raises(CandidateStateError):
        edit_candidate(
            session_factory,
            candidates["d1"].candidate_id,
            actor_id="reviewer",
            expected_version=2,
            category="AI",
        )
    with pytest.raises(CandidateStateError):
        edit_candidate(
            session_factory,
            candidates["m1"].candidate_id,
            actor_id="reviewer",
            expected_version=2,
            category="AI",
        )


def test_invalid_suggested_category_can_be_repaired_before_approval(session_factory):
    candidate = _persist(
        session_factory,
        meeting_id="M-CATEGORY-REPAIR",
        rows=[
            (
                item("m1", "DECISION", "잘못된 카테고리 결정", "결정 내용", []),
                judgment("m1", "NEW_DECISION", category="NOT_A_CATEGORY"),
            )
        ],
    )[0]
    assert candidate.effective_category == "NOT_A_CATEGORY"
    with pytest.raises(CandidateValidationError, match="active category"):
        approve_candidate(
            session_factory,
            candidate.candidate_id,
            actor_id="reviewer",
            expected_version=1,
        )

    edited = edit_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=1,
        category="BACKEND",
    ).candidates[0]
    approved = approve_candidate(
        session_factory,
        candidate.candidate_id,
        actor_id="reviewer",
        expected_version=edited.version,
    )
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(approved.created_node_ids[0]))
        row = session.get(NodeCandidate, uuid.UUID(candidate.candidate_id))
        assert node.category == "BACKEND"
        assert node.source_candidate_id == row.id
        assert row.suggested_category == "NOT_A_CATEGORY"
        assert row.reviewed_category == "BACKEND"
