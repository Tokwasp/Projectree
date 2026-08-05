"""Versioned meeting-minutes generation and persistence."""

from .contracts import (
    GeneratedMeetingSummary,
    MeetingSummaryGenerator,
    MeetingSummaryInput,
    SummarySegment,
)
from .fake import FakeMeetingSummaryGenerator
from .factory import build_meeting_summary_generator
from .gms import GmsMeetingSummaryGenerator, MeetingSummaryResponseError
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
    "GmsMeetingSummaryGenerator",
    "GeneratedMeetingSummary",
    "MeetingSummaryConflictError",
    "MeetingSummaryGenerator",
    "MeetingSummaryInput",
    "MeetingSummaryNotFoundError",
    "MeetingSummaryResult",
    "MeetingSummaryResponseError",
    "MeetingSummarySourceError",
    "SummarySegment",
    "build_meeting_summary_generator",
    "generate_meeting_summary",
    "get_meeting_summary",
]
