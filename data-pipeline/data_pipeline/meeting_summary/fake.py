"""Deterministic local meeting summary adapter used without credits/network."""

from __future__ import annotations

from .contracts import GeneratedMeetingSummary, MeetingSummaryInput


class FakeMeetingSummaryGenerator:
    name = "fake"
    version = "fixture-v1"

    def __init__(self, result: GeneratedMeetingSummary | None = None) -> None:
        self._result = result
        self.calls: list[MeetingSummaryInput] = []

    def generate(self, request: MeetingSummaryInput) -> GeneratedMeetingSummary:
        self.calls.append(request)
        if self._result is not None:
            return self._result
        lines = [
            f"- {segment.speaker_label or 'speaker'}: {segment.text}"
            for segment in request.segments
        ]
        return GeneratedMeetingSummary(
            title=f"회의록 - {request.external_meeting_id}",
            body="\n".join(lines) or "- No transcript content.",
        )


__all__ = ["FakeMeetingSummaryGenerator"]
