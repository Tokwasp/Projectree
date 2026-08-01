"""Fake and Clova implementations of the local-file Transcriber port."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import httpx

from .clova_response import clova_response_to_segments
from .errors import (
    AudioFileError,
    TranscriptionResponseError,
    TranscriptionTransportError,
)
from .ports import SttSegmentDTO

_DEFAULT_FAKE_RESPONSE = {
    "result": "COMPLETED",
    "segments": [
        {
            "start": 0,
            "end": 1000,
            "text": "테스트 음성입니다.",
            "speaker": {"label": "1"},
        }
    ],
}


class _Response(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class _HttpClient(Protocol):
    def post(self, url: str, **kwargs: Any) -> _Response: ...


def _validated_audio_path(audio_path: Path) -> Path:
    path = Path(audio_path)
    if not path.is_file():
        raise AudioFileError(f"Audio file does not exist: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AudioFileError(f"Cannot inspect audio file: {path}") from exc
    if size <= 0:
        raise AudioFileError(f"Audio file is empty: {path}")
    return path


class FakeTranscriber:
    """Deterministic adapter retained for local S3/SQS integration checks."""

    def __init__(self, response_payload: dict[str, Any] | None = None):
        self._response_payload = (
            _DEFAULT_FAKE_RESPONSE
            if response_payload is None
            else response_payload
        )

    @classmethod
    def from_fixture(cls, path: Path) -> "FakeTranscriber":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TranscriptionResponseError(
                f"Cannot load fake STT response fixture: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise TranscriptionResponseError(
                "Fake STT response fixture must contain a JSON object"
            )
        return cls(payload)

    def transcribe(
        self,
        audio_path: Path,
        *,
        meeting_id: str,
    ) -> list[SttSegmentDTO]:
        _validated_audio_path(audio_path)
        return clova_response_to_segments(
            self._response_payload,
            meeting_id=meeting_id,
        )


class ClovaTranscriber:
    """Adapter around the existing Clova Speech synchronous upload contract."""

    def __init__(
        self,
        *,
        invoke_url: str,
        secret: str,
        timeout_seconds: float = 900,
        http_client: _HttpClient | None = None,
    ):
        if not invoke_url.strip():
            raise ValueError("CLOVA_INVOKE_URL is required for STT_ADAPTER=clova")
        if not secret.strip():
            raise ValueError("CLOVA_SECRET is required for STT_ADAPTER=clova")
        if timeout_seconds <= 0:
            raise ValueError("CLOVA_TIMEOUT_SECONDS must be positive")
        self._invoke_url = invoke_url.rstrip("/")
        self._secret = secret
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    def transcribe(
        self,
        audio_path: Path,
        *,
        meeting_id: str,
    ) -> list[SttSegmentDTO]:
        path = _validated_audio_path(audio_path)
        params = {
            "language": "enko",
            "completion": "sync",
            "fullText": True,
            "wordAlignment": True,
            "diarization": {"enable": True},
        }
        client = self._http_client or httpx
        try:
            with path.open("rb") as audio:
                response = client.post(
                    f"{self._invoke_url}/recognizer/upload",
                    headers={"X-CLOVASPEECH-API-KEY": self._secret},
                    files={
                        "media": (
                            path.name,
                            audio,
                            "application/octet-stream",
                        ),
                        "params": (
                            None,
                            json.dumps(params),
                            "application/json",
                        ),
                    },
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise TranscriptionTransportError(
                "Clova transcription request failed"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TranscriptionResponseError(
                "Clova response is not valid JSON"
            ) from exc
        return clova_response_to_segments(payload, meeting_id=meeting_id)


__all__ = ["ClovaTranscriber", "FakeTranscriber"]
