"""Stable STT errors that do not expose provider credentials or response bodies."""


class TranscriptionError(RuntimeError):
    """Base error for STT processing."""


class AudioFileError(TranscriptionError):
    """The local audio input cannot safely be processed."""


class TranscriptionTransportError(TranscriptionError):
    """The STT provider request failed."""


class TranscriptionResponseError(TranscriptionError):
    """The STT provider returned an unusable response."""


__all__ = [
    "AudioFileError",
    "TranscriptionError",
    "TranscriptionResponseError",
    "TranscriptionTransportError",
]
