"""Turn an OpenVidu egress event into the worker's internal S3ObjectRecord.

The OpenVidu contract is missing everything the download and idempotency layers
need, so this adapter fills the gaps from authoritative sources:

    bucket                      <- configuration (the event carries none)
    size / eTag / versionId     <- S3 HeadObject (the event carries none)
    projectId / meetingId       <- MeetingContextResolver (the event carries none)
    uploadId                    <- egressId (stable per recording job)

By producing the same :class:`S3ObjectRecord` the S3-event path produces, the
downloader, the ``audio_upload_event`` claim/idempotency logic and the pipeline
runner are all reused unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .errors import (
    MeetingContextUnresolvedError,
    S3MetadataError,
)
from .meeting_context import MeetingContextResolver
from .openvidu_events import OpenViduEgressEvent
from .s3_events import S3ObjectRecord


class S3HeadClient(Protocol):
    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...


def _normalize_etag(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().strip('"')
    return cleaned or None


@dataclass(frozen=True)
class OpenViduIngestAdapter:
    """Resolve an OpenVidu egress event into a downloadable S3 object record."""

    s3_client: S3HeadClient
    resolver: MeetingContextResolver
    bucket: str
    max_audio_bytes: int

    def __post_init__(self) -> None:
        if not self.bucket:
            raise ValueError("OpenVidu recording bucket is required")
        if self.max_audio_bytes <= 0:
            raise ValueError("max_audio_bytes must be positive")

    def to_record(self, event: OpenViduEgressEvent) -> S3ObjectRecord:
        context = self._resolve_context(event)
        head = self._head_object(event)

        size = head.get("ContentLength")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise S3MetadataError(
                "S3 HeadObject returned an invalid ContentLength"
            )
        if size > self.max_audio_bytes:
            raise S3MetadataError(
                "OpenVidu recording exceeds the configured audio size limit"
            )

        version_id = head.get("VersionId")
        version_id = (
            version_id.strip()
            if isinstance(version_id, str) and version_id.strip()
            else None
        )
        etag = _normalize_etag(head.get("ETag"))
        if version_id is None and etag is None:
            raise S3MetadataError(
                "S3 HeadObject returned neither VersionId nor ETag; "
                "the upload cannot be made idempotent"
            )

        return S3ObjectRecord(
            bucket=self.bucket,
            object_key=event.object_key,
            version_id=version_id,
            etag=etag,
            size=size,
            project_id=context.project_id,
            external_meeting_id=context.external_meeting_id,
            upload_id=event.egress_id,
            filename=event.filename,
        )

    def _resolve_context(self, event: OpenViduEgressEvent):
        context = self.resolver.resolve_by_openvidu_room(event.room_name)
        if context is None:
            raise MeetingContextUnresolvedError(
                "OpenVidu room is not mapped to a project/meeting pair"
            )
        return context

    def _head_object(self, event: OpenViduEgressEvent) -> dict[str, Any]:
        try:
            return self.s3_client.head_object(
                Bucket=self.bucket,
                Key=event.object_key,
            )
        except Exception as exc:
            raise S3MetadataError(
                "S3 HeadObject failed for the OpenVidu recording"
            ) from exc


__all__ = ["OpenViduIngestAdapter", "S3HeadClient"]
