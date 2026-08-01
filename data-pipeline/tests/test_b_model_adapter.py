"""Real GMS B-model adapter: transport, retry classification, decision shape."""

from __future__ import annotations

import json

import httpx
import pytest

from data_pipeline.b_model.client import build_b_model_client
from data_pipeline.b_model.gms import (
    BModelClientSettings,
    BModelResponseError,
    BModelTransportError,
    GmsBModelClient,
    render_b_model_prompt,
)
from data_pipeline.contracts.dto import BModelDecision

SOURCE = {
    "nodeId": "11111111-1111-4111-8111-111111111111",
    "nodeVersion": 1,
    "nodeType": "DECISION",
    "category": "INFRA",
    "title": "회의 처리 서버는 EC2를 사용한다",
    "content": "회의 처리 서버는 EC2에서 운영한다.",
    "evidence": [],
}
TARGET_ID = "22222222-2222-4222-8222-222222222222"
CANDIDATES = [
    {
        "nodeId": TARGET_ID,
        "nodeVersion": 1,
        "nodeType": "DECISION",
        "category": "INFRA",
        "title": "회의 서버 EC2 운영 결정",
        "content": "회의 서버는 EC2로 운영한다.",
        "graphState": "ACTIVE",
        "rank": 1,
        "similarity": 0.91,
    }
]


def _settings(**overrides) -> BModelClientSettings:
    values = {
        "api_key": "test-key-not-a-real-secret",
        "base_url": "https://gateway.invalid/v1",
        "model": "gpt-test",
        "timeout_seconds": 5.0,
        "retry_count": 2,
        "retry_backoff_seconds": 0.0,
    }
    values.update(overrides)
    return BModelClientSettings(**values)


def _client(handler, **overrides) -> GmsBModelClient:
    return GmsBModelClient(
        _settings(**overrides),
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )


def _chat_response(decision: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(decision, ensure_ascii=False)}}]}


def _ok(decision: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response(decision))

    return handler


def _recommend(client):
    return client.recommend(
        source_node=SOURCE, retrieval_candidates=CANDIDATES, model="gpt-test"
    )


# ------------------------------------------------------------- happy paths ---


def test_create_new_decision_round_trips_and_validates() -> None:
    decision = {
        "recommendation": "CREATE_NEW",
        "targetNodeId": None,
        "relationType": None,
        "suggestedTitle": "독립 결정",
        "suggestedContent": "내용",
        "reason": "어떤 후보와도 다르다",
        "metadata": {},
    }
    raw = _recommend(_client(_ok(decision)))
    validated = BModelDecision.model_validate(raw)
    assert validated.recommendation.value == "CREATE_NEW"


def test_link_decision_round_trips() -> None:
    decision = {
        "recommendation": "LINK",
        "targetNodeId": TARGET_ID,
        "relationType": "ATTACHED_TO",
        "suggestedTitle": "연결",
        "suggestedContent": "내용",
        "reason": "상위 결정의 실행",
    }
    validated = BModelDecision.model_validate(_recommend(_client(_ok(decision))))
    assert validated.recommendation.value == "LINK"
    assert str(validated.targetNodeId) == TARGET_ID


def test_merge_decision_round_trips() -> None:
    decision = {
        "recommendation": "MERGE",
        "targetNodeId": TARGET_ID,
        "relationType": None,
        "suggestedTitle": "병합 제목",
        "suggestedContent": "병합 내용",
        "reason": "같은 결정의 다른 표현",
    }
    validated = BModelDecision.model_validate(_recommend(_client(_ok(decision))))
    assert validated.recommendation.value == "MERGE"


def test_request_carries_auth_model_and_json_mode() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_chat_response(
                {
                    "recommendation": "CREATE_NEW",
                    "suggestedTitle": "t",
                    "suggestedContent": "c",
                    "reason": "r",
                }
            ),
        )

    _recommend(_client(handler))
    assert seen["auth"] == "Bearer test-key-not-a-real-secret"
    assert seen["body"]["model"] == "gpt-test"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    # The rendered prompt contains both payloads.
    content = seen["body"]["messages"][0]["content"]
    assert SOURCE["title"] in content
    assert TARGET_ID in content


# ------------------------------------------------------- rejection paths ---


def test_target_outside_the_candidate_list_is_rejected() -> None:
    decision = {
        "recommendation": "MERGE",
        "targetNodeId": "99999999-9999-4999-8999-999999999999",
        "suggestedTitle": "t",
        "suggestedContent": "c",
        "reason": "r",
    }
    with pytest.raises(BModelResponseError) as excinfo:
        _recommend(_client(_ok(decision)))
    assert "outside the retrieval candidates" in str(excinfo.value)


def test_invalid_action_fails_downstream_validation() -> None:
    raw = _recommend(
        _client(
            _ok(
                {
                    "recommendation": "DELETE_EVERYTHING",
                    "suggestedTitle": "t",
                    "suggestedContent": "c",
                    "reason": "r",
                }
            )
        )
    )
    with pytest.raises(Exception):
        BModelDecision.model_validate(raw)


def test_malformed_message_json_is_a_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not json {"}}]}
        )

    with pytest.raises(BModelResponseError):
        _recommend(_client(handler))


def test_empty_choices_is_a_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(BModelResponseError):
        _recommend(_client(handler))


# ------------------------------------------------------------- transport ---


def test_retries_retryable_status_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(
            200,
            json=_chat_response(
                {
                    "recommendation": "CREATE_NEW",
                    "suggestedTitle": "t",
                    "suggestedContent": "c",
                    "reason": "r",
                }
            ),
        )

    assert _recommend(_client(handler))["recommendation"] == "CREATE_NEW"
    assert calls["n"] == 2


def test_gives_up_after_retry_budget_on_429() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(BModelTransportError):
        _recommend(_client(handler, retry_count=2))
    assert calls["n"] == 3


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_are_not_retried(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, json={"error": "denied"})

    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))
    assert calls["n"] == 1
    assert "non-retryable" in str(excinfo.value)


def test_timeout_is_retried_then_fails_as_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(BModelTransportError):
        _recommend(_client(handler))


# --------------------------------------------------------------- settings ---


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_key": ""},
        {"base_url": ""},
        {"model": ""},
        {"timeout_seconds": 0},
        {"retry_count": -1},
    ],
)
def test_settings_validation(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        _settings(**kwargs)


def test_settings_repr_never_contains_the_key() -> None:
    settings = _settings()
    assert "test-key-not-a-real-secret" not in repr(settings)


def test_factory_selects_gms_and_rejects_unknown(monkeypatch) -> None:
    monkeypatch.setenv("B_MODEL_ADAPTER", "gms")
    monkeypatch.setenv("GMS_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gw.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    client = build_b_model_client()
    assert isinstance(client, GmsBModelClient)

    monkeypatch.setenv("B_MODEL_ADAPTER", "banana")
    with pytest.raises(RuntimeError):
        build_b_model_client()

    monkeypatch.setenv("B_MODEL_ADAPTER", "")
    with pytest.raises(RuntimeError) as excinfo:
        build_b_model_client()
    assert "B_MODEL_ADAPTER" in str(excinfo.value)
    assert not isinstance(excinfo.value, NotImplementedError)


def test_prompt_contains_conservative_merge_and_hint_rules() -> None:
    text = render_b_model_prompt(source_node=SOURCE, retrieval_candidates=CANDIDATES)
    assert "sameMeetingSuggestedParent" in text
    assert "MERGE는 보수적으로" in text
    assert "회의 STT" not in text  # b prompt is not the extraction prompt
