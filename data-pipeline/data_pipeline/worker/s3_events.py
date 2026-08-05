"""Parse and validate S3 event notifications carried by SQS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote_plus

from .errors import S3EventValidationError


@dataclass(frozen=True)
class S3ObjectRecord:
    bucket: str
    object_key: str
    version_id: str | None
    etag: str | None
    size: int
    project_id: str
    external_meeting_id: str
    upload_id: str
    filename: str

    @property
    def object_identity(self) -> str:
        return self.version_id or self.etag or ""

    @property
    def identity_kind(self) -> str:
        return "VERSION_ID" if self.version_id else "ETAG"


@dataclass(frozen=True)
class ParsedS3Message:
    records: tuple[S3ObjectRecord, ...]
    is_test_event: bool = False


@dataclass(frozen=True)
class S3EventParser:
    allowed_buckets: frozenset[str]
    input_prefix: str = "audio-input/"
    allowed_extensions: frozenset[str] = frozenset(
        {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
    )
    max_audio_bytes: int = 100 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.allowed_buckets:
            raise ValueError("At least one S3 bucket must be allowed")
        if not self.input_prefix or not self.input_prefix.endswith("/"):
            raise ValueError("S3 input prefix must be non-empty and end with '/'")
        if self.max_audio_bytes <= 0:
            raise ValueError("S3 max audio size must be positive")

    def parse(self, body: str) -> ParsedS3Message:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise S3EventValidationError("SQS body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise S3EventValidationError("S3 event must be a JSON object")

        if payload.get("Event") == "s3:TestEvent":
            return ParsedS3Message(records=(), is_test_event=True)

        raw_records = payload.get("Records")
        if not isinstance(raw_records, list) or not raw_records:
            raise S3EventValidationError(
                "S3 event Records must be a non-empty array"
            )
        return ParsedS3Message(
            records=tuple(
                self._parse_record(raw, index=index)
                for index, raw in enumerate(raw_records, start=1)
            )
        )

    def _parse_record(self, raw: object, *, index: int) -> S3ObjectRecord:
        if not isinstance(raw, dict):
            raise S3EventValidationError(f"S3 Record {index} must be an object")
        event_name = raw.get("eventName")
        if not isinstance(event_name, str) or not (
            event_name.startswith("ObjectCreated:")
            or event_name.startswith("s3:ObjectCreated:")
        ):
            raise S3EventValidationError(
                f"S3 Record {index} is not an ObjectCreated event"
            )
        s3 = raw.get("s3")
        if not isinstance(s3, dict):
            raise S3EventValidationError(f"S3 Record {index} is missing s3")
        bucket_data = s3.get("bucket")
        object_data = s3.get("object")
        if not isinstance(bucket_data, dict) or not isinstance(object_data, dict):
            raise S3EventValidationError(
                f"S3 Record {index} is missing bucket or object"
            )

        bucket = bucket_data.get("name")
        encoded_key = object_data.get("key")
        if not isinstance(bucket, str) or not bucket:
            raise S3EventValidationError(
                f"S3 Record {index} has no bucket name"
            )
        if bucket not in self.allowed_buckets:
            raise S3EventValidationError(
                f"S3 Record {index} uses a disallowed bucket"
            )
        if not isinstance(encoded_key, str) or not encoded_key:
            raise S3EventValidationError(
                f"S3 Record {index} has no object key"
            )

        object_key = unquote_plus(encoded_key)
        key_parts = PurePosixPath(object_key).parts
        prefix_parts = PurePosixPath(self.input_prefix.rstrip("/")).parts
        if (
            "\\" in object_key
            or any(part in {"", ".", ".."} for part in key_parts)
            or tuple(key_parts[: len(prefix_parts)]) != prefix_parts
            or len(key_parts) != len(prefix_parts) + 4
        ):
            raise S3EventValidationError(
                f"S3 Record {index} does not match the object key contract"
            )
        project_id, meeting_id, upload_id, filename = key_parts[-4:]
        if any(not value.strip() for value in (project_id, meeting_id, upload_id, filename)):
            raise S3EventValidationError(
                f"S3 Record {index} has an empty key identifier"
            )
        if len(project_id) > 128 or len(meeting_id) > 128 or len(upload_id) > 128:
            raise S3EventValidationError(
                f"S3 Record {index} key identifier is too long"
            )
        suffix = PurePosixPath(filename).suffix.lower()
        if suffix not in self.allowed_extensions:
            raise S3EventValidationError(
                f"S3 Record {index} has a disallowed audio extension"
            )

        size = object_data.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise S3EventValidationError(
                f"S3 Record {index} has an invalid object size"
            )
        if size > self.max_audio_bytes:
            raise S3EventValidationError(
                f"S3 Record {index} exceeds the audio size limit"
            )

        version_id = object_data.get("versionId")
        etag = object_data.get("eTag")
        version_id = (
            version_id.strip()
            if isinstance(version_id, str) and version_id.strip()
            else None
        )
        etag = (
            etag.strip().strip('"')
            if isinstance(etag, str) and etag.strip().strip('"')
            else None
        )
        if version_id is None and etag is None:
            raise S3EventValidationError(
                f"S3 Record {index} needs versionId or eTag"
            )

        return S3ObjectRecord(
            bucket=bucket,
            object_key=object_key,
            version_id=version_id,
            etag=etag,
            size=size,
            project_id=project_id,
            external_meeting_id=meeting_id,
            upload_id=upload_id,
            filename=filename,
        )


__all__ = ["ParsedS3Message", "S3EventParser", "S3ObjectRecord"]
