"""Convert the existing Clova Speech response into pipeline segment DTOs."""

from __future__ import annotations

from typing import Any

from .errors import TranscriptionResponseError
from .ports import SttSegmentDTO


def _speaker_label(raw: object) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("name") or raw.get("label")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _timestamp(raw: object, *, field: str, index: int) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise TranscriptionResponseError(
            f"Clova segment {index} has invalid {field}"
        )
    if isinstance(raw, float) and not raw.is_integer():
        raise TranscriptionResponseError(
            f"Clova segment {index} has invalid {field}"
        )
    value = int(raw)
    if value < 0:
        raise TranscriptionResponseError(
            f"Clova segment {index} has negative {field}"
        )
    return value


def clova_response_to_segments(
    payload: object,
    *,
    meeting_id: str,
) -> list[SttSegmentDTO]:
    """Map a synchronous Clova response to the DTO required by ``run_meeting``."""

    if not meeting_id or not meeting_id.strip():
        raise ValueError("meeting_id must not be empty")
    if not isinstance(payload, dict):
        raise TranscriptionResponseError("Clova response must be a JSON object")

    result = payload.get("result")
    if result is not None and result != "COMPLETED":
        raise TranscriptionResponseError(
            f"Clova transcription did not complete (result={result!r})"
        )

    raw_segments: Any = payload.get("segments")
    if raw_segments is not None and not isinstance(raw_segments, list):
        raise TranscriptionResponseError("Clova response segments must be an array")

    segments: list[SttSegmentDTO] = []
    for sequence_no, raw in enumerate(raw_segments or [], start=1):
        if not isinstance(raw, dict):
            raise TranscriptionResponseError(
                f"Clova segment {sequence_no} must be an object"
            )
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        start_ms = _timestamp(raw.get("start"), field="start", index=sequence_no)
        end_ms = _timestamp(raw.get("end"), field="end", index=sequence_no)
        if start_ms is not None and end_ms is not None and end_ms < start_ms:
            raise TranscriptionResponseError(
                f"Clova segment {sequence_no} ends before it starts"
            )
        segments.append(
            {
                "segmentId": f"{meeting_id}-seg-{sequence_no:06d}",
                "sequenceNo": sequence_no,
                "startMs": start_ms,
                "endMs": end_ms,
                "speakerLabel": _speaker_label(raw.get("speaker")),
                "text": text,
            }
        )

    if not segments:
        full_text = str(payload.get("text") or "").strip()
        if full_text:
            segments.append(
                {
                    "segmentId": f"{meeting_id}-seg-000001",
                    "sequenceNo": 1,
                    "startMs": None,
                    "endMs": None,
                    "speakerLabel": None,
                    "text": full_text,
                }
            )

    if not segments:
        raise TranscriptionResponseError(
            "Clova response contains no usable transcript"
        )
    return segments


__all__ = ["clova_response_to_segments"]
