"""Speech-to-text adapters and the pipeline boundary."""

from .adapters import ClovaTranscriber, FakeTranscriber
from .clova_response import clova_response_to_segments
from .errors import (
    AudioFileError,
    TranscriptionError,
    TranscriptionResponseError,
    TranscriptionTransportError,
)
from .factory import build_transcriber
from .ports import SttSegmentDTO, Transcriber

__all__ = [
    "AudioFileError",
    "ClovaTranscriber",
    "FakeTranscriber",
    "SttSegmentDTO",
    "Transcriber",
    "TranscriptionError",
    "TranscriptionResponseError",
    "TranscriptionTransportError",
    "build_transcriber",
    "clova_response_to_segments",
]
