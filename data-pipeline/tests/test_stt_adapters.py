from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from data_pipeline.config import SttSettings
from data_pipeline.contracts.io import Segment
from data_pipeline.pipeline.chain import normalize_transcript_segments
from data_pipeline.stt import (
    AudioFileError,
    ClovaTranscriber,
    FakeTranscriber,
    TranscriptionResponseError,
    TranscriptionTransportError,
    build_transcriber,
    clova_response_to_segments,
)

FIXTURE = Path(__file__).parent / "fixtures" / "clova_response.json"


def _audio(tmp_path: Path, content: bytes = b"not-real-audio") -> Path:
    path = tmp_path / "meeting.wav"
    path.write_bytes(content)
    return path


class _JsonResponse:
    def __init__(self, payload: object):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class _RecordingClient:
    def __init__(self, payload: object):
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _JsonResponse:
        media = kwargs["files"]["media"]
        self.calls.append(
            {
                "url": url,
                "headers": kwargs["headers"],
                "filename": media[0],
                "audio": media[1].read(),
                "params": json.loads(kwargs["files"]["params"][1]),
                "timeout": kwargs["timeout"],
            }
        )
        return _JsonResponse(self.payload)


class _FailingClient:
    def post(self, url: str, **kwargs: Any) -> _JsonResponse:
        raise httpx.ConnectError("provider unavailable")


def test_fixture_converts_to_run_meeting_segment_contract(tmp_path: Path) -> None:
    transcriber = FakeTranscriber.from_fixture(FIXTURE)

    segments = transcriber.transcribe(_audio(tmp_path), meeting_id="meeting-42")

    assert segments == [
        {
            "segmentId": "meeting-42-seg-000001",
            "sequenceNo": 1,
            "startMs": 120,
            "endMs": 1840,
            "speakerLabel": "참석자 1",
            "text": "깃 랩 배포를 확인합니다.",
        },
        {
            "segmentId": "meeting-42-seg-000002",
            "sequenceNo": 2,
            "startMs": 1900,
            "endMs": 4100,
            "speakerLabel": "2",
            "text": "스프링 부트 작업도 확인했습니다.",
        },
    ]
    assert all(Segment.model_validate(segment) for segment in segments)
    normalized = normalize_transcript_segments(segments)
    assert normalized[0]["rawText"] == "깃 랩 배포를 확인합니다."
    assert normalized[0]["normalizedText"]


def test_clova_adapter_reuses_upload_contract_without_network(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    client = _RecordingClient(payload)
    transcriber = ClovaTranscriber(
        invoke_url="https://clova.invalid/test/",
        secret="not-a-real-secret",
        timeout_seconds=17,
        http_client=client,
    )

    segments = transcriber.transcribe(_audio(tmp_path), meeting_id="meeting-7")

    assert len(segments) == 2
    assert client.calls == [
        {
            "url": "https://clova.invalid/test/recognizer/upload",
            "headers": {"X-CLOVASPEECH-API-KEY": "not-a-real-secret"},
            "filename": "meeting.wav",
            "audio": b"not-real-audio",
            "params": {
                "language": "enko",
                "completion": "sync",
                "fullText": True,
                "wordAlignment": True,
                "diarization": {"enable": True},
            },
            "timeout": 17,
        }
    ]


def test_full_text_is_used_when_clova_has_no_segments() -> None:
    segments = clova_response_to_segments(
        {"result": "COMPLETED", "text": "전체 회의 내용"},
        meeting_id="meeting-full",
    )

    assert segments == [
        {
            "segmentId": "meeting-full-seg-000001",
            "sequenceNo": 1,
            "startMs": None,
            "endMs": None,
            "speakerLabel": None,
            "text": "전체 회의 내용",
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"result": "FAILED", "text": "부분 응답"},
        {"result": "COMPLETED", "segments": {}},
        {"result": "COMPLETED", "segments": ["invalid"]},
        {
            "result": "COMPLETED",
            "segments": [{"start": 20, "end": 10, "text": "잘못된 시간"}],
        },
        {"result": "COMPLETED", "segments": [], "text": ""},
    ],
)
def test_malformed_clova_responses_are_rejected(payload: object) -> None:
    with pytest.raises(TranscriptionResponseError):
        clova_response_to_segments(payload, meeting_id="meeting-error")


def test_audio_path_must_exist_and_not_be_empty(tmp_path: Path) -> None:
    transcriber = FakeTranscriber()

    with pytest.raises(AudioFileError):
        transcriber.transcribe(tmp_path / "missing.wav", meeting_id="meeting")
    with pytest.raises(AudioFileError):
        transcriber.transcribe(_audio(tmp_path, b""), meeting_id="meeting")


def test_fake_does_not_hide_an_explicit_empty_response(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionResponseError):
        FakeTranscriber({}).transcribe(_audio(tmp_path), meeting_id="meeting")


def test_clova_transport_error_is_wrapped(tmp_path: Path) -> None:
    transcriber = ClovaTranscriber(
        invoke_url="https://clova.invalid",
        secret="secret",
        http_client=_FailingClient(),
    )

    with pytest.raises(TranscriptionTransportError) as exc_info:
        transcriber.transcribe(_audio(tmp_path), meeting_id="meeting")

    assert "secret" not in str(exc_info.value)


def test_factory_selects_fake_or_clova(tmp_path: Path) -> None:
    fake = build_transcriber(
        SttSettings(adapter="fake", fake_response_path=FIXTURE)
    )
    clova = build_transcriber(
        SttSettings(
            adapter="clova",
            clova_invoke_url="https://clova.invalid",
            clova_secret="secret",
        )
    )

    assert isinstance(fake, FakeTranscriber)
    assert isinstance(clova, ClovaTranscriber)
    assert len(fake.transcribe(_audio(tmp_path), meeting_id="meeting")) == 2


def test_clova_factory_requires_provider_credentials() -> None:
    with pytest.raises(ValueError, match="CLOVA_INVOKE_URL"):
        build_transcriber(SttSettings(adapter="clova"))
