"""Producer/consumer SQS contract and visibility-heartbeat regression tests.

Two gaps found during the 2026-07-31 AWS end-to-end experiment are locked in here:

1. The queue that the worker consumes (``muOpenviduQueue``) is also fed by the
   OpenVidu/egress recording service, whose message body is NOT an S3 event
   notification. The worker rejects it. These tests pin the exact incompatible
   shape so the mismatch cannot be "fixed" silently or regress unnoticed.
2. ``_VisibilityHeartbeat`` had no coverage at all: every existing worker test
   constructs the worker with ``heartbeat_interval_seconds=0`` and
   ``heartbeat_max_extensions=0``, which disables the heartbeat thread.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote_plus

import pytest

from data_pipeline.stt import FakeTranscriber
from data_pipeline.worker.errors import S3EventValidationError
from data_pipeline.worker.fakes import FakeMeetingChatClient
from data_pipeline.worker.s3_download import S3TemporaryDownloader
from data_pipeline.worker.s3_events import S3EventParser
from data_pipeline.worker.sqs import SqsAudioWorker

BUCKET = "test-audio-bucket"
WAV = b"RIFF" + (8).to_bytes(4, "little") + b"WAVEfmt "

# Verbatim shape observed on the live queue on 2026-07-31 (identifiers replaced).
OPENVIDU_EGRESS_BODY = json.dumps(
    {
        "roomName": "00000000-0000-4000-8000-000000000001",
        "memberId": None,
        "kind": "MIXED",
        "objectKey": (
            "meetings/00000000-0000-4000-8000-000000000001"
            "/mixed/2026-07-31T031718.ogg"
        ),
        "egressId": "EG_XXXXXXXXXXXX",
        "endedAt": "2026-07-31T03:17:41.736107114",
    }
)


def _parser() -> S3EventParser:
    return S3EventParser(allowed_buckets=frozenset({BUCKET}))


def _s3_event_body(
    *,
    project: str = "project-1",
    meeting: str = "meeting-1",
    upload: str = "upload-1",
    filename: str = "meeting.wav",
    content: bytes = WAV,
) -> tuple[str, str]:
    key = f"audio-input/{project}/{meeting}/{upload}/{filename}"
    body = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": BUCKET},
                    "object": {
                        "key": quote_plus(key, safe="/"),
                        "size": len(content),
                        "eTag": "etag-1",
                    },
                },
            }
        ]
    }
    return json.dumps(body), key


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def download_fileobj(self, bucket, key, fileobj, **kwargs):
        fileobj.write(self.objects[key])


class _FakeSqs:
    def __init__(self, bodies: list[str]):
        self._bodies = list(bodies)
        self.deleted: list[dict] = []
        self.visibility: list[dict] = []
        self.receive_calls = 0

    def receive_message(self, **kwargs):
        self.receive_calls += 1
        if not self._bodies:
            return {}
        return {
            "Messages": [
                {
                    "MessageId": f"message-{self.receive_calls}",
                    "ReceiptHandle": f"receipt-{self.receive_calls}",
                    "Body": self._bodies.pop(0),
                }
            ]
        }

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    def change_message_visibility(self, **kwargs):
        self.visibility.append(kwargs)


class _SlowTranscriber:
    """Transcriber that holds the message long enough for heartbeats to fire."""

    def __init__(self, delay_seconds: float):
        self._delay = delay_seconds
        self._inner = FakeTranscriber()

    def transcribe(self, audio_path: Path, *, meeting_id: str):
        time.sleep(self._delay)
        return self._inner.transcribe(audio_path, meeting_id=meeting_id)


def _worker(
    session_factory,
    *,
    sqs: _FakeSqs,
    s3: _FakeS3,
    transcriber=None,
    heartbeat_interval_seconds: float = 0,
    heartbeat_max_extensions: int = 0,
    visibility_timeout_seconds: int = 30,
) -> SqsAudioWorker:
    return SqsAudioWorker(
        sqs_client=sqs,
        queue_url="https://sqs.invalid/test",
        parser=_parser(),
        downloader=S3TemporaryDownloader(s3, max_audio_bytes=1024 * 1024),
        session_factory=session_factory,
        transcriber=transcriber or FakeTranscriber(),
        llm_client_factory=lambda record: FakeMeetingChatClient(
            record.external_meeting_id
        ),
        wait_time_seconds=1,
        visibility_timeout_seconds=visibility_timeout_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        heartbeat_max_extensions=heartbeat_max_extensions,
        upload_processing_timeout_seconds=60,
    )


# --------------------------------------------------------------------------
# 1. Producer/consumer contract mismatch
# --------------------------------------------------------------------------


def test_openvidu_egress_body_is_rejected_by_the_s3_event_parser() -> None:
    """The live producer's body is not an S3 event and must not be accepted.

    This documents a real production incompatibility rather than asserting
    desired behaviour: the recording service publishes a flat object, while the
    worker only understands S3 ObjectCreated notifications.
    """

    with pytest.raises(S3EventValidationError) as excinfo:
        _parser().parse(OPENVIDU_EGRESS_BODY)
    assert "Records" in str(excinfo.value)


def test_openvidu_egress_body_lacks_every_field_the_worker_requires() -> None:
    """Pin exactly which fields are missing, so a future mapping is deliberate."""

    payload = json.loads(OPENVIDU_EGRESS_BODY)
    # Nothing the worker needs to build an S3ObjectRecord is present.
    for required in ("Records", "bucket", "eTag", "versionId", "size"):
        assert required not in payload
    # projectId in particular cannot be derived from this message at all;
    # only a room identifier is carried.
    assert "projectId" not in payload
    assert set(payload) == {
        "roomName",
        "memberId",
        "kind",
        "objectKey",
        "egressId",
        "endedAt",
    }
    # Its object key also violates the worker's prefix/segment contract.
    assert not payload["objectKey"].startswith("audio-input/")


def test_incompatible_producer_message_is_not_deleted_from_the_queue(
    session_factory,
) -> None:
    """A message the worker cannot parse must stay on the queue, not vanish."""

    sqs = _FakeSqs([OPENVIDU_EGRESS_BODY])
    worker = _worker(session_factory, sqs=sqs, s3=_FakeS3({}))

    result = worker.poll_once()

    assert result.received == 1
    assert result.deleted == 0
    assert result.failed == 1
    assert sqs.deleted == []


# --------------------------------------------------------------------------
# 2. Visibility heartbeat
# --------------------------------------------------------------------------


def test_visibility_heartbeat_extends_while_processing_and_stops_after(
    session_factory,
) -> None:
    body, key = _s3_event_body()
    sqs = _FakeSqs([body])
    worker = _worker(
        session_factory,
        sqs=sqs,
        s3=_FakeS3({key: WAV}),
        transcriber=_SlowTranscriber(0.35),
        heartbeat_interval_seconds=0.05,
        heartbeat_max_extensions=6,
        visibility_timeout_seconds=42,
    )

    result = worker.poll_once()
    assert result.deleted == 1

    assert sqs.visibility, "heartbeat never extended the message visibility"
    for call in sqs.visibility:
        assert call["QueueUrl"] == "https://sqs.invalid/test"
        assert call["ReceiptHandle"] == "receipt-1"
        assert call["VisibilityTimeout"] == 42

    # The heartbeat thread must be stopped once processing finished.
    observed = len(sqs.visibility)
    time.sleep(0.2)
    assert len(sqs.visibility) == observed


def test_visibility_heartbeat_respects_max_extensions(session_factory) -> None:
    body, key = _s3_event_body()
    sqs = _FakeSqs([body])
    worker = _worker(
        session_factory,
        sqs=sqs,
        s3=_FakeS3({key: WAV}),
        transcriber=_SlowTranscriber(0.5),
        heartbeat_interval_seconds=0.02,
        heartbeat_max_extensions=3,
    )

    result = worker.poll_once()

    assert result.deleted == 1
    assert 0 < len(sqs.visibility) <= 3


def test_visibility_heartbeat_failure_does_not_fail_the_message(
    session_factory,
) -> None:
    """A ChangeMessageVisibility error must not lose an otherwise good message."""

    body, key = _s3_event_body()

    class _FlakySqs(_FakeSqs):
        def change_message_visibility(self, **kwargs):
            super().change_message_visibility(**kwargs)
            raise RuntimeError("simulated ChangeMessageVisibility failure")

    sqs = _FlakySqs([body])
    worker = _worker(
        session_factory,
        sqs=sqs,
        s3=_FakeS3({key: WAV}),
        transcriber=_SlowTranscriber(0.2),
        heartbeat_interval_seconds=0.02,
        heartbeat_max_extensions=6,
    )

    result = worker.poll_once()

    assert result.deleted == 1
    assert result.failed == 0
    assert sqs.visibility
