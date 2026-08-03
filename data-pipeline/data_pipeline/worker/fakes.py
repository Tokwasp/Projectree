"""Deterministic adapters used by the first S3/SQS integration pass."""

from __future__ import annotations

import hashlib
import json

from data_pipeline.llm import LLMResponse


class FakeMeetingChatClient:
    """Return valid empty extraction/judgment envelopes for one meeting."""

    class _Settings:
        model = "fake-node-generation"
        temperature = 0.0

    settings = _Settings()

    def __init__(self, meeting_id: str):
        self._meeting_id = meeting_id
        self._call_count = 0

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        del messages
        self._call_count += 1
        if self._call_count == 1:
            payload = {"meetingId": self._meeting_id, "items": []}
        else:
            payload = {"meetingId": self._meeting_id, "judgments": []}
        raw = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(
            raw_response=raw,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            latency_ms=0,
        )


class FakeEmbeddingClient:
    """Stable non-zero vector; never use it as an operating similarity model."""

    def embed(self, *, text: str, model: str, dimensions: int):
        seed = hashlib.sha256(f"{model}\0{text}".encode("utf-8")).digest()
        return [
            ((seed[index % len(seed)] / 255.0) * 2.0) - 1.0
            for index in range(dimensions)
        ]


class FakeBModelClient:
    """Safe integration fake: it never merges or invents a relationship."""

    def recommend(self, *, source_node, retrieval_candidates, model):
        del retrieval_candidates, model
        return {
            "recommendation": "CREATE_NEW",
            "targetNodeId": None,
            "relationType": None,
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node.get("content", ""),
            "reason": "offline fake keeps every evidence-backed Node",
            "metadata": {"adapter": "fake", "automaticMerge": False},
        }


__all__ = [
    "FakeBModelClient",
    "FakeEmbeddingClient",
    "FakeMeetingChatClient",
]
