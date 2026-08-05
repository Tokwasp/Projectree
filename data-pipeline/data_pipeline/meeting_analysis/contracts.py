"""Strict wire contracts for Java analysis commands."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


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


class AnalysisCommandParser:
    """Parse commandSchemaVersion=1 without coercing booleans or identifiers."""

    def parse(self, body: str) -> MeetingAnalysisCommandMessage:
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
        if payload.get("commandSchemaVersion") != 1:
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
        if str(parsed) != value.lower():
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


__all__ = [
    "AnalysisCommandParser",
    "AnalysisCommandValidationError",
    "MeetingAnalysisCommandMessage",
]
