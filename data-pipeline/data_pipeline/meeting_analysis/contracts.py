"""Strict wire contracts for Java analysis commands."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias


class AnalysisCommandValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MeetingAnalysisCommandMessage:
    command_id: uuid.UUID
    project_id: str
    meeting_id: str
    room_name: str
    generate_summary: bool
    generate_nodes: bool
    requested_at: datetime


@dataclass(frozen=True)
class NodeContentUpdateCommandMessage:
    command_id: uuid.UUID
    project_id: str
    node_id: uuid.UUID
    expected_node_version: int
    title: str | None
    content: str | None
    requested_by_member_id: str
    requested_at: datetime


@dataclass(frozen=True)
class NodeDeleteCommandMessage:
    """Seed Node ids for one logical delete; Python computes the closure."""

    command_id: uuid.UUID
    project_id: str
    node_ids: tuple[uuid.UUID, ...]
    expected_graph_version: int
    requested_by_member_id: str
    requested_at: datetime


JavaCommandMessage: TypeAlias = (
    MeetingAnalysisCommandMessage
    | NodeContentUpdateCommandMessage
    | NodeDeleteCommandMessage
)


class AnalysisCommandParser:
    """Parse commandSchemaVersion=1 without coercing booleans or identifiers."""

    def parse(self, body: str) -> MeetingAnalysisCommandMessage:
        payload = _json_object(body)
        return self.parse_payload(payload)

    def parse_payload(self, payload: dict) -> MeetingAnalysisCommandMessage:
        if type(payload.get("commandSchemaVersion")) is not int or payload.get(
            "commandSchemaVersion"
        ) != 1:
            raise AnalysisCommandValidationError(
                "commandSchemaVersion must be 1"
            )
        if payload.get("commandType") != "MEETING_ANALYSIS_REQUESTED":
            raise AnalysisCommandValidationError(
                "commandType must be MEETING_ANALYSIS_REQUESTED"
            )
        command_id = self._uuid(payload.get("commandId"), "commandId")
        project_id = self._positive_int(payload.get("projectId"), "projectId")
        requested_at = self._utc_datetime(payload.get("requestedAt"))
        nested = payload.get("payload")
        if not isinstance(nested, dict):
            raise AnalysisCommandValidationError("payload must be an object")
        meeting_id = self._positive_int(nested.get("meetingId"), "meetingId")
        room_name = str(self._uuid(nested.get("roomName"), "roomName"))
        generate_summary = self._boolean(nested.get("generateSummary"), "generateSummary")
        generate_nodes = self._boolean(nested.get("generateNodes"), "generateNodes")
        return MeetingAnalysisCommandMessage(
            command_id=command_id,
            project_id=project_id,
            meeting_id=meeting_id,
            room_name=room_name,
            generate_summary=generate_summary,
            generate_nodes=generate_nodes,
            requested_at=requested_at,
        )

    @staticmethod
    def _uuid(value: object, field: str) -> uuid.UUID:
        if not isinstance(value, str):
            raise AnalysisCommandValidationError(f"{field} must be a UUID string")
        try:
            parsed = uuid.UUID(value)
        except ValueError as exc:
            raise AnalysisCommandValidationError(
                f"{field} must be a UUID string"
            ) from exc
        if str(parsed) != value:
            raise AnalysisCommandValidationError(
                f"{field} must use canonical UUID text"
            )
        return parsed

    @staticmethod
    def _positive_int(value: object, field: str) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AnalysisCommandValidationError(
                f"{field} must be a positive JSON integer"
            )
        if value <= 0 or value > 2**63 - 1:
            raise AnalysisCommandValidationError(
                f"{field} is outside the positive signed 64-bit range"
            )
        return str(value)

    @staticmethod
    def _boolean(value: object, field: str) -> bool:
        if not isinstance(value, bool):
            raise AnalysisCommandValidationError(f"{field} must be boolean")
        return value

    @staticmethod
    def _utc_datetime(value: object) -> datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise AnalysisCommandValidationError(
                "requestedAt must be an ISO-8601 UTC timestamp ending in Z"
            )
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise AnalysisCommandValidationError(
                "requestedAt must be an ISO-8601 UTC timestamp"
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise AnalysisCommandValidationError("requestedAt must be UTC")
        return parsed.astimezone(timezone.utc)


class NodeContentUpdateCommandParser:
    """Strict parser for canonical Node title/content update commands."""

    def parse(self, body: str) -> NodeContentUpdateCommandMessage:
        payload = _json_object(body)
        return self.parse_payload(payload)

    def parse_payload(self, payload: dict) -> NodeContentUpdateCommandMessage:
        if type(payload.get("commandSchemaVersion")) is not int or payload.get(
            "commandSchemaVersion"
        ) != 1:
            raise AnalysisCommandValidationError(
                "commandSchemaVersion must be 1"
            )
        if payload.get("commandType") != "NODE_CONTENT_UPDATE_REQUESTED":
            raise AnalysisCommandValidationError(
                "commandType must be NODE_CONTENT_UPDATE_REQUESTED"
            )
        command_id = AnalysisCommandParser._uuid(
            payload.get("commandId"), "commandId"
        )
        project_id = AnalysisCommandParser._positive_int(
            payload.get("projectId"), "projectId"
        )
        requested_at = AnalysisCommandParser._utc_datetime(
            payload.get("requestedAt")
        )
        nested = payload.get("payload")
        if not isinstance(nested, dict):
            raise AnalysisCommandValidationError("payload must be an object")
        node_id = AnalysisCommandParser._uuid(nested.get("nodeId"), "nodeId")
        expected = nested.get("expectedNodeVersion")
        if (
            isinstance(expected, bool)
            or not isinstance(expected, int)
            or expected <= 0
            or expected > 2**31 - 1
        ):
            raise AnalysisCommandValidationError(
                "expectedNodeVersion must be a positive JSON integer"
            )
        title = nested.get("title")
        content = nested.get("content")
        if title is None and content is None:
            raise AnalysisCommandValidationError(
                "at least one of title or content must be non-null"
            )
        if title is not None:
            if not isinstance(title, str) or not title.strip():
                raise AnalysisCommandValidationError(
                    "title must be a non-blank string or null"
                )
            if len(title) > 255:
                raise AnalysisCommandValidationError(
                    "title must be at most 255 characters"
                )
        if content is not None:
            if not isinstance(content, str) or not content.strip():
                raise AnalysisCommandValidationError(
                    "content must be a non-blank string or null"
                )
            if len(content) > 65535:
                raise AnalysisCommandValidationError(
                    "content must be at most 65535 characters"
                )
        member_id = AnalysisCommandParser._positive_int(
            nested.get("requestedByMemberId"), "requestedByMemberId"
        )
        return NodeContentUpdateCommandMessage(
            command_id=command_id,
            project_id=project_id,
            node_id=node_id,
            expected_node_version=expected,
            title=title,
            content=content,
            requested_by_member_id=member_id,
            requested_at=requested_at,
        )


class NodeDeleteCommandParser:
    """Strict parser for Node logical delete commands.

    ``nodeIds`` is a delete *seed*: the effective set is derived from the
    authoritative PostgreSQL graph, so duplicates and already-included
    descendants sent by Java are accepted and deduplicated downstream.
    """

    def parse(self, body: str) -> NodeDeleteCommandMessage:
        payload = _json_object(body)
        return self.parse_payload(payload)

    def parse_payload(self, payload: dict) -> NodeDeleteCommandMessage:
        if type(payload.get("commandSchemaVersion")) is not int or payload.get(
            "commandSchemaVersion"
        ) != 1:
            raise AnalysisCommandValidationError(
                "commandSchemaVersion must be 1"
            )
        if payload.get("commandType") != "NODE_DELETE_REQUESTED":
            raise AnalysisCommandValidationError(
                "commandType must be NODE_DELETE_REQUESTED"
            )
        command_id = AnalysisCommandParser._uuid(
            payload.get("commandId"), "commandId"
        )
        project_id = AnalysisCommandParser._positive_int(
            payload.get("projectId"), "projectId"
        )
        requested_at = AnalysisCommandParser._utc_datetime(
            payload.get("requestedAt")
        )
        nested = payload.get("payload")
        if not isinstance(nested, dict):
            raise AnalysisCommandValidationError("payload must be an object")
        raw_ids = nested.get("nodeIds")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise AnalysisCommandValidationError(
                "nodeIds must be a non-empty array of UUID strings"
            )
        if len(raw_ids) > 10_000:
            raise AnalysisCommandValidationError(
                "nodeIds must contain at most 10000 entries"
            )
        node_ids = tuple(
            AnalysisCommandParser._uuid(value, "nodeIds") for value in raw_ids
        )
        expected = nested.get("expectedGraphVersion")
        # >= 0 is accepted on purpose: a stale or zero version must die as a
        # durable GRAPH_VERSION_CONFLICT rejection, not as an unparseable
        # message that loops in the command queue forever.
        if (
            isinstance(expected, bool)
            or not isinstance(expected, int)
            or expected < 0
            or expected > 2**31 - 1
        ):
            raise AnalysisCommandValidationError(
                "expectedGraphVersion must be a non-negative JSON integer"
            )
        member_id = AnalysisCommandParser._positive_int(
            nested.get("requestedByMemberId"), "requestedByMemberId"
        )
        return NodeDeleteCommandMessage(
            command_id=command_id,
            project_id=project_id,
            node_ids=node_ids,
            expected_graph_version=expected,
            requested_by_member_id=member_id,
            requested_at=requested_at,
        )


class JavaCommandParser:
    """Route one Java command envelope without weakening any subtype."""

    def __init__(self) -> None:
        self._meeting = AnalysisCommandParser()
        self._node_update = NodeContentUpdateCommandParser()
        self._node_delete = NodeDeleteCommandParser()

    def parse(self, body: str) -> JavaCommandMessage:
        payload = _json_object(body)
        command_type = payload.get("commandType")
        if command_type == "MEETING_ANALYSIS_REQUESTED":
            return self._meeting.parse_payload(payload)
        if command_type == "NODE_CONTENT_UPDATE_REQUESTED":
            return self._node_update.parse_payload(payload)
        if command_type == "NODE_DELETE_REQUESTED":
            return self._node_delete.parse_payload(payload)
        raise AnalysisCommandValidationError("unsupported commandType")


def _json_object(body: str) -> dict:
    try:
        payload = json.loads(body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AnalysisCommandValidationError(
            "analysis command body is not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise AnalysisCommandValidationError(
            "analysis command must be a JSON object"
        )
    return payload


__all__ = [
    "AnalysisCommandParser",
    "AnalysisCommandValidationError",
    "JavaCommandMessage",
    "JavaCommandParser",
    "MeetingAnalysisCommandMessage",
    "NodeContentUpdateCommandMessage",
    "NodeContentUpdateCommandParser",
    "NodeDeleteCommandMessage",
    "NodeDeleteCommandParser",
]
