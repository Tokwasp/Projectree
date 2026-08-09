"""GMS/OpenAI-compatible meeting-summary adapter."""

from __future__ import annotations

import json
from typing import Any

from data_pipeline.llm import ChatClient

from .contracts import GeneratedMeetingSummary, MeetingSummaryInput


PROMPT_VERSION = "meeting-summary-v2"


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
            "정규화된 회의 Transcript에 직접 근거한 한국어 회의록을 만든다. "
            "사실, 담당자, 기한, 결정, 할 일, 이슈를 발명하지 말고 기술 용어를 "
            "보존한다. 설명, 코드 펜스, Markdown 없이 정확히 title, summary, "
            "decisions, nextTodos, issues 다섯 키만 가진 JSON 객체를 반환한다. "
            "title은 회의 전체를 대표하는 200자 이하의 비어 있지 않은 문자열이다. "
            "summary는 회의 전체 핵심 논의와 결과를 간결한 문장 배열로 작성하며 "
            "개수를 강제하지 않는다. decisions에는 최종 합의 또는 확정된 내용만 "
            "넣고 제안, 질문, 보류 사항은 넣지 않는다. nextTodos에는 회의 이후 "
            "수행할 구체적인 작업만 넣으며 담당자와 기한은 Transcript에 명시된 "
            "경우에만 포함한다. issues에는 회의 종료 후 남아 있는 문제, 위험, 확인 "
            "사항 또는 추가 논의를 넣고 회의 중 해결된 문제는 넣지 않는다. "
            "근거가 없는 항목은 만들지 말고 빈 배열을 반환한다. 같은 문장을 여러 "
            "배열에 반복하지 않으며 배열 요소에 -, • 같은 불릿 문자를 넣지 않는다. "
            "네 배열은 모두 문자열 배열이며 null을 반환하지 않는다."
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
        expected = {"title", "summary", "decisions", "nextTodos", "issues"}
        if set(payload) != expected:
            raise MeetingSummaryResponseError(
                "meeting summary provider response keys do not match the contract"
            )
        title = cls._string(payload["title"], "title")
        return GeneratedMeetingSummary(
            title=title,
            summary=cls._string_list(payload["summary"], "summary"),
            decisions=cls._string_list(payload["decisions"], "decisions"),
            next_todos=cls._string_list(payload["nextTodos"], "nextTodos"),
            issues=cls._string_list(payload["issues"], "issues"),
        )

    @staticmethod
    def _string(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise MeetingSummaryResponseError(f"{field} must be a non-empty string")
        normalized = value.strip()
        if field == "title" and len(normalized) > 200:
            raise MeetingSummaryResponseError("title must not exceed 200 characters")
        return normalized

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
