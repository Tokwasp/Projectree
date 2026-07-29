"""M2 ①② 체인 오프라인 테스트 (FakeClient — LLM 결정론적 모사).

회의 내 전용 판정(UNATTACHED 포함)이 review candidate로 정확히 보존되는지 검증한다.
실제 GMS 호출은 scripts/run_m2_meeting.py / run_m2_regression.py 로 수행(크레딧 소비).
"""

from __future__ import annotations

import json
import uuid

from data_pipeline.llm import LLMResponse
from data_pipeline.pipeline import run_meeting
from data_pipeline.storage import Node, NodeCandidate

from .support import count


class FakeClient:
    """호출 순서대로 canned JSON 을 돌려주는 결정론적 클라이언트."""

    class _S:
        model = "fake-model"

    settings = _S()

    def __init__(self, responses: list[dict]):
        self._responses = [json.dumps(r, ensure_ascii=False) for r in responses]
        self.calls = 0

    def complete(self, messages):
        raw = self._responses[self.calls]
        self.calls += 1
        # 대략적 토큰 수(테스트용) — 크레딧 계산 경로도 함께 탄다.
        return LLMResponse(raw_response=raw, input_tokens=100, output_tokens=50,
                           total_tokens=150, latency_ms=1)


SEGMENTS = [
    {"segmentId": "seg-1", "startMs": 1000, "speakerLabel": "SPK_1",
     "text": "소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다."},
    {"segmentId": "seg-2", "startMs": 5000, "speakerLabel": "SPK_2",
     "text": "레디스 캐시 도입은 나중에 다시 논의해 봐야 할 것 같아요."},
]

EXTRACTION_OUT = {
    "meetingId": "M-CHAIN",
    "items": [
        {"id": "m1", "type": "DECISION", "predictedCategory": "BACKEND",
         "title": "소음 전처리 파이프라인 도입", "content": "STT 앞단 전처리.",
         "evidence": [{"segmentId": "seg-1", "quote": "소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다."}]},
        {"id": "m2", "type": "ISSUE", "predictedCategory": "BACKEND",
         "title": "레디스 캐시 도입 여부 미확정", "content": "도입 여부 보류.",
         "evidence": [{"segmentId": "seg-2", "quote": "레디스 캐시 도입은 나중에 다시 논의해 봐야 할 것 같아요."}]},
    ],
}

JUDGMENT_OUT = {
    "meetingId": "M-CHAIN",
    "judgments": [
        {"itemId": "m1", "result": "NEW_DECISION", "category": "BACKEND"},
        {"itemId": "m2", "result": "MINUTES_ONLY", "reason": "NO_RELATED_DECISION"},
    ],
}


def test_chain_persists_all_items_as_review_pending_candidates(session_factory, tmp_path):
    client = FakeClient([EXTRACTION_OUT, JUDGMENT_OUT])
    meeting_input = {"projectId": "proj-01", "externalMeetingId": "M-CHAIN", "segments": SEGMENTS}
    res = run_meeting(session_factory, meeting_input=meeting_input, client=client, output_dir=tmp_path)

    assert client.calls == 2  # ①, ②
    assert res.proposal_result.status == "REVIEW_PENDING"
    assert res.proposal_result.candidateCount == 2
    assert count(session_factory, Node) == 0

    with session_factory() as s:
        by_item = {row.source_item_id: row for row in s.query(NodeCandidate).all()}
        assert by_item["m1"].suggested_disposition == "NEW_DECISION"
        assert by_item["m2"].suggested_disposition == "UNATTACHED"
        assert all(row.review_status == "PENDING" for row in by_item.values())

    # lineage 에 프롬프트 sha 기록 + 아티팩트 파일 생성.
    assert res.lineage["extractionPromptSha256"] and res.lineage["judgmentPromptSha256"]
    assert res.lineage["extractionPromptName"] == "extraction-poc-v3-lts"
    assert res.lineage["judgmentPromptName"] == "judgment-poc-v4-lts"
    assert res.lineage["judgmentContractAdapterVersion"] == "poc-v4-to-server-v1"
    assert (res.output_dir / "extraction.json").is_file()
    assert (res.output_dir / "judgment.json").is_file()
    assert res.credits > 0


def test_chain_normalizes_duplicate_extraction_itemid_without_dropping(session_factory):
    ext = {"meetingId": "M-DUP", "items": [
        EXTRACTION_OUT["items"][0],
        {**EXTRACTION_OUT["items"][0]},  # 중복 id m1
    ]}
    jud = {"meetingId": "M-DUP", "judgments": [{"itemId": "m1", "result": "NEW_DECISION", "category": "BACKEND"}]}
    client = FakeClient([ext, jud])
    res = run_meeting(session_factory,
                      meeting_input={"projectId": "proj-01", "externalMeetingId": "M-DUP", "segments": SEGMENTS},
                      client=client)
    assert res.dropped_item_ids == []
    assert count(session_factory, NodeCandidate) == 2
    with session_factory() as session:
        rows = session.query(NodeCandidate).order_by(NodeCandidate.created_at).all()
        assert rows[0].source_item_id == "m1"
        assert rows[1].source_item_id.startswith("item-2-")
        assert rows[1].raw_item["id"] == "m1"
    assert count(session_factory, Node) == 0
