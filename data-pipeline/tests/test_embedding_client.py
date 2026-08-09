"""Real embedding adapter: response validation, retry and error classification."""

from __future__ import annotations

import json

import httpx
import pytest

from data_pipeline.retrieval.embedding_client import (
    EmbeddingClientSettings,
    EmbeddingResponseError,
    EmbeddingTransportError,
    GmsEmbeddingClient,
    build_embedding_client,
)
from data_pipeline.retrieval.errors import EmbeddingValidationError

DIM = 8


def _settings(**overrides) -> EmbeddingClientSettings:
    values = {
        "api_key": "test-key-not-a-real-secret",
        "base_url": "https://gateway.invalid/v1",
        "model": "text-embedding-3-small",
        "dimensions": DIM,
        "timeout_seconds": 5.0,
        "retry_count": 2,
        "retry_backoff_seconds": 0.0,
    }
    values.update(overrides)
    return EmbeddingClientSettings(**values)


def _client(handler, **overrides) -> GmsEmbeddingClient:
    return GmsEmbeddingClient(
        _settings(**overrides),
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )


def _ok(vector=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"embedding": vector or [0.1] * DIM}]}
        )

    return handler


def _embed(client) -> list[float]:
    return list(
        client.embed(text="hello", model="text-embedding-3-small", dimensions=DIM)
    )


def test_returns_a_validated_vector() -> None:
    assert _embed(_client(_ok())) == [0.1] * DIM


def test_detailed_result_preserves_provider_usage_without_raw_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "x-request-id": "request-123",
                "x-ratelimit-remaining-requests": "9",
            },
            json={
                "data": [{"embedding": [0.1] * DIM}],
                "usage": {
                    "prompt_tokens": 12,
                    "total_tokens": 12,
                    "credits": 3.5,
                },
            },
        )

    result = _client(handler).embed_detailed(
        text="hello",
        model="text-embedding-3-small",
        dimensions=DIM,
    )

    assert result.vector == [0.1] * DIM
    assert result.usage.input_tokens == 12
    assert result.usage.total_tokens == 12
    assert result.usage.credit == 3.5
    assert result.usage.source == "PROVIDER_REPORTED"
    assert result.request_id == "request-123"
    assert result.rate_limit == {"x-ratelimit-remaining-requests": "9"}
    assert result.retry_count == 0


def test_sends_bearer_auth_model_and_dimensions() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.5] * DIM}]})

    _embed(_client(handler))

    assert seen["auth"] == "Bearer test-key-not-a-real-secret"
    assert seen["url"] == "https://gateway.invalid/v1/embeddings"
    assert seen["body"]["model"] == "text-embedding-3-small"
    assert seen["body"]["dimensions"] == DIM


def test_rejects_a_wrong_dimension() -> None:
    with pytest.raises(EmbeddingValidationError) as excinfo:
        _embed(_client(_ok([0.1] * (DIM + 1))))
    assert "dimension mismatch" in str(excinfo.value)


def test_rejects_an_empty_response_array() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with pytest.raises(EmbeddingResponseError):
        _embed(_client(handler))


def test_rejects_a_missing_embedding_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0}]})

    with pytest.raises(EmbeddingResponseError):
        _embed(_client(handler))


def test_rejects_a_non_json_success_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with pytest.raises(EmbeddingResponseError):
        _embed(_client(handler))


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_rejects_nan_and_infinity(literal: str) -> None:
    """Strict JSON forbids these, but Python's decoder accepts them, so a lenient
    provider could hand us one. Build the body as raw bytes because httpx's own
    encoder refuses to emit them."""

    body = '{"data": [{"embedding": [%s, %s]}]}' % (
        literal,
        ", ".join(["0.1"] * (DIM - 1)),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    with pytest.raises(EmbeddingValidationError) as excinfo:
        _embed(_client(handler))
    assert "finite" in str(excinfo.value)


def test_rejects_a_zero_vector() -> None:
    with pytest.raises(EmbeddingValidationError):
        _embed(_client(_ok([0.0] * DIM)))


def test_rejects_non_numeric_values() -> None:
    with pytest.raises(EmbeddingValidationError):
        _embed(_client(_ok(["a"] * DIM)))


def test_rejects_blank_input_text() -> None:
    with pytest.raises(EmbeddingResponseError):
        _client(_ok()).embed(text="   ", model="m", dimensions=DIM)


def test_retries_a_retryable_status_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"data": [{"embedding": [0.2] * DIM}]})

    assert _embed(_client(handler)) == [0.2] * DIM
    assert calls["n"] == 2


def test_gives_up_after_the_retry_budget() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(EmbeddingTransportError):
        _embed(_client(handler, retry_count=2))
    assert calls["n"] == 3  # initial attempt + 2 retries


def test_does_not_retry_a_non_retryable_status() -> None:
    """A 401 will never fix itself; burning the retry budget only delays the error."""

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(EmbeddingTransportError) as excinfo:
        _embed(_client(handler))
    assert calls["n"] == 1
    assert "non-retryable" in str(excinfo.value)


def test_retries_a_transport_timeout() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("timed out")
        return httpx.Response(200, json={"data": [{"embedding": [0.3] * DIM}]})

    assert _embed(_client(handler)) == [0.3] * DIM


def test_a_persistent_timeout_is_a_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(EmbeddingTransportError):
        _embed(_client(handler))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_key": ""},
        {"base_url": ""},
        {"model": ""},
        {"dimensions": 0},
        {"timeout_seconds": 0},
        {"retry_count": -1},
    ],
)
def test_settings_validation_rejects_bad_configuration(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        _settings(**kwargs)


def test_factory_rejects_an_unknown_adapter(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_ADAPTER", "fake")
    with pytest.raises(ValueError) as excinfo:
        build_embedding_client()
    assert "EMBEDDING_ADAPTER" in str(excinfo.value)


def test_settings_never_expose_the_key_in_the_endpoint() -> None:
    settings = _settings()
    assert settings.api_key not in settings.endpoint
    assert settings.endpoint.endswith("/embeddings")
