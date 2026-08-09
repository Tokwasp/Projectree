"""OpenVidu egress ingestion: parser, S3 enrichment, room mapping, worker.

The reference body is the one actually observed on the production queue
``muOpenviduQueue`` on 2026-07-31 (identifiers replaced with fixtures).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from data_pipeline.storage import AudioUploadEvent, Request
from data_pipeline.stt import FakeTranscriber
from data_pipeline.worker.errors import (
    MeetingContextUnresolvedError,
    OpenViduEventValidationError,
    S3MetadataError,
    UnsupportedMessageError,
)
from data_pipeline.worker.fakes import FakeMeetingChatClient
from data_pipeline.worker.meeting_context import (
    MeetingContext,
    StaticMeetingContextResolver,
    UnavailableMeetingContextResolver,
)
from data_pipeline.worker.message_router import (
    OPENVIDU_CONTRACT,
    S3_EVENT_CONTRACT,
    SqsMessageRouter,
)
from data_pipeline.worker.openvidu_events import (
    OpenViduEgressEventParser,
    looks_like_openvidu_egress,
)
from data_pipeline.worker.openvidu_ingest import OpenViduIngestAdapter
from data_pipeline.worker.s3_download import S3TemporaryDownloader
from data_pipeline.worker.s3_events import S3EventParser
from data_pipeline.worker.sqs import SqsAudioWorker

BUCKET = "projectree-bucket"
ROOM = "eebcfd55-bdd1-4dc0-b0a2-352a072cd3cf"
EGRESS = "EG_UuuCd2jaUU6J"
KEY = f"meetings/{ROOM}/mixed/2026-07-31T072730.ogg"
OGG = b"OggS" + bytes(28)
PROJECT = "168a9037-485a-4145-a93f-a651fd1a254c"
MEETING = "33cdf33c-aa42-471e-a0a0-d257ffc8a9eb"


def _event(**overrides) -> dict:
    payload = {
        "projectId": 15,
        "roomName": ROOM,
        "memberId": None,
        "kind": "MIXED",
        "objectKey": KEY,
        "egressId": EGRESS,
        "endedAt": "2026-07-31T07:28:05.804108359",
    }
    payload.update(overrides)
    return payload


def _body(**overrides) -> str:
    return json.dumps(_event(**overrides))


def _parser(**kwargs) -> OpenViduEgressEventParser:
    return OpenViduEgressEventParser(**kwargs)


class _FakeHeadS3:
    """Minimal S3 double supporting head_object and download_fileobj."""

    def __init__(self, objects: dict[str, bytes], *, head: dict | None = None,
                 head_error: Exception | None = None):
        self.objects = objects
        self._head = head
        self._head_error = head_error
        self.head_calls: list[dict] = []
        self.download_calls: list[tuple] = []

    def head_object(self, **kwargs):
        self.head_calls.append(kwargs)
        if self._head_error is not None:
            raise self._head_error
        if self._head is not None:
            return dict(self._head)
        body = self.objects[kwargs["Key"]]
        import hashlib
        return {
            "ContentLength": len(body),
            "ETag": '"' + hashlib.md5(body).hexdigest() + '"',
            "ContentType": "audio/ogg",
        }

    def download_fileobj(self, bucket, key, fileobj, **kwargs):
        self.download_calls.append((bucket, key, kwargs))
        fileobj.write(self.objects[key])


def _adapter(s3, resolver=None, *, max_audio_bytes=1024 * 1024) -> OpenViduIngestAdapter:
    return OpenViduIngestAdapter(
        s3_client=s3,
        resolver=resolver
        or StaticMeetingContextResolver.from_pairs({ROOM: (PROJECT, MEETING)}),
        bucket=BUCKET,
        max_audio_bytes=max_audio_bytes,
    )


# ---------------------------------------------------------------- parser ---


def test_parser_accepts_the_observed_production_body() -> None:
    event = _parser().parse(_body())

    assert event.project_id == "15"
    assert event.room_name == ROOM
    assert event.egress_id == EGRESS
    assert event.object_key == KEY
    assert event.kind == "MIXED"
    assert event.member_id is None
    assert event.filename == "2026-07-31T072730.ogg"
    # endedAt has no timezone offset, so it is preserved verbatim, never parsed.
    assert event.ended_at_raw == "2026-07-31T07:28:05.804108359"


@pytest.mark.parametrize("missing", ["roomName", "egressId", "objectKey"])
def test_parser_rejects_missing_required_fields(missing: str) -> None:
    payload = _event()
    del payload[missing]
    with pytest.raises(OpenViduEventValidationError) as excinfo:
        _parser().parse(json.dumps(payload))
    assert missing in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_parser_rejects_blank_required_fields(blank: str) -> None:
    with pytest.raises(OpenViduEventValidationError):
        _parser().parse(_body(roomName=blank))


def test_parser_rejects_invalid_json() -> None:
    with pytest.raises(OpenViduEventValidationError):
        _parser().parse("not-json")


def test_parser_rejects_non_object_payload() -> None:
    with pytest.raises(OpenViduEventValidationError):
        _parser().parse("[1, 2, 3]")


def test_parser_rejects_unsupported_kind() -> None:
    """kind values other than MIXED were never observed; never guess at them."""

    with pytest.raises(OpenViduEventValidationError) as excinfo:
        _parser().parse(_body(kind="INDIVIDUAL"))
    assert "INDIVIDUAL" in str(excinfo.value)


def test_parser_rejects_key_outside_the_recording_prefix() -> None:
    with pytest.raises(OpenViduEventValidationError) as excinfo:
        _parser().parse(_body(objectKey="audio-input/test/a/b/c/d.ogg"))
    assert "prefix" in str(excinfo.value)


def test_parser_rejects_disallowed_extension() -> None:
    with pytest.raises(OpenViduEventValidationError):
        _parser().parse(_body(objectKey=f"meetings/{ROOM}/mixed/take.exe"))


@pytest.mark.parametrize(
    "key",
    [
        f"meetings/{ROOM}/../../etc/passwd.ogg",
        f"meetings/{ROOM}/./mixed/take.ogg",
        "meetings\\room\\mixed\\take.ogg",
        "meetings/",
    ],
)
def test_parser_rejects_path_traversal_and_empty_names(key: str) -> None:
    with pytest.raises(OpenViduEventValidationError):
        _parser().parse(_body(objectKey=key))


def test_parser_rejects_room_that_does_not_match_the_object_key() -> None:
    """The project comes from roomName but the audio comes from objectKey.

    If they disagree, one room's recording would be transcribed into another
    room's project, using a perfectly real projectId.
    """

    with pytest.raises(OpenViduEventValidationError) as excinfo:
        _parser().parse(
            _body(objectKey="meetings/some-other-room/mixed/2026-07-31T072730.ogg")
        )
    assert "room segment" in str(excinfo.value)


@pytest.mark.parametrize("field", ["roomName", "egressId"])
def test_parser_bounds_identifiers_that_reach_128_char_columns(field: str) -> None:
    """egressId becomes upload_id String(128); roomName feeds the same layer.

    Without this bound PostgreSQL raises DataError at COMMIT - after Clova and
    the LLM have already been paid for.
    """

    overrides = {field: "x" * 129}
    if field == "roomName":
        overrides["objectKey"] = f"meetings/{'x' * 129}/mixed/take.ogg"
    with pytest.raises(OpenViduEventValidationError) as excinfo:
        _parser().parse(_body(**overrides))
    assert "too long" in str(excinfo.value)


def test_parser_accepts_identifiers_at_the_128_boundary() -> None:
    event = _parser().parse(
        _body(
            egressId="e" * 128,
        )
    )
    assert event.room_name == ROOM
    assert len(event.egress_id) == 128


def test_parser_rejects_non_string_member_id() -> None:
    with pytest.raises(OpenViduEventValidationError):
        _parser().parse(_body(memberId=42))


def test_parser_accepts_a_populated_member_id() -> None:
    event = _parser().parse(_body(memberId="member-7"))
    assert event.member_id == "member-7"


def test_discriminator_matches_only_openvidu_shaped_bodies() -> None:
    assert looks_like_openvidu_egress(_event()) is True
    assert looks_like_openvidu_egress({"Records": []}) is False
    assert looks_like_openvidu_egress("string") is False


# ------------------------------------------------- S3 metadata enrichment ---


def test_adapter_fills_bucket_size_and_etag_from_head_object() -> None:
    s3 = _FakeHeadS3({KEY: OGG})
    record = _adapter(s3).to_record(_parser().parse(_body()))

    assert s3.head_calls == [{"Bucket": BUCKET, "Key": KEY}]
    assert record.bucket == BUCKET
    assert record.object_key == KEY
    assert record.size == len(OGG)
    assert record.etag is not None and '"' not in record.etag
    assert record.identity_kind == "ETAG"
    assert record.project_id == PROJECT
    assert record.external_meeting_id == MEETING
    # egressId is a stable per-recording id, so it becomes the upload id and is
    # persisted on audio_upload_event without needing a new migration.
    assert record.upload_id == EGRESS
    assert record.filename == "2026-07-31T072730.ogg"


def test_adapter_normalizes_quoted_etag() -> None:
    s3 = _FakeHeadS3({}, head={"ContentLength": 10, "ETag": '"abc123"'})
    record = _adapter(s3).to_record(_parser().parse(_body()))
    assert record.etag == "abc123"


def test_adapter_prefers_version_id_over_etag() -> None:
    s3 = _FakeHeadS3(
        {}, head={"ContentLength": 10, "ETag": '"abc123"', "VersionId": "v-9"}
    )
    record = _adapter(s3).to_record(_parser().parse(_body()))
    assert record.version_id == "v-9"
    assert record.object_identity == "v-9"
    assert record.identity_kind == "VERSION_ID"


def test_adapter_rejects_object_exceeding_the_size_limit() -> None:
    s3 = _FakeHeadS3({}, head={"ContentLength": 999_999, "ETag": '"a"'})
    with pytest.raises(S3MetadataError) as excinfo:
        _adapter(s3, max_audio_bytes=1000).to_record(_parser().parse(_body()))
    assert "size limit" in str(excinfo.value)


@pytest.mark.parametrize("head", [{"ETag": '"a"'}, {"ContentLength": 0, "ETag": '"a"'}])
def test_adapter_rejects_missing_or_zero_content_length(head: dict) -> None:
    s3 = _FakeHeadS3({}, head=head)
    with pytest.raises(S3MetadataError):
        _adapter(s3).to_record(_parser().parse(_body()))


def test_adapter_rejects_object_without_etag_or_version_id() -> None:
    """Without an object identity the upload cannot be de-duplicated."""

    s3 = _FakeHeadS3({}, head={"ContentLength": 10})
    with pytest.raises(S3MetadataError) as excinfo:
        _adapter(s3).to_record(_parser().parse(_body()))
    assert "idempotent" in str(excinfo.value)


def test_adapter_wraps_head_object_access_denied() -> None:
    """The live IAM policy denies meetings/*, so this path must be explicit."""

    s3 = _FakeHeadS3({}, head_error=RuntimeError("An error occurred (403) ... Forbidden"))
    with pytest.raises(S3MetadataError) as excinfo:
        _adapter(s3).to_record(_parser().parse(_body()))
    assert "HeadObject" in str(excinfo.value)


def test_adapter_wraps_missing_object() -> None:
    s3 = _FakeHeadS3({}, head_error=KeyError("NoSuchKey"))
    with pytest.raises(S3MetadataError):
        _adapter(s3).to_record(_parser().parse(_body()))


def test_adapter_tolerates_missing_content_type() -> None:
    s3 = _FakeHeadS3({}, head={"ContentLength": 10, "ETag": '"abc"'})
    record = _adapter(s3).to_record(_parser().parse(_body()))
    assert record.size == 10


# ----------------------------------------------------- room -> project map ---


def test_resolver_maps_a_known_room() -> None:
    resolver = StaticMeetingContextResolver.from_pairs({ROOM: (PROJECT, MEETING)})
    context = resolver.resolve_by_openvidu_room(ROOM)
    assert context == MeetingContext(
        project_id=PROJECT, external_meeting_id=MEETING
    )


def test_unknown_room_is_reported_as_unresolved() -> None:
    s3 = _FakeHeadS3({KEY: OGG})
    adapter = _adapter(s3, StaticMeetingContextResolver({}))
    with pytest.raises(MeetingContextUnresolvedError):
        adapter.to_record(_parser().parse(_body()))


def test_unresolved_mapping_is_detected_before_calling_s3() -> None:
    """Never spend an S3 call on a recording we cannot place in the graph."""

    s3 = _FakeHeadS3({KEY: OGG})
    adapter = _adapter(s3, StaticMeetingContextResolver({}))
    with pytest.raises(MeetingContextUnresolvedError):
        adapter.to_record(_parser().parse(_body()))
    assert s3.head_calls == []


def test_default_resolver_refuses_to_guess() -> None:
    """The shipped default must never invent a projectId."""

    with pytest.raises(MeetingContextUnresolvedError) as excinfo:
        UnavailableMeetingContextResolver().resolve_by_openvidu_room(ROOM)
    assert "mapping source" in str(excinfo.value)


@pytest.mark.parametrize("bad", [("", MEETING), (PROJECT, ""), ("x" * 129, MEETING)])
def test_meeting_context_rejects_invalid_identifiers(bad) -> None:
    with pytest.raises(ValueError):
        MeetingContext(project_id=bad[0], external_meeting_id=bad[1])


# ------------------------------------------------------------------ router ---


def _router(*, openvidu: bool = True, s3=None, resolver=None) -> SqsMessageRouter:
    return SqsMessageRouter(
        s3_parser=S3EventParser(allowed_buckets=frozenset({BUCKET})),
        openvidu_parser=_parser() if openvidu else None,
        openvidu_adapter=(
            _adapter(s3 or _FakeHeadS3({KEY: OGG}), resolver) if openvidu else None
        ),
    )


def test_router_sends_openvidu_bodies_to_the_openvidu_contract() -> None:
    routed = _router().route(_body())
    assert routed.contract == OPENVIDU_CONTRACT
    assert len(routed.records) == 1
    assert routed.records[0].upload_id == EGRESS


def test_router_still_sends_s3_events_to_the_s3_contract() -> None:
    body = json.dumps(
        {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": BUCKET},
                        "object": {
                            "key": "audio-input/p/m/u/a.ogg",
                            "size": 32,
                            "eTag": "etag-1",
                        },
                    },
                }
            ]
        }
    )
    routed = _router().route(body)
    assert routed.contract == S3_EVENT_CONTRACT
    assert routed.records[0].project_id == "p"


def test_router_preserves_s3_test_event_acknowledgement() -> None:
    routed = _router().route(
        json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent"})
    )
    assert routed.is_test_event is True
    assert routed.records == ()


def test_router_reports_openvidu_body_when_openvidu_is_disabled() -> None:
    with pytest.raises(UnsupportedMessageError) as excinfo:
        _router(openvidu=False).route(_body())
    assert "OpenVidu" in str(excinfo.value)


def test_router_rejects_unknown_contract_with_the_observed_keys() -> None:
    with pytest.raises(UnsupportedMessageError) as excinfo:
        _router().route(json.dumps({"foo": 1, "bar": 2}))
    message = str(excinfo.value)
    assert "no known message contract" in message
    assert "bar" in message and "foo" in message


def test_router_rejects_invalid_json() -> None:
    with pytest.raises(UnsupportedMessageError):
        _router().route("not-json")


# ------------------------------------------------------------------ config ---


def test_legacy_openvidu_worker_needs_bucket_and_explicit_flag(
    monkeypatch,
) -> None:
    """OpenVidu ingestion is opt-in; deploying this change changes nothing."""

    from data_pipeline.worker.config import load_worker_settings

    monkeypatch.delenv("OPENVIDU_RECORDING_BUCKET", raising=False)
    assert load_worker_settings().openvidu_enabled is False

    monkeypatch.setenv("OPENVIDU_RECORDING_BUCKET", "projectree-bucket")
    settings = load_worker_settings()
    assert settings.openvidu_enabled is False

    monkeypatch.setenv("ENABLE_LEGACY_OPENVIDU_AUDIO_WORKER", "true")
    settings = load_worker_settings()
    assert settings.openvidu_enabled is True
    assert settings.openvidu_recording_prefix == "meetings/"
    assert settings.openvidu_supported_kinds == ("MIXED",)


def test_openvidu_recording_prefix_is_normalized(monkeypatch) -> None:
    from data_pipeline.worker.config import load_worker_settings

    monkeypatch.setenv("OPENVIDU_RECORDING_BUCKET", "b")
    monkeypatch.setenv("OPENVIDU_RECORDING_PREFIX", "recordings")
    assert load_worker_settings().openvidu_recording_prefix == "recordings/"


# ------------------------------------------------------------------ worker ---


class _FakeSqs:
    def __init__(self, bodies: list[str]):
        self._bodies = list(bodies)
        self.deleted: list[dict] = []
        self.visibility: list[dict] = []
        self.receives = 0

    def receive_message(self, **kwargs):
        self.receives += 1
        if not self._bodies:
            return {}
        return {
            "Messages": [
                {
                    "MessageId": f"message-{self.receives}",
                    "ReceiptHandle": f"receipt-{self.receives}",
                    "Body": self._bodies.pop(0),
                }
            ]
        }

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    def change_message_visibility(self, **kwargs):
        self.visibility.append(kwargs)


def _worker(session_factory, *, sqs, s3, resolver=None, transcriber=None,
            heartbeat_interval_seconds: float = 0,
            heartbeat_max_extensions: int = 0) -> SqsAudioWorker:
    s3_parser = S3EventParser(allowed_buckets=frozenset({BUCKET}))
    return SqsAudioWorker(
        sqs_client=sqs,
        queue_url="https://sqs.invalid/test",
        parser=s3_parser,
        router=SqsMessageRouter(
            s3_parser=s3_parser,
            openvidu_parser=_parser(),
            openvidu_adapter=_adapter(s3, resolver),
        ),
        downloader=S3TemporaryDownloader(s3, max_audio_bytes=1024 * 1024),
        session_factory=session_factory,
        transcriber=transcriber or FakeTranscriber(),
        llm_client_factory=lambda record: FakeMeetingChatClient(
            record.external_meeting_id
        ),
        wait_time_seconds=1,
        visibility_timeout_seconds=30,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        heartbeat_max_extensions=heartbeat_max_extensions,
        upload_processing_timeout_seconds=60,
    )


def test_worker_processes_an_openvidu_message_end_to_end(session_factory) -> None:
    sqs = _FakeSqs([_body()])
    s3 = _FakeHeadS3({KEY: OGG})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.received == 1
    assert result.deleted == 1
    assert result.failed == 0
    assert len(sqs.deleted) == 1
    assert s3.download_calls and s3.download_calls[0][1] == KEY
    with session_factory() as session:
        upload = session.execute(select(AudioUploadEvent)).scalar_one()
        request = session.execute(select(Request)).scalar_one()
        assert upload.status == "COMPLETED"
        assert upload.bucket == BUCKET
        assert upload.object_key == KEY
        assert upload.upload_id == EGRESS
        assert upload.identity_kind == "ETAG"
        assert upload.pipeline_status == "REVIEW_PENDING"
        assert request.project_id == PROJECT
        assert request.external_meeting_id == MEETING


def test_worker_still_processes_s3_events_when_openvidu_is_enabled(
    session_factory,
) -> None:
    """The regression surface of this change: S3 ingestion with the router on.

    Existing worker tests construct SqsAudioWorker without a router, so this is
    the only end-to-end cover for "S3 message + OpenVidu-enabled router".
    """

    s3_key = "audio-input/proj-9/meet-9/upload-9/take.ogg"
    s3_body = json.dumps(
        {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": BUCKET},
                        "object": {
                            "key": s3_key,
                            "size": len(OGG),
                            "eTag": "etag-s3",
                        },
                    },
                }
            ]
        }
    )
    sqs = _FakeSqs([s3_body])
    s3 = _FakeHeadS3({s3_key: OGG})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 1
    assert result.failed == 0
    # The S3 path must not consult HeadObject or the OpenVidu resolver at all.
    assert s3.head_calls == []
    assert s3.download_calls and s3.download_calls[0][1] == s3_key
    with session_factory() as session:
        upload = session.execute(select(AudioUploadEvent)).scalar_one()
        request = session.execute(select(Request)).scalar_one()
        assert upload.object_key == s3_key
        assert upload.project_id == "proj-9"
        assert upload.external_meeting_id == "meet-9"
        assert upload.upload_id == "upload-9"
        assert upload.status == "COMPLETED"
        assert request.project_id == "proj-9"


def test_worker_does_not_delete_an_unparseable_openvidu_message(
    session_factory,
) -> None:
    sqs = _FakeSqs([_body(kind="INDIVIDUAL")])
    s3 = _FakeHeadS3({KEY: OGG})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 0
    assert result.failed == 1
    assert sqs.deleted == []
    with session_factory() as session:
        assert session.execute(select(AudioUploadEvent)).scalars().all() == []


def test_worker_does_not_delete_when_the_room_is_unmapped(session_factory) -> None:
    sqs = _FakeSqs([_body()])
    s3 = _FakeHeadS3({KEY: OGG})

    result = _worker(
        session_factory, sqs=sqs, s3=s3, resolver=StaticMeetingContextResolver({})
    ).poll_once()

    assert result.deleted == 0
    assert result.failed == 1
    assert sqs.deleted == []


def test_worker_does_not_delete_when_head_object_is_denied(session_factory) -> None:
    sqs = _FakeSqs([_body()])
    s3 = _FakeHeadS3({}, head_error=RuntimeError("403 Forbidden"))

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 0
    assert result.failed == 1
    assert sqs.deleted == []


def test_worker_does_not_delete_when_download_content_is_not_audio(
    session_factory,
) -> None:
    sqs = _FakeSqs([_body()])
    s3 = _FakeHeadS3({KEY: b"not-an-ogg-file-at-all-xxxxxx"})

    result = _worker(session_factory, sqs=sqs, s3=s3).poll_once()

    assert result.deleted == 0
    assert result.failed == 1
    with session_factory() as session:
        upload = session.execute(select(AudioUploadEvent)).scalar_one()
        assert upload.status == "FAILED"
        assert upload.failure_code == "S3DownloadError"


def test_duplicate_openvidu_message_is_idempotent(session_factory) -> None:
    body = _body()
    sqs = _FakeSqs([body, body])
    s3 = _FakeHeadS3({KEY: OGG})
    worker = _worker(session_factory, sqs=sqs, s3=s3)

    first = worker.poll_once()
    second = worker.poll_once()

    assert first.deleted == second.deleted == 1
    assert len(sqs.deleted) == 2
    # The second delivery must not re-download, re-transcribe or re-run the LLM.
    assert len(s3.download_calls) == 1
    with session_factory() as session:
        assert len(session.execute(select(AudioUploadEvent)).scalars().all()) == 1
        assert len(session.execute(select(Request)).scalars().all()) == 1


def test_openvidu_processing_keeps_the_visibility_heartbeat(session_factory) -> None:
    import time

    class _SlowTranscriber:
        def __init__(self):
            self._inner = FakeTranscriber()

        def transcribe(self, audio_path: Path, *, meeting_id: str):
            time.sleep(0.25)
            return self._inner.transcribe(audio_path, meeting_id=meeting_id)

    sqs = _FakeSqs([_body()])
    s3 = _FakeHeadS3({KEY: OGG})
    worker = _worker(
        session_factory,
        sqs=sqs,
        s3=s3,
        transcriber=_SlowTranscriber(),
        heartbeat_interval_seconds=0.05,
        heartbeat_max_extensions=6,
    )

    result = worker.poll_once()

    assert result.deleted == 1
    assert sqs.visibility
    assert all(call["VisibilityTimeout"] == 30 for call in sqs.visibility)


def test_worker_temporary_file_is_removed_after_openvidu_processing(
    session_factory, tmp_path
) -> None:
    sqs = _FakeSqs([_body()])
    s3 = _FakeHeadS3({KEY: OGG})
    s3_parser = S3EventParser(allowed_buckets=frozenset({BUCKET}))
    worker = SqsAudioWorker(
        sqs_client=sqs,
        queue_url="https://sqs.invalid/test",
        parser=s3_parser,
        router=SqsMessageRouter(
            s3_parser=s3_parser,
            openvidu_parser=_parser(),
            openvidu_adapter=_adapter(s3),
        ),
        downloader=S3TemporaryDownloader(
            s3, max_audio_bytes=1024 * 1024, temp_directory=tmp_path
        ),
        session_factory=session_factory,
        transcriber=FakeTranscriber(),
        llm_client_factory=lambda record: FakeMeetingChatClient(
            record.external_meeting_id
        ),
        wait_time_seconds=1,
        visibility_timeout_seconds=30,
        heartbeat_interval_seconds=0,
        heartbeat_max_extensions=0,
        upload_processing_timeout_seconds=60,
    )

    assert worker.poll_once().deleted == 1
    assert list(tmp_path.iterdir()) == []
