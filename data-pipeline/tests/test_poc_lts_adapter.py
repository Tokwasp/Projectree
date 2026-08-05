from __future__ import annotations

import json

from data_pipeline.adapters import PocJudgmentResult, PocV4JudgmentContractAdapter
from data_pipeline.llm import LLMResponse
from data_pipeline.pipeline import run_judgment_only, run_meeting
from data_pipeline.prompts import get_prompt_profile, render_judgment_prompt
from data_pipeline.storage import Node, NodeCandidate

from .support import count


class FakeClient:
    class _S:
        model = "fake-model"

    settings = _S()

    def __init__(self, responses: list[dict]):
        self._responses = [json.dumps(value, ensure_ascii=False) for value in responses]
        self.calls = 0
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages):
        self.messages.append(messages)
        raw = self._responses[self.calls]
        self.calls += 1
        return LLMResponse(
            raw_response=raw,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=1,
        )


ITEMS = [
    {
        "id": "m1",
        "type": "DECISION",
        "predictedCategory": "BACKEND",
        "title": "JWT 적용 검토",
        "content": "JWT 적용 여부를 검토함.",
        "evidence": [{"segmentId": "seg-1", "quote": "JWT 적용은 더 검토해 봅시다."}],
    },
    {
        "id": "m2",
        "type": "ACTION",
        "predictedCategory": "BACKEND",
        "title": "JWT 문서 조사",
        "content": "JWT 문서를 조사함.",
        "evidence": [{"segmentId": "seg-2", "quote": "관련 문서는 제가 조사할게요."}],
    },
    {
        "id": "m3",
        "type": "ISSUE",
        "predictedCategory": "BACKEND",
        "title": "토큰 폐기 정책 미정",
        "content": "토큰 폐기 정책이 필요함.",
        "evidence": [{"segmentId": "seg-3", "quote": "토큰 폐기 정책은 아직 없어요."}],
    },
]

SEGMENTS = [
    {"segmentId": "seg-1", "startMs": 1000, "text": "JWT 적용은 더 검토해 봅시다."},
    {"segmentId": "seg-2", "startMs": 2000, "text": "관련 문서는 제가 조사할게요."},
    {"segmentId": "seg-3", "startMs": 3000, "text": "토큰 폐기 정책은 아직 없어요."},
]


def test_poc_llm_enum_does_not_contain_unattached():
    assert {value.value for value in PocJudgmentResult} == {
        "NEW_DECISION",
        "ATTACH",
        "UPDATE_ACTION",
        "MINUTES_ONLY",
    }


def test_poc_adapter_derives_unattached_only_for_no_related_action_or_issue():
    adapter = PocV4JudgmentContractAdapter()
    raw = [
        {"itemId": "m1", "result": "MINUTES_ONLY", "reason": "NO_RELATED_DECISION"},
        {"itemId": "m2", "result": "MINUTES_ONLY", "reason": "NO_RELATED_DECISION"},
        {"itemId": "m3", "result": "MINUTES_ONLY", "reason": "NOT_CONFIRMED"},
    ]
    adapted = adapter.adapt(items=ITEMS, judgments=raw)

    assert adapted == [
        {"itemId": "m1", "result": "MINUTES_ONLY", "reason": "NO_RELATED_DECISION"},
        {"itemId": "m2", "result": "UNATTACHED", "reason": "NO_RELATED_DECISION"},
        {"itemId": "m3", "result": "MINUTES_ONLY", "reason": "NOT_CONFIRMED"},
    ]


def test_poc_adapter_keeps_low_confidence_minutes_only_and_normalizes_unknown_reason():
    adapter = PocV4JudgmentContractAdapter()
    raw = [
        {"itemId": "m2", "result": "MINUTES_ONLY", "reason": "LOW_CONFIDENCE"},
        {"itemId": "m3", "result": "MINUTES_ONLY", "reason": "SOMETHING_NEW"},
    ]
    assert adapter.adapt(items=ITEMS, judgments=raw) == [
        {"itemId": "m2", "result": "MINUTES_ONLY", "reason": "LOW_CONFIDENCE"},
        {"itemId": "m3", "result": "MINUTES_ONLY", "reason": "LOW_CONFIDENCE"},
    ]


def test_poc_lts_renderer_includes_candidate_list_without_rewriting_asset():
    prompt = render_judgment_prompt(
        "poc-v4-lts",
        items=ITEMS,
        candidates={"decisions": [{"decisionId": "dec_1", "title": "JWT 사용"}]},
        segments=SEGMENTS,
    )
    assert '"decisionId": "dec_1"' in prompt
    assert "{{CANDIDATES_JSON}}" not in prompt
    assert "UNATTACHED" not in prompt
    assert get_prompt_profile("poc-v4-lts").judgment_asset.sha256 == (
        "258e5b42b74f2f1a25960e9eaf4f15d5894f77e48088b6938eaaf481d4f1c352"
    )


def test_judgment_only_profiles_share_fixed_items_and_apply_different_adapters():
    current_client = FakeClient([
        {"meetingId": "M", "judgments": [{"itemId": "m2", "result": "UNATTACHED", "reason": "NO_RELATED_DECISION"}]}
    ])
    lts_client = FakeClient([
        {"meetingId": "M", "judgments": [{"itemId": "m2", "result": "MINUTES_ONLY", "reason": "NO_RELATED_DECISION"}]}
    ])
    current = run_judgment_only(
        client=current_client,
        items=[ITEMS[1]],
        segments=SEGMENTS,
        prompt_profile="m2-current",
    )
    lts = run_judgment_only(
        client=lts_client,
        items=[ITEMS[1]],
        segments=SEGMENTS,
        prompt_profile="poc-v4-lts",
    )
    assert current.adapted_judgments == lts.adapted_judgments
    assert current.adapter_version == "identity-v1"
    assert lts.adapter_version == "poc-v4-to-server-v1"
    assert current.profile_name == "m2-current-candidate"
    assert lts.profile_name == "poc-lts"


def test_poc_lts_meeting_persists_every_item_for_review(session_factory):
    extraction = {"meetingId": "M-LTS", "items": ITEMS}
    judgment = {
        "meetingId": "M-LTS",
        "judgments": [
            {"itemId": "m1", "result": "MINUTES_ONLY", "reason": "NOT_CONFIRMED"},
            {"itemId": "m2", "result": "MINUTES_ONLY", "reason": "NO_RELATED_DECISION"},
            {"itemId": "m3", "result": "MINUTES_ONLY", "reason": "LOW_CONFIDENCE"},
        ],
    }
    client = FakeClient([extraction, judgment])
    result = run_meeting(
        session_factory,
        meeting_input={"projectId": "proj-01", "externalMeetingId": "M-LTS", "segments": SEGMENTS},
        client=client,
        prompt_profile="poc-v4-lts",
    )

    assert result.proposal_result.status == "REVIEW_PENDING"
    assert result.proposal_result.candidateCount == 3
    assert result.prompt_profile == "poc-lts"
    assert result.lineage["judgmentPromptName"] == "judgment-poc-v4-lts"
    assert result.lineage["judgmentContractAdapterVersion"] == "poc-v4-to-server-v1"
    assert count(session_factory, Node) == 0
    with session_factory() as session:
        by_item = {row.source_item_id: row for row in session.query(NodeCandidate).all()}
        assert by_item["m1"].suggested_disposition == "MINUTES_ONLY"
        assert by_item["m2"].suggested_disposition == "UNATTACHED"
        assert by_item["m3"].suggested_disposition == "MINUTES_ONLY"


def test_default_generation_runs_complete_poc_pair_without_database():
    from data_pipeline.pipeline import run_generation_only

    extraction = {"meetingId": "M-PAIR", "items": [ITEMS[1]]}
    judgment = {
        "meetingId": "M-PAIR",
        "judgments": [
            {"itemId": "m2", "result": "MINUTES_ONLY", "reason": "NO_RELATED_DECISION"}
        ],
    }
    client = FakeClient([extraction, judgment])
    run = run_generation_only(
        meeting_input={
            "projectId": "proj-01",
            "externalMeetingId": "M-PAIR",
            "segments": SEGMENTS,
        },
        client=client,
    )

    assert run.profile_name == "poc-lts"
    assert run.adapter_version == "poc-v4-to-server-v1"
    assert run.judgments == [
        {"itemId": "m2", "result": "UNATTACHED", "reason": "NO_RELATED_DECISION"}
    ]
    assert "당신의 역할은 **기록**이다" in run.extraction_prompt
    assert "잘못된 반영이 누락보다 나쁘다" in run.judgment_prompt
    assert "UNATTACHED" not in run.judgment_prompt


def test_candidate_generation_requires_explicit_profile_selection():
    from data_pipeline.pipeline import run_generation_only

    extraction = {"meetingId": "M-CAND", "items": [ITEMS[1]]}
    judgment = {
        "meetingId": "M-CAND",
        "judgments": [
            {"itemId": "m2", "result": "UNATTACHED", "reason": "NO_RELATED_DECISION"}
        ],
    }
    client = FakeClient([extraction, judgment])
    run = run_generation_only(
        meeting_input={
            "projectId": "proj-01",
            "externalMeetingId": "M-CAND",
            "segments": SEGMENTS,
        },
        client=client,
        prompt_profile="m2-current-candidate",
    )

    assert run.profile_name == "m2-current-candidate"
    assert run.adapter_version == "identity-v1"
    assert "최대 40개" in run.extraction_prompt
    assert "UNATTACHED" in run.judgment_prompt
