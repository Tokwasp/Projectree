"""Parse OpenVidu/LiveKit egress completion events carried by SQS.

This is a second, explicit external contract alongside :mod:`s3_events`. It is
deliberately kept separate: an OpenVidu egress event is an *application* event,
not an S3 ObjectCreated notification, and it is never rewritten to look like one.

The observed production body (2026-07-31, queue ``muOpenviduQueue``) is::

    {"roomName": "<uuid>",
     "memberId": null,
     "kind": "MIXED",
     "objectKey": "meetings/<roomName>/mixed/<yyyy-MM-dd'T'HHmmss>.ogg",
     "egressId": "EG_XXXXXXXXXXXX",
     "endedAt": "2026-07-31T07:28:05.804108359"}

Only fields that were actually observed are modelled. Notably the event carries
no bucket, no size, no eTag/versionId and no projectId; those are supplied later
by :mod:`openvidu_ingest`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath

from .errors import OpenViduEventValidationError

#: ``kind`` values this worker is willing to process. Only ``MIXED`` has ever
#: been observed; anything else is rejected explicitly rather than guessed at.
DEFAULT_SUPPORTED_KINDS = frozenset({"MIXED"})

#: Keys that identify a body as an OpenVidu egress event for routing purposes.
DISCRIMINATOR_FIELDS = ("roomName", "objectKey", "egressId")


@dataclass(frozen=True)
class OpenViduEgressEvent:
    """One completed OpenVidu egress recording."""

    room_name: str
    object_key: str
    egress_id: str
    kind: str
    member_id: str | None
    #: Verbatim ``endedAt`` string. It carries no timezone offset, so it is kept
    #: as text for traceability and never parsed into an instant.
    ended_at_raw: str | None

    @property
    def filename(self) -> str:
        return PurePosixPath(self.object_key).name


@dataclass(frozen=True)
class OpenViduEgressEventParser:
    """Validate an OpenVidu egress body without touching AWS."""

    recording_prefix: str = "meetings/"
    allowed_extensions: frozenset[str] = frozenset(
        {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
    )
    supported_kinds: frozenset[str] = DEFAULT_SUPPORTED_KINDS

    def __post_init__(self) -> None:
        if not self.recording_prefix or not self.recording_prefix.endswith("/"):
            raise ValueError(
                "OpenVidu recording prefix must be non-empty and end with '/'"
            )
        if not self.allowed_extensions:
            raise ValueError("At least one audio extension must be allowed")
        if not self.supported_kinds:
            raise ValueError("At least one egress kind must be supported")

    def parse(self, body: str) -> OpenViduEgressEvent:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise OpenViduEventValidationError(
                "OpenVidu egress body is not valid JSON"
            ) from exc
        return self.parse_payload(payload)

    def parse_payload(self, payload: object) -> OpenViduEgressEvent:
        if not isinstance(payload, dict):
            raise OpenViduEventValidationError(
                "OpenVidu egress event must be a JSON object"
            )

        # roomName and egressId are bounded at 128 because they reach
        # audio_upload_event columns declared String(128); a longer value would
        # only fail at COMMIT time on PostgreSQL, after Clova and the LLM ran.
        room_name = self._required_text(payload, "roomName", max_length=128)
        egress_id = self._required_text(payload, "egressId", max_length=128)
        object_key = self._required_text(payload, "objectKey", max_length=1024)

        kind = payload.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise OpenViduEventValidationError(
                "OpenVidu egress event has no kind"
            )
        kind = kind.strip()
        if kind not in self.supported_kinds:
            raise OpenViduEventValidationError(
                f"OpenVidu egress kind is not supported: {kind}"
            )

        member_id = payload.get("memberId")
        if member_id is not None and (
            not isinstance(member_id, str) or not member_id.strip()
        ):
            raise OpenViduEventValidationError(
                "OpenVidu egress memberId must be a non-empty string or null"
            )

        ended_at = payload.get("endedAt")
        if ended_at is not None and not isinstance(ended_at, str):
            raise OpenViduEventValidationError(
                "OpenVidu egress endedAt must be a string when present"
            )

        self._validate_object_key(object_key, room_name=room_name)

        return OpenViduEgressEvent(
            room_name=room_name,
            object_key=object_key,
            egress_id=egress_id,
            kind=kind,
            member_id=member_id.strip() if isinstance(member_id, str) else None,
            ended_at_raw=ended_at,
        )

    @staticmethod
    def _required_text(payload: dict, field: str, *, max_length: int) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise OpenViduEventValidationError(
                f"OpenVidu egress event has no {field}"
            )
        value = value.strip()
        if len(value) > max_length:
            raise OpenViduEventValidationError(
                f"OpenVidu egress event {field} is too long"
            )
        return value

    def _validate_object_key(self, object_key: str, *, room_name: str) -> None:
        # The key is used verbatim as an S3 key; it is not URL-encoded by this
        # producer, unlike an S3 event notification key. Validate the RAW split
        # rather than PurePosixPath.parts: PurePosixPath collapses "." segments,
        # but S3 treats "a/./b" and "a/b" as two distinct keys, so a normalized
        # view would validate a key that is not the key we would fetch.
        if "\\" in object_key:
            raise OpenViduEventValidationError(
                "OpenVidu objectKey must not contain a backslash"
            )
        parts = tuple(object_key.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            raise OpenViduEventValidationError(
                "OpenVidu objectKey must not contain empty or relative path segments"
            )
        prefix_parts = tuple(self.recording_prefix.rstrip("/").split("/"))
        if parts[: len(prefix_parts)] != prefix_parts:
            raise OpenViduEventValidationError(
                "OpenVidu objectKey is outside the configured recording prefix"
            )
        if len(parts) <= len(prefix_parts):
            raise OpenViduEventValidationError(
                "OpenVidu objectKey has no object name under the prefix"
            )
        # The room segment must match roomName. The project/meeting context is
        # resolved from roomName while the audio is fetched from objectKey; if
        # the two disagree, one room's recording would be transcribed into
        # another room's project. The producer always emits them equal, so a
        # mismatch means a malformed or forged message.
        if parts[len(prefix_parts)] != room_name:
            raise OpenViduEventValidationError(
                "OpenVidu objectKey room segment does not match roomName"
            )
        suffix = PurePosixPath(parts[-1]).suffix.lower()
        if suffix not in self.allowed_extensions:
            raise OpenViduEventValidationError(
                "OpenVidu objectKey has a disallowed audio extension"
            )


def looks_like_openvidu_egress(payload: object) -> bool:
    """Cheap discriminator used by the router; does not validate the event."""

    return isinstance(payload, dict) and all(
        field in payload for field in DISCRIMINATOR_FIELDS
    )


__all__ = [
    "DEFAULT_SUPPORTED_KINDS",
    "DISCRIMINATOR_FIELDS",
    "OpenViduEgressEvent",
    "OpenViduEgressEventParser",
    "looks_like_openvidu_egress",
]
