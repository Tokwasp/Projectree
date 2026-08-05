"""GMS/OpenAI-compatible meeting-summary adapter."""

from __future__ import annotations

import json
from typing import Any

from data_pipeline.llm import ChatClient

from .contracts import GeneratedMeetingSummary, MeetingSummaryInput


PROMPT_VERSION = "meeting-summary-v1"


class MeetingSummaryResponseError(ValueError):
    """Raised when the provider response violates the summary contract."""


class GmsMeetingSummaryGenerator:
    """Create a grounded Korean meeting summary through the shared chat port."""

    name = "gms"
    version = PROMPT_VERSION

    def __init__(self, client: ChatClient) -> None:
        self._client = client

    def generate(self, request: MeetingSummaryInput) -> GeneratedMeetingSummary:
        if not request.segments:
            raise MeetingSummaryResponseError(
                "meeting summary requires at least one transcript segment"
            )
        response = self._client.complete(self._messages(request))
        return self._parse(response.raw_response)

    @staticmethod
    def _messages(request: MeetingSummaryInput) -> list[dict[str, str]]:
        transcript = [
            {
                "segmentId": segment.segment_id,
                "sequenceNo": segment.sequence_no,
                "speakerLabel": segment.speaker_label,
                "text": segment.text,
            }
            for segment in request.segments
        ]
        system = (
            "You create a Korean meeting summary using only the supplied "
            "normalized transcript. Do not invent facts, owners, deadlines, "
            "decisions, actions, or issues. Preserve technical terms. Return "
            "one JSON object with exactly these keys: title, body, decisions, "
            "actions, issues. title and body are strings. decisions, actions, "
            "and issues are arrays of strings. body should be concise Markdown "
            "that a meeting participant can read without the raw transcript."
        )
        user = json.dumps(
            {
                "projectId": request.project_id,
                "meetingId": request.external_meeting_id,
                "transcript": transcript,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @classmethod
    def _parse(cls, raw: str) -> GeneratedMeetingSummary:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise MeetingSummaryResponseError(
                "meeting summary provider returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise MeetingSummaryResponseError(
                "meeting summary provider response must be an object"
            )
        expected = {"title", "body", "decisions", "actions", "issues"}
        if set(payload) != expected:
            raise MeetingSummaryResponseError(
                "meeting summary provider response keys do not match the contract"
            )
        title = cls._string(payload["title"], "title")
        body = cls._string(payload["body"], "body")
        return GeneratedMeetingSummary(
            title=title,
            body=body,
            decisions=cls._string_list(payload["decisions"], "decisions"),
            actions=cls._string_list(payload["actions"], "actions"),
            issues=cls._string_list(payload["issues"], "issues"),
        )

    @staticmethod
    def _string(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise MeetingSummaryResponseError(f"{field} must be a non-empty string")
        return value.strip()

    @classmethod
    def _string_list(cls, value: Any, field: str) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise MeetingSummaryResponseError(f"{field} must be an array")
        return tuple(cls._string(item, f"{field}[]") for item in value)


__all__ = [
    "GmsMeetingSummaryGenerator",
    "MeetingSummaryResponseError",
    "PROMPT_VERSION",
]
