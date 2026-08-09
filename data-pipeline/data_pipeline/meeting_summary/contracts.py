"""Provider-neutral meeting summary port.

No external provider implementation lives in this package.  Tests and local
validation use the deterministic fake adapter only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol


SUMMARY_SECTION_MAX_ITEMS = 500
SUMMARY_SECTION_SAFE_BYTES = 60_000
SUMMARY_SECTION_NAMES = ("summary", "decisions", "nextTodos", "issues")


class MeetingSummaryContractError(ValueError):
    """Raised when generated or stored minutes cannot satisfy Java's contract."""


@dataclass(frozen=True)
class SummarySegment:
    segment_id: str
    sequence_no: int
    speaker_label: str | None
    text: str


@dataclass(frozen=True)
class MeetingSummaryInput:
    project_id: str
    external_meeting_id: str
    segments: tuple[SummarySegment, ...]


@dataclass(frozen=True)
class GeneratedMeetingSummary:
    title: str
    summary: tuple[str, ...] = field(default_factory=tuple)
    decisions: tuple[str, ...] = field(default_factory=tuple)
    next_todos: tuple[str, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)

    def structured(self) -> dict[str, list[str]]:
        return {
            "summary": list(self.summary),
            "decisions": list(self.decisions),
            "nextTodos": list(self.next_todos),
            "issues": list(self.issues),
        }


def json_array_size_bytes(items: tuple[str, ...] | list[str]) -> int:
    return len(
        json.dumps(
            list(items),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def normalize_summary_items(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise MeetingSummaryContractError(f"{field} must be an array")
    if len(value) > SUMMARY_SECTION_MAX_ITEMS:
        raise MeetingSummaryContractError(
            f"{field} must contain at most {SUMMARY_SECTION_MAX_ITEMS} items"
        )
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise MeetingSummaryContractError(
                f"{field}[{index}] must be a non-empty string"
            )
        text = item.strip()
        if text.startswith(("- ", "* ", "• ")):
            raise MeetingSummaryContractError(
                f"{field}[{index}] must not include a bullet prefix"
            )
        normalized.append(text)
    result = tuple(normalized)
    size = json_array_size_bytes(result)
    if size > SUMMARY_SECTION_SAFE_BYTES:
        raise MeetingSummaryContractError(
            f"{field} is too large: {size} bytes "
            f"(safe limit: {SUMMARY_SECTION_SAFE_BYTES})"
        )
    return result


def normalize_generated_summary(
    document: GeneratedMeetingSummary,
) -> GeneratedMeetingSummary:
    if not isinstance(document.title, str) or not document.title.strip():
        raise MeetingSummaryContractError("title must be a non-empty string")
    title = document.title.strip()
    if len(title) > 200:
        raise MeetingSummaryContractError("title must not exceed 200 characters")
    return GeneratedMeetingSummary(
        title=title,
        summary=normalize_summary_items(document.summary, "summary"),
        decisions=normalize_summary_items(document.decisions, "decisions"),
        next_todos=normalize_summary_items(document.next_todos, "nextTodos"),
        issues=normalize_summary_items(document.issues, "issues"),
    )


class MeetingSummaryGenerator(Protocol):
    name: str
    version: str

    def generate(self, request: MeetingSummaryInput) -> GeneratedMeetingSummary: ...


__all__ = [
    "GeneratedMeetingSummary",
    "MeetingSummaryContractError",
    "MeetingSummaryGenerator",
    "MeetingSummaryInput",
    "SUMMARY_SECTION_MAX_ITEMS",
    "SUMMARY_SECTION_NAMES",
    "SUMMARY_SECTION_SAFE_BYTES",
    "SummarySegment",
    "json_array_size_bytes",
    "normalize_generated_summary",
    "normalize_summary_items",
]
