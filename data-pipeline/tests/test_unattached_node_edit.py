from __future__ import annotations

import uuid

import pytest

from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
from data_pipeline.contracts import Lineage
from data_pipeline.pipeline import (
    NodeStateError,
    NodeValidationError,
    NodeVersionConflict,
    complete_initial_review,
    edit_unattached_node,
    list_candidates,
    persist_generation_candidates,
    seed_node,
)
from data_pipeline.storage import (
    GraphChangeEvent,
    Node,
    NodeCandidate,
    NodeEmbedding,
    NodeEvidence,
    session_scope,
)

from .support import ev, item, judgment, request_payload, seg


def _initial_node(session_factory, *, meeting_id: str = "M-UNATTACHED"):
    transcript = "Redis를 세션 캐시 저장소로 사용하기로 최종 결정했습니다."
    segments = [seg("s1", transcript, 1000)]
    source_item = item(
        "d1",
        "DECISION",
        "Redis 캐시 결정",
        "세션 조회 성능을 위해 Redis를 사용한다.",
        [ev("s1", transcript)],
    )
    source_judgment = judgment(
        "d1",
        "NEW_DECISION",
        category="BACKEND",
    )
    payload = request_payload(
        meeting_id=meeting_id,
        segments=segments,
        items=[source_item],
        judgments=[source_judgment],
    )
    persist_generation_candidates(
        session_factory,
        payload,
        raw_extraction={"meetingId": meeting_id, "items": [source_item]},
        raw_judgment={
            "meetingId": meeting_id,
            "judgments": [source_judgment],
        },
        lineage=Lineage(generatedBy="AI"),
        usage={},
    )
    candidate = list_candidates(
        session_factory,
        project_id="proj-01",
        external_meeting_id=meeting_id,
    )[0]
    reviewed = complete_initial_review(
        session_factory,
        candidate.candidate_id,
        project_id="proj-01",
        actor_id="reviewer",
        expected_version=1,
    ).candidates[0]
    return reviewed.initial_review_node_id, candidate.candidate_id, transcript


def test_edit_unattached_node_invalidates_analysis_and_is_idempotent(
    session_factory,
):
    node_id, candidate_id, _ = _initial_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        node.analysis_status = "ANALYZED"
        node.analysis_input_hash = "a" * 64
        session.add(
            NodeEmbedding(
                node_id=node.id,
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=1536,
                embedded_text_hash="a" * 64,
                status="READY",
            )
        )
        session.commit()

    result = edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="editor",
        expected_version=1,
        title="Redis 세션 캐시 최종안",
        content="세션 조회는 Redis 캐시를 우선 사용한다.",
    )

    assert result.analysis_invalidated is True
    assert result.node.version == 2
    assert result.node.graph_state.value == "UNATTACHED"
    assert result.node.analysis_status == "STALE"
    assert result.node.analysis_input_hash is None
    with session_factory() as session:
        candidate = session.get(NodeCandidate, uuid.UUID(candidate_id))
        embedding = session.get(
            NodeEmbedding,
            {
                "node_id": uuid.UUID(node_id),
                "embedding_version": EMBEDDING_CONTRACT_VERSION,
            },
        )
        assert candidate.suggested_title == "Redis 캐시 결정"
        assert embedding.status == "STALE"
        events = session.query(GraphChangeEvent).order_by(
            GraphChangeEvent.created_at
        ).all()
        assert [event.detail["stage"] for event in events] == [
            "INITIAL_REVIEW",
            "UNATTACHED_EDIT",
        ]
        assert events[-1].detail["analysisInvalidated"] is True

    replayed = edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="other-editor",
        expected_version=1,
        title="Redis 세션 캐시 최종안",
        content="세션 조회는 Redis 캐시를 우선 사용한다.",
    )
    assert replayed.analysis_invalidated is False
    assert replayed.node.version == 2

    with pytest.raises(NodeVersionConflict):
        edit_unattached_node(
            session_factory,
            node_id,
            project_id="proj-01",
            actor_id="other-editor",
            expected_version=1,
            title="서로 다른 오래된 수정",
        )


def test_edit_unattached_node_replaces_evidence_with_key_based_upsert(
    session_factory,
):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-UNATTACHED-EVIDENCE",
    )
    quote = "Redis를 세션 캐시 저장소로 사용하기로"
    evidence = {
        "segmentId": "s1",
        "quote": quote,
        "sourceMeetingId": "M-UNATTACHED-EVIDENCE",
    }

    result = edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="editor",
        expected_version=1,
        evidence=[evidence, evidence],
    )

    assert result.analysis_invalidated is True
    assert len(result.node.evidence) == 1
    assert result.node.evidence[0].quote == quote
    with session_factory() as session:
        assert session.query(NodeEvidence).filter_by(
            node_id=uuid.UUID(node_id)
        ).count() == 1


def test_edit_unattached_node_rejects_invalid_evidence_without_partial_change(
    session_factory,
):
    node_id, _, original_quote = _initial_node(
        session_factory,
        meeting_id="M-UNATTACHED-INVALID-EVIDENCE",
    )

    with pytest.raises(NodeValidationError, match="quote not in"):
        edit_unattached_node(
            session_factory,
            node_id,
            project_id="proj-01",
            actor_id="editor",
            expected_version=1,
            title="롤백되어야 하는 제목",
            evidence=[
                {
                    "segmentId": "s1",
                    "quote": "원문에 존재하지 않는 완전히 잘못된 근거 문장입니다.",
                }
            ],
        )

    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        assert node.title == "Redis 캐시 결정"
        assert node.version == 1
        assert node.analysis_status == "PENDING"
        assert [row.quote for row in node.evidence] == [original_quote]


def test_edit_unattached_node_rejects_active_node(session_factory):
    with session_scope(session_factory) as session:
        active = seed_node(
            session,
            project_id="proj-01",
            source_meeting_id="M-ACTIVE",
            source_item_id="d1",
            node_type="DECISION",
            category="BACKEND",
            title="이미 확정된 Node",
        )
        node_id = str(active.id)

    with pytest.raises(NodeStateError):
        edit_unattached_node(
            session_factory,
            node_id,
            project_id="proj-01",
            actor_id="editor",
            expected_version=1,
            title="수정 불가",
        )


def test_edit_unattached_node_type_change_marks_analysis_stale(session_factory):
    node_id, _, _ = _initial_node(
        session_factory,
        meeting_id="M-UNATTACHED-TYPE",
    )

    result = edit_unattached_node(
        session_factory,
        node_id,
        project_id="proj-01",
        actor_id="editor",
        expected_version=1,
        node_type="ACTION",
    )

    assert result.node.node_type.value == "ACTION"
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        assert node.analysis_status == "STALE"
