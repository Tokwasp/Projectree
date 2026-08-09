from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests.evaluation_support.gms_fatal_smoke import (
    CallBudget,
    HardCallBudgetExceeded,
    MeteredBModelClient,
    MeteredChatClient,
    MeteredEmbeddingClient,
    ProviderUsageLedger,
    contains_secret_field,
    derive_database_urls,
    meeting_input,
    redact,
)
from data_pipeline.llm import LLMResponse
from data_pipeline.retrieval.embedding_client import EmbeddingCallResult, EmbeddingUsage
from data_pipeline.storage import Evidence


def test_corrected_production_path_budget_is_exactly_15_requests():
    budget = CallBudget()
    budget.validate(
        candidate_calls=2,
        b_model_calls=4,
        embedding_items=9,
        http_requests=15,
    )

    with pytest.raises(HardCallBudgetExceeded):
        budget.validate(
            candidate_calls=2,
            b_model_calls=4,
            embedding_items=10,
            http_requests=16,
        )


def test_ledger_blocks_before_sixteenth_http_request():
    ledger = ProviderUsageLedger(CallBudget())
    for _ in range(2):
        ledger.reserve(provider="candidate-llm")
    for _ in range(4):
        ledger.reserve(provider="b-model")
    for _ in range(9):
        ledger.reserve(provider="embedding", embedding_items=1)

    with pytest.raises(HardCallBudgetExceeded):
        ledger.reserve(provider="embedding", embedding_items=1)


def test_secret_redaction_removes_credential_shaped_fields():
    source = {
        "GMS_KEY": "should-not-survive",
        "nested": {"Authorization": "Bearer should-not-survive", "model": "fixture"},
    }
    result = redact(source)
    assert result["GMS_KEY"] == "<redacted>"
    assert result["nested"]["Authorization"] == "<redacted>"
    assert not contains_secret_field(result)


def test_disposable_database_name_never_reuses_pipeline_database():
    admin, target, name = derive_database_urls(
        "postgresql+psycopg://user:password@localhost:5432/pipeline",
        "20260803_170000",
    )
    assert admin.database == "postgres"
    assert target.database == name
    assert name.startswith("gms_smoke_")
    assert name != "pipeline"


def test_synthetic_meeting_input_uses_no_s3_sqs_or_clova_fields():
    payload = meeting_input()
    assert len(payload["segments"]) == 4
    assert "s3" not in payload
    assert "audio" not in payload


def test_fatal_evidence_validator_uses_current_immutable_evidence_contract():
    assert hasattr(Evidence, "external_meeting_id")
    assert hasattr(Evidence, "source_segment_id")
    assert not hasattr(Evidence, "source_meeting_id")


class _Chat:
    settings = type("Settings", (), {"model": "candidate-model"})()

    def complete(self, messages):
        assert messages
        return LLMResponse("{}", 2, 3, 5, 7)


@dataclass
class _EmbeddingSettings:
    model: str = "embedding-model"


class _Embedding:
    settings = _EmbeddingSettings()

    def embed_detailed(self, *, text, model, dimensions):
        assert text and model and dimensions == 3
        return EmbeddingCallResult(
            vector=[1.0, 0.0, 0.0],
            usage=EmbeddingUsage(4, 0, 4, None, "PROVIDER_REPORTED"),
            latency_ms=8,
            request_id="fixture",
            retry_count=0,
            rate_limit={},
        )


@dataclass
class _BSettings:
    model: str = "b-model"


class _BResult:
    decision = {
        "recommendation": "CREATE_NEW",
        "targetNodeId": None,
        "relationType": None,
        "suggestedTitle": "fixture",
        "suggestedContent": "fixture",
        "reason": "fixture",
        "metadata": {},
    }
    usage = {"total_tokens": 6}
    latency_ms = 9
    retry_count = 0


class _B:
    provider_model = "fake-b-model"

    settings = _BSettings()

    def recommend_detailed(self, **kwargs):
        assert kwargs["source_node"]
        return _BResult()


def test_metered_wrappers_preserve_item_level_production_calls():
    ledger = ProviderUsageLedger(CallBudget())
    chat = MeteredChatClient(_Chat(), ledger)
    embedding = MeteredEmbeddingClient(_Embedding(), ledger)
    b_model = MeteredBModelClient(_B(), ledger)

    chat.complete([{"role": "user", "content": "fixture"}])
    embedding.embed(text="fixture", model="embedding-model", dimensions=3)
    decision = b_model.recommend(
        source_node={"nodeId": "source"},
        retrieval_candidates=[],
    )

    assert decision["recommendation"] == "CREATE_NEW"
    assert ledger.candidate_calls == 1
    assert ledger.embedding_items == 1
    assert ledger.b_model_calls == 1
    assert ledger.http_requests == 3
    assert len(b_model.calls) == 1
