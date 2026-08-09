from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote_plus

import pytest
from sqlalchemy import inspect, select

from data_pipeline.storage import AudioUploadEvent, Request
from data_pipeline.stt import FakeTranscriber
from data_pipeline.worker.errors import S3DownloadError, S3EventValidationError
from data_pipeline.worker.fakes import FakeMeetingChatClient
from data_pipeline.worker.s3_download import S3TemporaryDownloader
from data_pipeline.worker.s3_events import S3EventParser, S3ObjectRecord
from data_pipeline.worker.sqs import SqsAudioWorker

BUCKET = "test-audio-bucket"
WAV = b"RIFF" + (8).to_bytes(4, "little") + b"WAVEfmt "


def _record(
    *,
    project: str = "project-1",
    meeting: str = "meeting-1",
    upload: str = "upload-1",
    filename: str = "meeting.wav",
    content: bytes = WAV,
    version_id: str | None = None,
    etag: str | None = "etag-1",
) -> tuple[dict, str]:
    key = f"audio-input/{project}/{meeting}/{upload}/{filename}"
    object_data: dict = {
        "key": quote_plus(key, safe="/"),
        "size": len(content),
    }
    if version_id is not None:
        object_data["versionId"] = version_id
    if etag is not None:
        object_data["eTag"] = etag
    return (
        {
            "eventName": "ObjectCreated:Put",
            "s3": {
                "bucket": {"name": BUCKET},
                "object": object_data,
            },
        },
        key,
    )


def _body(*records: dict) -> str:
    return json.dumps({"Records": list(records)})


def _parser(**kwargs) -> S3EventParser:
    return S3EventParser(
        allowed_buckets=frozenset({BUCKET}),
        **kwargs,
    )


class FakeS3:
    def __init__(self, objects: dict[str, bytes], *, fail_keys: set[str] | None = None):
        self.objects = objects
        self.fail_keys = fail_keys or set()
        self.calls: list[tuple] = []

    def download_fileobj(self, bucket, key, fileobj, **kwargs):
        self.calls.append((bucket, key, kwargs))
        if key in self.fail_keys:
            raise RuntimeError("simulated S3 failure")
        fileobj.write(self.objects[key])


class FakeSqs:
    def __init__(self, bodies: list[str]):
        self._bodies = list(bodies)
        self.receive_calls: list[dict] = []
        self.deleted: list[dict] = []
        self.visibility: list[dict] = []

    def receive_message(self, **kwargs):
        self.receive_calls.append(kwargs)
        if not self._bodies:
            return {}
        index = len(self.receive_calls)
        return {
            "Messages": [
                {
                    "MessageId": f"message-{index}",
                    "ReceiptHandle": f"receipt-{index}",
                    "Body": self._bodies.pop(0),
                }
            ]
        }

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    def change_message_visibility(self, **kwargs):
        self.visibility.append(kwargs)


def _worker(
    session_factory,
    *,
    sqs: FakeSqs,
    s3: FakeS3,
    transcriber=None,
) -> SqsAudioWorker:
    return SqsAudioWorker(
        sqs_client=sqs,
        queue_url="https://sqs.invalid/test",
        parser=_parser(),
        downloader=S3TemporaryDownloader(
            s3,
            max_audio_bytes=1024 * 1024,
        ),
        session_factory=session_factory,
        transcriber=transcriber or FakeTranscriber(),
        llm_client_factory=lambda record: FakeMeetingChatClient(
            record.external_meeting_id
        ),
        wait_time_seconds=1,
        visibility_timeout_seconds=30,
        heartbeat_interval_seconds=0,
        heartbeat_max_extensions=0,
        upload_processing_timeout_seconds=60,
    )


def test_parser_decodes_multiple_records_and_prefers_version_id() -> None:
    first, first_key = _record(
        filename="회의 녹음.wav",
        version_id="version-1",
        etag="etag-ignored",
    )
    second, second_key = _record(
        meeting="meeting-2",
        upload="upload-2",
        etag='"etag-2"',
    )

    parsed = _parser().parse(_body(first, second))

    assert [record.object_key for record in parsed.records] == [
        first_key,
        second_key,
    ]
    assert parsed.records[0].object_identity == "version-1"
    assert parsed.records[0].identity_kind == "VERSION_ID"
    assert parsed.records[1].object_identity == "etag-2"
    assert parsed.records[1].identity_kind == "ETAG"


def test_parser_accepts_s3_test_event() -> None:
    parsed = _parser().parse(
        json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent"})
    )

    assert parsed.is_test_event is True
    assert parsed.records == ()


@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        "{}",
        json.dumps({"Records": []}),
        _body(_record()[0] | {"eventName": "ObjectRemoved:Delete"}),
        _body(
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "production-bucket"},
                    "object": {
                        "key": "audio-input/p/m/u/a.wav",
                        "size": 10,
                        "eTag": "etag",
                    },
                },
            }
        ),
        _body(
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": BUCKET},
                    "object": {
                        "key": "audio-input/p/m/u/%2E%2E/escape.wav",
                        "size": 10,
                        "eTag": "etag",
                    },
                },
            }
        ),
        _body(_record(filename="meeting.exe")[0]),
        _body(_record(etag=None)[0]),
    ],
)
def test_parser_rejects_malformed_or_disallowed_events(body: str) -> None:
    with pytest.raises(S3EventValidationError):
        _parser().parse(body)


def test_downloader_uses_version_and_removes_temporary_file(tmp_path: Path) -> None:
    event, key = _record(version_id="version-7")
    record = _parser().parse(_body(event)).records[0]
    s3 = FakeS3({key: WAV})
    downloader = S3TemporaryDownloader(
        s3,
        max_audio_bytes=1024,
        temp_directory=tmp_path,
    )

    with downloader.download(record) as path:
        assert path.exists()
        assert path.read_bytes() == WAV
        downloaded_path = path

    assert not downloaded_path.exists()
    assert s3.calls == [
        (BUCKET, key, {"ExtraArgs": {"VersionId": "version-7"}})
    ]


def test_downloader_removes_file_after_validation_failure(tmp_path: Path) -> None:
    event, key = _record(content=b"not-a-wave")
    record = _parser().parse(_body(event)).records[0]
    downloader = S3TemporaryDownloader(
        FakeS3({key: b"not-a-wave"}),
        max_audio_bytes=1024,
        temp_directory=tmp_path,
    )

    with pytest.raises(S3DownloadError):
        with downloader.download(record):
            pass

    assert list(tmp_path.iterdir()) == []


def test_worker_deletes_only_after_pipeline_and_db_success(session_factory) -> None:
    event, key = _record()
    sqs = FakeSqs([_body(event)])
    s3 = FakeS3({key: WAV})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 1
    assert result.failed == 0
    assert len(sqs.deleted) == 1
    with session_factory() as session:
        upload = session.execute(select(AudioUploadEvent)).scalar_one()
        request = session.execute(select(Request)).scalar_one()
        assert upload.status == "COMPLETED"
        assert upload.pipeline_status == "REVIEW_PENDING"
        assert upload.external_request_id.startswith("s3-")
        assert request.status == "REVIEW_PENDING"
        assert request.project_id == "project-1"
        assert request.external_meeting_id == "meeting-1"


def test_worker_does_not_delete_failed_message(session_factory) -> None:
    event, key = _record()
    sqs = FakeSqs([_body(event)])
    s3 = FakeS3({key: b"not-a-wave"})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 0
    assert result.failed == 1
    assert sqs.deleted == []
    with session_factory() as session:
        upload = session.execute(select(AudioUploadEvent)).scalar_one()
        assert upload.status == "FAILED"
        assert upload.failure_code == "S3DownloadError"


def test_duplicate_event_reuses_completed_upload_without_download(session_factory) -> None:
    event, key = _record()
    body = _body(event)
    sqs = FakeSqs([body, body])
    s3 = FakeS3({key: WAV})
    worker = _worker(session_factory, sqs=sqs, s3=s3)

    first = worker.poll_once()
    second = worker.poll_once()

    assert first.deleted == second.deleted == 1
    assert len(sqs.deleted) == 2
    assert len(s3.calls) == 1
    with session_factory() as session:
        assert len(session.execute(select(AudioUploadEvent)).scalars().all()) == 1
        assert len(session.execute(select(Request)).scalars().all()) == 1


def test_failed_upload_is_retried_on_message_redelivery(session_factory) -> None:
    event, key = _record()
    body = _body(event)
    sqs = FakeSqs([body, body])
    s3 = FakeS3({key: b"bad-audio"})
    worker = _worker(session_factory, sqs=sqs, s3=s3)

    first = worker.poll_once()
    s3.objects[key] = WAV
    second = worker.poll_once()

    assert first.failed == 1
    assert second.deleted == 1
    assert len(sqs.deleted) == 1
    with session_factory() as session:
        upload = session.execute(select(AudioUploadEvent)).scalar_one()
        assert upload.status == "COMPLETED"
        assert upload.attempt_count == 2


def test_multi_record_message_is_deleted_only_when_all_succeed(session_factory) -> None:
    first, first_key = _record()
    second, second_key = _record(
        meeting="meeting-2",
        upload="upload-2",
        etag="etag-2",
        content=b"bad-audio",
    )
    sqs = FakeSqs([_body(first, second)])
    s3 = FakeS3({first_key: WAV, second_key: b"bad-audio"})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 0
    assert result.failed == 1
    assert sqs.deleted == []
    with session_factory() as session:
        rows = {
            row.external_meeting_id: row
            for row in session.execute(select(AudioUploadEvent)).scalars()
        }
        assert rows["meeting-1"].status == "COMPLETED"
        assert rows["meeting-2"].status == "FAILED"


def test_s3_test_event_is_acknowledged_without_pipeline_work(session_factory) -> None:
    sqs = FakeSqs(
        [json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent"})]
    )
    s3 = FakeS3({})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 1
    assert s3.calls == []
    with session_factory() as session:
        assert session.execute(select(AudioUploadEvent)).first() is None


def test_audio_upload_schema_has_database_unique_key(session_factory) -> None:
    with session_factory() as session:
        constraints = {
            value["name"]
            for value in inspect(session.get_bind()).get_unique_constraints(
                "audio_upload_event"
            )
        }

    assert "uq_audio_upload_object_identity" in constraints
