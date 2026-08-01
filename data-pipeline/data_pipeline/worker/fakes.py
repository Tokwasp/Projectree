"""Deterministic adapters used by the first S3/SQS integration pass."""

from __future__ import annotations

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


__all__ = ["FakeMeetingChatClient"]
