"""Versioned meeting-minutes generation and persistence."""

from .contracts import (
    GeneratedMeetingSummary,
    MeetingSummaryGenerator,
    MeetingSummaryInput,
    SummarySegment,
)
from .fake import FakeMeetingSummaryGenerator
from .service import (
    MeetingSummaryConflictError,
    MeetingSummaryNotFoundError,
    MeetingSummaryResult,
    MeetingSummarySourceError,
    generate_meeting_summary,
    get_meeting_summary,
)

__all__ = [
    "FakeMeetingSummaryGenerator",
    "GeneratedMeetingSummary",
    "MeetingSummaryConflictError",
    "MeetingSummaryGenerator",
    "MeetingSummaryInput",
    "MeetingSummaryNotFoundError",
    "MeetingSummaryResult",
    "MeetingSummarySourceError",
    "SummarySegment",
    "generate_meeting_summary",
    "get_meeting_summary",
]
