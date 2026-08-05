from __future__ import annotations

import pytest

from data_pipeline.b_model.gms import BModelClientSettings, GmsBModelClient
from data_pipeline.llm import LLMSettings, OpenAIChatClient
from data_pipeline.provider_safety import (
    ExternalAIProviderBlockedError,
    assert_external_ai_client_allowed,
    gms_fatal_smoke_scope,
)
from data_pipeline.retrieval.embedding_client import (
    EmbeddingClientSettings,
    GmsEmbeddingClient,
)


def test_real_llm_client_creation_is_blocked_before_sdk_construction():
    with pytest.raises(ExternalAIProviderBlockedError):
        OpenAIChatClient(
            LLMSettings(
                gms_key="fixture-key",
                openai_base_url="https://provider.invalid/v1",
                model="fixture-model",
            )
        )


def test_real_embedding_transport_is_blocked_before_http():
    client = GmsEmbeddingClient(
        EmbeddingClientSettings(
            api_key="fixture-key",
            base_url="https://provider.invalid/v1",
            model="fixture-embedding",
            dimensions=3,
            retry_count=0,
        )
    )
    with pytest.raises(ExternalAIProviderBlockedError):
        client.embed(text="fixture input", model="fixture-embedding", dimensions=3)


def test_real_b_model_transport_is_blocked_before_http():
    client = GmsBModelClient(
        BModelClientSettings(
            api_key="fixture-key",
            base_url="https://provider.invalid/v1",
            model="fixture-model",
            retry_count=0,
        )
    )
    with pytest.raises(ExternalAIProviderBlockedError):
        client.recommend(
            source_node={
                "nodeId": "source",
                "nodeVersion": 1,
                "nodeType": "DECISION",
                "category": "BACKEND",
                "title": "fixture",
                "content": "fixture",
                "evidence": [],
            },
            retrieval_candidates=[],
            model="fixture-model",
        )


def test_fatal_smoke_flags_alone_do_not_open_provider_boundary(monkeypatch):
    monkeypatch.setenv("NO_EXTERNAL_AI_CALLS", "1")
    monkeypatch.setenv("ALLOW_GMS_FATAL_SMOKE", "1")

    with pytest.raises(ExternalAIProviderBlockedError):
        assert_external_ai_client_allowed("embedding")


def test_fatal_smoke_scope_is_bounded_and_restores_default_deny(monkeypatch):
    monkeypatch.setenv("NO_EXTERNAL_AI_CALLS", "1")
    monkeypatch.setenv("ALLOW_GMS_FATAL_SMOKE", "1")

    with gms_fatal_smoke_scope(
        max_http_requests=15,
        max_candidate_calls=1,
        max_b_model_calls=2,
        max_embedding_items=12,
    ):
        assert_external_ai_client_allowed("embedding")

    with pytest.raises(ExternalAIProviderBlockedError):
        assert_external_ai_client_allowed("embedding")


def test_fatal_smoke_scope_requires_both_flags(monkeypatch):
    monkeypatch.setenv("NO_EXTERNAL_AI_CALLS", "1")
    monkeypatch.delenv("ALLOW_GMS_FATAL_SMOKE", raising=False)

    with pytest.raises(ExternalAIProviderBlockedError):
        with gms_fatal_smoke_scope(
            max_http_requests=15,
            max_candidate_calls=1,
            max_b_model_calls=2,
            max_embedding_items=12,
        ):
            pass
