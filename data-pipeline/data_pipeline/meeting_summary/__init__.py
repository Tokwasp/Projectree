"""Versioned meeting-minutes generation and persistence."""

from .contracts import (
    GeneratedMeetingSummary,
    MeetingSummaryContractError,
    MeetingSummaryGenerator,
    MeetingSummaryInput,
    SummarySegment,
    json_array_size_bytes,
    normalize_generated_summary,
    normalize_summary_items,
)
from .callback import (
    CallbackResult,
    MeetingRecordCallbackSettings,
    MeetingRecordCallbackClient,
    PermanentMeetingRecordCallbackError,
    RetryableMeetingRecordCallbackError,
    build_callback_body,
    build_meeting_record_callback_client,
    compact_callback_body,
    load_meeting_record_callback_settings,
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
    "CallbackResult",
    "MeetingRecordCallbackClient",
    "MeetingRecordCallbackSettings",
    "MeetingSummaryContractError",
    "MeetingSummaryConflictError",
    "MeetingSummaryGenerator",
    "MeetingSummaryInput",
    "MeetingSummaryNotFoundError",
    "MeetingSummaryResult",
    "MeetingSummaryResponseError",
    "MeetingSummarySourceError",
    "PermanentMeetingRecordCallbackError",
    "RetryableMeetingRecordCallbackError",
    "SummarySegment",
    "build_meeting_summary_generator",
    "build_callback_body",
    "build_meeting_record_callback_client",
    "compact_callback_body",
    "generate_meeting_summary",
    "get_meeting_summary",
    "json_array_size_bytes",
    "load_meeting_record_callback_settings",
    "normalize_generated_summary",
    "normalize_summary_items",
]
