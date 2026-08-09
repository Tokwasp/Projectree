"""Provider-model contract and error preservation for the GMS B-model adapter.

Regression suite for the production incident where embeddings returned 200 but
every B-model call returned HTTP 400: the internal execution label
``automatic-b-model`` was passed as the request body's ``model`` field, and the
400 response body was discarded so nothing in the logs or the database said so.
"""

from __future__ import annotations

import json

import httpx
import pytest

from data_pipeline.b_model.failures import (
    FAILURE_HTTP_ERROR,
    FAILURE_INVALID_RESPONSE,
    FAILURE_TIMEOUT,
    FAILURE_TRANSPORT_ERROR,
    FAILURE_UNCLASSIFIED,
    FAILURE_VALIDATION_ERROR,
    MAX_PROVIDER_MESSAGE_CHARS,
    describe_b_model_failure,
)
from data_pipeline.b_model.gms import (
    BModelClientSettings,
    BModelResponseError,
    BModelTransportError,
    GmsBModelClient,
    load_b_model_client_settings,
    resolve_provider_model,
)
from data_pipeline.contracts.dto import BModelDecision

API_KEY = "test-key-not-a-real-secret"
SOURCE = {
    "nodeId": "11111111-1111-4111-8111-111111111111",
    "nodeVersion": 1,
    "nodeType": "DECISION",
    "category": "INFRA",
    "title": "회의 처리 서버는 EC2를 사용한다",
    "content": "회의 처리 서버는 EC2에서 운영한다.",
    "evidence": [],
}
CANDIDATES: list[dict] = []

#: Strings that name a pipeline or a contract version - never a provider model.
INTERNAL_LABELS = (
    "automatic-b-model",
    "b-model",
    "configured-b-model",
    "fake-b-model",
    "automatic-v1",
    "retrieval-v1",
    "v1",
)

#: A markdown-fenced answer - the routine LLM regression when a model changes.
FENCED_CONTENT = "```json\n{oops"

DECISION = {
    "recommendation": "CREATE_NEW",
    "targetNodeId": None,
    "relationType": None,
    "suggestedTitle": "제목",
    "suggestedContent": "내용",
    "reason": "독립 노드",
    "metadata": {},
}


def _client(handler, **overrides) -> GmsBModelClient:
    values = {
        "api_key": API_KEY,
        "base_url": "https://gateway.invalid/v1",
        "model": "gpt-5.2",
        "timeout_seconds": 5.0,
        "retry_count": 0,
        "retry_backoff_seconds": 0.0,
    }
    values.update(overrides)
    return GmsBModelClient(
        BModelClientSettings(**values),
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )


def _chat_body(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _ok(handler_body: dict | None = None):
    payload = _chat_body(json.dumps(handler_body or DECISION, ensure_ascii=False))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


def _fails(status: int, **response_kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, **response_kwargs)

    return handler


def _recommend(client):
    return client.recommend(source_node=SOURCE, retrieval_candidates=CANDIDATES)


# ------------------------------------------------ A/B: provider model source ---


def test_provider_model_falls_back_from_b_model_name_to_openai_model(
    monkeypatch,
) -> None:
    monkeypatch.delenv("B_MODEL_NAME", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.2")
    assert resolve_provider_model() == "gpt-5.2"


def test_b_model_name_overrides_openai_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.2")
    monkeypatch.setenv("B_MODEL_NAME", "gpt-5.2-mini")
    assert resolve_provider_model() == "gpt-5.2-mini"


def test_blank_b_model_name_still_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.2")
    monkeypatch.setenv("B_MODEL_NAME", "   ")
    assert resolve_provider_model() == "gpt-5.2"


def test_settings_loader_resolves_the_provider_model(monkeypatch) -> None:
    monkeypatch.delenv("B_MODEL_NAME", raising=False)
    monkeypatch.delenv("B_MODEL_TEMPERATURE", raising=False)
    monkeypatch.setenv("GMS_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.2")

    settings = load_b_model_client_settings()

    assert settings.model == "gpt-5.2"
    assert settings.endpoint == "https://gateway.invalid/v1/chat/completions"


# ------------------------------------------------- A/C: what reaches the wire ---


def _sent_body(**overrides) -> dict:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json=_chat_body(json.dumps(DECISION, ensure_ascii=False))
        )

    _recommend(_client(handler, **overrides))
    return seen["body"]


def test_request_model_is_the_configured_provider_model() -> None:
    assert _sent_body()["model"] == "gpt-5.2"


def test_request_model_is_never_an_internal_label() -> None:
    assert _sent_body()["model"] not in INTERNAL_LABELS


def test_recommend_rejects_a_per_call_model_override() -> None:
    """The wire model is client configuration, not a caller argument.

    The previous signature accepted ``model=`` and every call site passed an
    execution label into it. Keeping this a TypeError makes the regression
    impossible to reintroduce silently.
    """

    with pytest.raises(TypeError):
        _client(_ok()).recommend(
            source_node=SOURCE,
            retrieval_candidates=CANDIDATES,
            model="automatic-b-model",
        )


def test_provider_model_property_exposes_the_configured_model() -> None:
    assert _client(_ok()).provider_model == "gpt-5.2"


def test_request_still_uses_json_object_mode_and_bearer_auth() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json=_chat_body(json.dumps(DECISION, ensure_ascii=False))
        )

    _recommend(_client(handler))
    assert seen["auth"] == f"Bearer {API_KEY}"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert set(seen["body"]) <= {
        "model",
        "messages",
        "response_format",
        "temperature",
    }


# ---------------------------------------------------- D: HTTP 400 diagnostics ---


def test_http_400_preserves_status_model_endpoint_and_provider_message() -> None:
    handler = _fails(
        400,
        json={"error": {"message": "invalid model", "code": "model_not_found"}},
    )
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))

    error = excinfo.value
    assert error.status_code == 400
    assert error.failure_code == FAILURE_HTTP_ERROR
    assert error.provider_message == "invalid model"
    rendered = str(error)
    assert "status=400" in rendered
    assert "model=gpt-5.2" in rendered
    assert "/chat/completions" in rendered
    assert "invalid model" in rendered


def test_http_error_never_leaks_the_api_key_or_auth_header() -> None:
    handler = _fails(400, json={"error": {"message": "invalid model"}})
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))
    rendered = f"{excinfo.value}|{excinfo.value.provider_message}"
    assert API_KEY not in rendered
    assert "Authorization" not in rendered
    assert "Bearer" not in rendered


def test_http_error_never_leaks_the_rendered_prompt() -> None:
    handler = _fails(400, json={"error": {"message": "invalid model"}})
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))
    assert SOURCE["content"] not in str(excinfo.value)


def test_http_400_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "invalid model"}})

    with pytest.raises(BModelTransportError):
        _recommend(_client(handler, retry_count=2))
    assert calls["n"] == 1


def test_request_id_header_is_kept_when_the_provider_sends_one() -> None:
    handler = _fails(
        400,
        json={"error": {"message": "invalid model"}},
        headers={"x-request-id": "req-123"},
    )
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))
    assert "request_id=req-123" in str(excinfo.value)


def test_non_json_error_body_is_captured_flattened_and_capped() -> None:
    handler = _fails(400, text="<html>\n\n" + ("x" * 4000) + "\n</html>")
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))

    provider_message = excinfo.value.provider_message
    assert provider_message
    assert "\n" not in provider_message
    assert provider_message.endswith("...(truncated)")
    assert len(provider_message) <= MAX_PROVIDER_MESSAGE_CHARS + len(
        "...(truncated)"
    )


def test_flat_message_and_detail_bodies_are_understood() -> None:
    for body, expected in (
        ({"message": "flat message"}, "flat message"),
        ({"detail": "fastapi style"}, "fastapi style"),
        ({"error": "string error"}, "string error"),
    ):
        with pytest.raises(BModelTransportError) as excinfo:
            _recommend(_client(_fails(400, json=body)))
        assert excinfo.value.provider_message == expected


# ------------------------------------------------ E: retry policy is preserved ---


def test_429_is_retried_then_reports_the_last_provider_message() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler, retry_count=2))
    assert calls["n"] == 3
    assert excinfo.value.status_code == 429
    assert "rate limited" in str(excinfo.value)


def test_500_is_retried_then_reports_the_last_provider_message() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": {"message": "upstream boom"}})

    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler, retry_count=1))
    assert calls["n"] == 2
    assert "upstream boom" in str(excinfo.value)


def test_retryable_status_that_later_succeeds_returns_the_decision() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": {"message": "warming up"}})
        return httpx.Response(
            200, json=_chat_body(json.dumps(DECISION, ensure_ascii=False))
        )

    decision = _recommend(_client(handler, retry_count=2))
    assert calls["n"] == 2
    assert decision["recommendation"] == "CREATE_NEW"


# --------------------------------------------- F/G: failure classification ---


def test_timeout_is_classified_as_a_timeout_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))
    code, message = describe_b_model_failure(excinfo.value)
    assert code == FAILURE_TIMEOUT
    assert "BModelTransportError" in message


def test_connection_error_is_classified_as_a_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))
    assert describe_b_model_failure(excinfo.value)[0] == FAILURE_TRANSPORT_ERROR


def test_http_failure_is_classified_apart_from_transport() -> None:
    handler = _fails(400, json={"error": {"message": "invalid model"}})
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler))
    assert describe_b_model_failure(excinfo.value)[0] == FAILURE_HTTP_ERROR


def test_unparseable_decision_is_classified_as_an_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_body("not json at all"))

    with pytest.raises(BModelResponseError) as excinfo:
        _recommend(_client(handler))
    assert describe_b_model_failure(excinfo.value)[0] == FAILURE_INVALID_RESPONSE


def test_contract_violation_is_classified_as_a_validation_failure() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        BModelDecision.model_validate({"recommendation": "CREATE_NEW"})
    assert describe_b_model_failure(excinfo.value)[0] == FAILURE_VALIDATION_ERROR


def test_failure_message_is_length_capped() -> None:
    class _Noisy(RuntimeError):
        pass

    _, message = describe_b_model_failure(_Noisy("y" * 5000))
    assert len(message) <= MAX_PROVIDER_MESSAGE_CHARS + len("...(truncated)")


# ------------------------------------- redaction and truncation guarantees ---


def test_a_provider_message_echoing_a_credential_is_redacted() -> None:
    """Provider error bodies are arbitrary remote text and can echo a request."""

    leaked = f"upstream rejected header Authorization: Bearer {API_KEY}"
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(_fails(400, json={"error": {"message": leaked}})))

    rendered = f"{excinfo.value}|{excinfo.value.provider_message}"
    assert API_KEY not in rendered
    assert "[REDACTED]" in rendered


def test_an_openai_style_key_in_the_body_is_redacted() -> None:
    body = {"error": {"message": "bad key sk-abcdef0123456789ABCDEF"}}
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(_fails(400, json=body)))
    assert "sk-abcdef0123456789ABCDEF" not in str(excinfo.value)


def test_provider_message_survives_the_persistence_boundary_untruncated() -> None:
    """describe_b_model_failure must not re-truncate an already-capped body.

    The incident was "the 400 body was discarded"; capping the composed string
    a second time would discard a long HTML body all over again.
    """

    marker = "ERROR: model gpt-5.2 does not exist"
    html = "<html><head><title>400</title><style>" + ("a" * 600) + "</style>"
    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(_fails(400, text=html + marker + "</html>")))

    _, message = describe_b_model_failure(excinfo.value)
    # The head of the body is capped, but the cap is applied once - the
    # composed message keeps everything the adapter chose to preserve.
    assert excinfo.value.provider_message in message
    assert "status=400" in message
    assert "model=gpt-5.2" in message


# ------------------------------------------- heterogeneous retry sequences ---


def test_a_429_then_a_connection_reset_still_reports_the_429() -> None:
    """The provider's own answer outranks a later contentless transport error."""

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429, json={"error": {"message": "org quota exhausted"}}
            )
        raise httpx.ConnectError("reset")

    with pytest.raises(BModelTransportError) as excinfo:
        _recommend(_client(handler, retry_count=1))

    assert calls["n"] == 2
    assert excinfo.value.status_code == 429
    assert excinfo.value.failure_code == FAILURE_HTTP_ERROR
    assert "org quota exhausted" in str(excinfo.value)


# ---------------------------------------------- unclassified vs. transport ---


def test_a_local_error_is_not_diagnosed_as_a_network_failure() -> None:
    """A bug in our own code must not send an operator to the network."""

    code, message = describe_b_model_failure(AttributeError("no such field"))
    assert code == FAILURE_UNCLASSIFIED
    assert code != FAILURE_TRANSPORT_ERROR
    assert "no such field" in message


def test_unparseable_content_keeps_a_bounded_snippet() -> None:
    """Distinguish a markdown fence from a refusal from a truncated answer."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_body(FENCED_CONTENT))

    with pytest.raises(BModelResponseError) as excinfo:
        _recommend(_client(handler))
    assert "```json" in str(excinfo.value)
