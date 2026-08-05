"""Provider-neutral meeting summary port.

No external provider implementation lives in this package.  Tests and local
validation use the deterministic fake adapter only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


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
    body: str
    decisions: tuple[str, ...] = field(default_factory=tuple)
    actions: tuple[str, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)

    def structured(self) -> dict[str, list[str]]:
        return {
            "decisions": list(self.decisions),
            "actions": list(self.actions),
            "issues": list(self.issues),
        }


class MeetingSummaryGenerator(Protocol):
    name: str
    version: str

    def generate(self, request: MeetingSummaryInput) -> GeneratedMeetingSummary: ...


__all__ = [
    "GeneratedMeetingSummary",
    "MeetingSummaryGenerator",
    "MeetingSummaryInput",
    "SummarySegment",
]
