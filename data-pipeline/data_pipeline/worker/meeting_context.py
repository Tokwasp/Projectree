"""Resolve an OpenVidu room to the internal (projectId, meetingId) pair.

An OpenVidu egress event carries only ``roomName``. The ingestion pipeline needs
both a ``projectId`` and an ``externalMeetingId`` to place a meeting in the
graph, and **neither can be derived from the event, the S3 key, or the file
name**. This module therefore defines the port; the concrete production adapter
belongs to whoever owns that mapping data.

Deliberately NOT provided: any implementation that invents a projectId (for
example by reusing ``roomName`` as the project). Guessing here would silently
write meetings into the wrong project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .errors import MeetingContextUnresolvedError


@dataclass(frozen=True)
class MeetingContext:
    """Internal identity of a recorded meeting."""

    project_id: str
    external_meeting_id: str

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id must not be blank")
        if not self.external_meeting_id.strip():
            raise ValueError("external_meeting_id must not be blank")
        if len(self.project_id) > 128 or len(self.external_meeting_id) > 128:
            raise ValueError(
                "project_id and external_meeting_id must be <= 128 characters"
            )


class MeetingContextResolver(Protocol):
    """Maps an OpenVidu room name to internal identifiers."""

    def resolve_by_openvidu_room(self, room_name: str) -> MeetingContext | None:
        """Return the context, or None when the room is unknown."""
        ...


class UnavailableMeetingContextResolver:
    """Default resolver: fails loudly because no mapping source is configured.

    This is the safe default. It keeps the OpenVidu ingestion path wired end to
    end while making it impossible to process a recording under a guessed
    project. The raised error is not retryable by itself - the message stays on
    the queue until the mapping source exists.
    """

    def resolve_by_openvidu_room(self, room_name: str) -> MeetingContext | None:
        del room_name
        raise MeetingContextUnresolvedError(
            "No OpenVidu room -> project/meeting mapping source is configured. "
            "Set one via MeetingContextResolver before enabling OpenVidu ingestion."
        )


class StaticMeetingContextResolver:
    """Resolver backed by an explicit operator-supplied mapping.

    Intended for controlled smoke tests and for unit tests. The mapping is data
    the operator states, never data this worker infers.
    """

    def __init__(self, mapping: dict[str, MeetingContext] | None = None):
        self._mapping = dict(mapping or {})

    @classmethod
    def from_pairs(cls, pairs: dict[str, tuple[str, str]]) -> "StaticMeetingContextResolver":
        return cls(
            {
                room: MeetingContext(
                    project_id=project_id,
                    external_meeting_id=meeting_id,
                )
                for room, (project_id, meeting_id) in pairs.items()
            }
        )

    def resolve_by_openvidu_room(self, room_name: str) -> MeetingContext | None:
        return self._mapping.get(room_name)


__all__ = [
    "MeetingContext",
    "MeetingContextResolver",
    "StaticMeetingContextResolver",
    "UnavailableMeetingContextResolver",
]
