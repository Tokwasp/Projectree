from __future__ import annotations

import copy
import json

from data_pipeline.contracts import Lineage
from data_pipeline.llm import LLMResponse
from data_pipeline.pipeline import persist_generation_candidates, run_meeting
from data_pipeline.storage import (
    GraphChangeEvent,
    Meeting,
    Node,
    NodeCandidate,
    NodeCandidateEvidence,
    NodeEvidence,
    Relation,
    Request,
)

from .support import count, ev, item, judgment, request_payload, seg


SEGMENTS = [
    seg("s1", "JWT를 인증 방식으로 최종 채택하기로 결정했습니다.", 1000),
    seg("s2", "인증 미들웨어 구현은 민수가 맡아서 진행합니다.", 2000),
    seg("s3", "로그 정리 작업도 다음 회의 전까지 진행하겠습니다.", 3000),
    seg("s4", "캐시 정책은 아직 확정하지 않고 회의록에만 남깁니다.", 4000),
]
ITEMS = [
    item("m1", "DECISION", "JWT 인증 채택", "JWT를 인증 방식으로 채택.", [ev("s1", SEGMENTS[0]["text"])]),
    item("m2", "ACTION", "인증 미들웨어 구현", "미들웨어를 구현.", [ev("s2", SEGMENTS[1]["text"])]),
    item("m3", "ACTION", "로그 정리", "로그를 정리.", [ev("s3", SEGMENTS[2]["text"])]),
    item("m4", "ISSUE", "캐시 정책 미확정", "정책이 아직 미확정.", [ev("s4", SEGMENTS[3]["text"])]),
]
JUDGMENTS = [
    judgment("m1", "NEW_DECISION", category="BACKEND"),
    judgment("m2", "ATTACH", attachTo="m1"),
    judgment("m3", "UNATTACHED", reason="NO_RELATED_DECISION"),
    judgment("m4", "MINUTES_ONLY", reason="NOT_CONFIRMED"),
]


def _payload(meeting_id: str = "M-PROPOSED") -> dict:
    return request_payload(
        meeting_id=meeting_id,
        segments=copy.deepcopy(SEGMENTS),
        items=copy.deepcopy(ITEMS),
        judgments=copy.deepcopy(JUDGMENTS),
    )


def _persist(session_factory, payload: dict):
    return persist_generation_candidates(
        session_factory,
        payload,
        raw_extraction={"meetingId": payload["externalMeetingId"], "items": payload["items"]},
        raw_judgment={"meetingId": payload["externalMeetingId"], "judgments": payload["judgments"]},
        lineage=Lineage(generatedBy="AI", extractionPromptSha256="frozen-extraction"),
        usage={
            "inputTokens": 10,
            "outputTokens": 20,
            "totalTokens": 30,
            "credits": 2.0,
            "extractionLatencyMs": 11,
            "judgmentLatencyMs": 12,
        },
    )


def test_persists_all_dispositions_raw_values_evidence_and_same_meeting_parent(session_factory):
    result = _persist(session_factory, _payload())

    assert result.status == "REVIEW_PENDING"
    assert result.candidateCount == 4
    assert result.suggestedDispositionCounts == {
        "NEW_DECISION": 1,
        "ATTACH": 1,
        "UNATTACHED": 1,
        "MINUTES_ONLY": 1,
    }
    with session_factory() as session:
        rows = session.query(NodeCandidate).order_by(NodeCandidate.source_item_id).all()
        by_item = {row.source_item_id: row for row in rows}
        assert set(by_item) == {"m1", "m2", "m3", "m4"}
        assert by_item["m2"].suggested_parent_candidate_id == by_item["m1"].id
        assert by_item["m2"].suggested_parent_node_id is None
        assert by_item["m4"].suggested_disposition == "MINUTES_ONLY"
        assert by_item["m1"].raw_item == ITEMS[0]
        assert by_item["m1"].raw_judgment == JUDGMENTS[0]
        evidence = session.query(NodeCandidateEvidence).filter_by(
            candidate_id=by_item["m1"].id
        ).one()
        assert evidence.quote == SEGMENTS[0]["text"]
        assert evidence.quote_start == 0
        assert evidence.quote_end == len(SEGMENTS[0]["text"])

        request = session.query(Request).one()
        meeting = session.query(Meeting).one()
        assert request.status == meeting.status == "REVIEW_PENDING"
        assert request.raw_extraction["items"] == ITEMS
        assert request.raw_judgment["judgments"] == JUDGMENTS
        assert request.lineage["extractionPromptSha256"] == "frozen-extraction"
        assert request.usage["totalTokens"] == 30
        assert request.completed_at is not None


def test_validation_demotion_changes_suggestion_but_preserves_raw_judgment(session_factory):
    payload = _payload("M-DEMOTED")
    payload["items"] = [copy.deepcopy(ITEMS[0])]
    payload["items"][0]["evidence"][0]["quote"] = "짧음"
    payload["judgments"] = [copy.deepcopy(JUDGMENTS[0])]

    result = _persist(session_factory, payload)

    assert result.demoted[0]["rule"] == "EVIDENCE_INVALID"
    with session_factory() as session:
        candidate = session.query(NodeCandidate).one()
        assert candidate.suggested_disposition == "MINUTES_ONLY"
        assert candidate.raw_judgment["result"] == "NEW_DECISION"


def test_direct_candidate_persistence_is_idempotent_and_allows_new_material_input(session_factory):
    payload = _payload("M-IDEMPOTENT")
    first = _persist(session_factory, payload)
    duplicate = _persist(session_factory, copy.deepcopy(payload))
    assert first.status == "REVIEW_PENDING"
    assert duplicate.status == "REVIEW_PENDING"
    assert duplicate.outcome == "DUPLICATE_REVIEW_PENDING"
    assert duplicate.candidateIds == first.candidateIds
    assert count(session_factory, NodeCandidate) == 4

    changed = copy.deepcopy(payload)
    changed["items"][0]["title"] = "다른 제목"
    regenerated = _persist(session_factory, changed)
    assert regenerated.outcome == "NEWLY_CREATED_REVIEW_PENDING"
    assert count(session_factory, NodeCandidate) == 8


class FakeClient:
    class _Settings:
        model = "fake-model"

    settings = _Settings()

    def __init__(self):
        self.responses = [
            json.dumps({"meetingId": "M-SAFE", "items": ITEMS}, ensure_ascii=False),
            json.dumps({"meetingId": "M-SAFE", "judgments": JUDGMENTS}, ensure_ascii=False),
        ]

    def complete(self, messages):
        return LLMResponse(
            raw_response=self.responses.pop(0),
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            latency_ms=1,
        )


def test_default_run_meeting_never_mutates_confirmed_graph_before_review(session_factory):
    result = run_meeting(
        session_factory,
        meeting_input={
            "projectId": "proj-01",
            "externalMeetingId": "M-SAFE",
            "segments": SEGMENTS,
        },
        client=FakeClient(),
    )

    assert result.proposal_result.status == "REVIEW_PENDING"
    assert result.proposal_result.candidateCount == 4
    assert count(session_factory, NodeCandidate) == 4
    assert count(session_factory, Node) == 0
    assert count(session_factory, NodeEvidence) == 0
    assert count(session_factory, Relation) == 0
    assert count(session_factory, GraphChangeEvent) == 0
