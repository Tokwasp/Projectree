"""STT boundary used by the node-generation pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypedDict


class SttSegmentDTO(TypedDict):
    """Segment shape accepted by ``pipeline.chain.run_meeting``."""

    segmentId: str
    sequenceNo: int
    startMs: int | None
    endMs: int | None
    speakerLabel: str | None
    text: str


class Transcriber(Protocol):
    """Convert one local audio file into pipeline-ready STT segments."""

    def transcribe(
        self,
        audio_path: Path,
        *,
        meeting_id: str,
    ) -> list[SttSegmentDTO]: ...


__all__ = ["SttSegmentDTO", "Transcriber"]
