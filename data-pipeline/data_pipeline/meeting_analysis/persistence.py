"""Short DB transactions for the two input queues and their join state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from data_pipeline.storage import (
    MeetingAnalysisCommand,
    MeetingAnalysisTask,
    RecordingReadyEvent,
)
from .contracts import MeetingAnalysisCommandMessage

if TYPE_CHECKING:
    from data_pipeline.worker.openvidu_events import OpenViduEgressEvent
else:
    OpenViduEgressEvent = Any


class RecordingPayloadConflictError(RuntimeError):
    pass


class CommandPayloadConflictError(RuntimeError):
    pass


def _canonical_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _command_hash(command: MeetingAnalysisCommandMessage) -> str:
    return _canonical_hash(
        {
            "commandId": str(command.command_id),
            "projectId": command.project_id,
            "meetingId": command.meeting_id,
            "roomName": command.room_name,
            "generateSummary": command.generate_summary,
            "generateNodes": command.generate_nodes,
            "requestedAt": command.requested_at.isoformat(),
        }
    )


def _recording_identity(event: OpenViduEgressEvent, bucket: str) -> tuple:
    return (
        event.project_id,
        event.room_name,
        event.egress_id,
        bucket,
        event.object_key,
        event.kind,
    )


def _task_status(selected: bool, ready: bool) -> str:
    if not selected:
        return "SKIPPED"
    return "READY" if ready else "WAITING_INPUT"


def _join(session, *, project_id: str, room_name: str) -> bool:
    command = session.execute(
        select(MeetingAnalysisCommand)
        .where(
            MeetingAnalysisCommand.project_id == project_id,
            MeetingAnalysisCommand.room_name == room_name,
            MeetingAnalysisCommand.status.in_(["WAITING_FOR_RECORDING", "READY"]),
        )
        .with_for_update()
    ).scalar_one_or_none()
    recording = session.execute(
        select(RecordingReadyEvent)
        .where(
            RecordingReadyEvent.project_id == project_id,
            RecordingReadyEvent.room_name == room_name,
            RecordingReadyEvent.status.in_(["WAITING_FOR_COMMAND", "READY"]),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if command is None or recording is None:
        return False
    command.status = "READY"
    recording.status = "READY"
    for task in session.execute(
        select(MeetingAnalysisTask).where(
            MeetingAnalysisTask.command_id == command.command_id,
            MeetingAnalysisTask.status == "WAITING_INPUT",
        )
    ).scalars():
        task.status = "READY"
        task.available_at = datetime.now(timezone.utc)
    return True


def persist_recording_ready(
    session_factory,
    *,
    event: OpenViduEgressEvent,
    recording_bucket: str,
) -> tuple[RecordingReadyEvent, bool]:
    """Persist and ACK-safe join one recording; return (row, created)."""

    if not recording_bucket.strip():
        raise ValueError("recording_bucket must not be blank")
    session = session_factory()
    try:
        existing = session.execute(
            select(RecordingReadyEvent).where(
                (RecordingReadyEvent.egress_id == event.egress_id)
                | (
                    (RecordingReadyEvent.recording_bucket == recording_bucket)
                    & (RecordingReadyEvent.object_key == event.object_key)
                )
            )
        ).scalars().all()
        if existing:
            row = existing[0]
            actual = (
                row.project_id,
                row.room_name,
                row.egress_id,
                row.recording_bucket,
                row.object_key,
                row.kind,
            )
            if actual != _recording_identity(event, recording_bucket):
                raise RecordingPayloadConflictError(
                    "recording egress/object identity was reused with another payload"
                )
            session.rollback()
            return row, False
        row = RecordingReadyEvent(
            project_id=event.project_id,
            room_name=event.room_name,
            egress_id=event.egress_id,
            kind=event.kind,
            member_id=event.member_id,
            recording_bucket=recording_bucket,
            object_key=event.object_key,
            ended_at_raw=event.ended_at_raw,
            status="WAITING_FOR_COMMAND",
        )
        session.add(row)
        session.flush()
        _join(session, project_id=event.project_id, room_name=event.room_name)
        session.commit()
        return row, True
    except IntegrityError:
        session.rollback()
        # A concurrent winner is safe only if its full identity is identical.
        return persist_recording_ready(
            session_factory,
            event=event,
            recording_bucket=recording_bucket,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def persist_analysis_command(
    session_factory,
    *,
    command: MeetingAnalysisCommandMessage,
) -> tuple[MeetingAnalysisCommand, bool]:
    """Persist one command and exactly two task rows, then attempt the join."""

    payload_hash = _command_hash(command)
    session = session_factory()
    try:
        existing = session.execute(
            select(MeetingAnalysisCommand).where(
                (MeetingAnalysisCommand.command_id == command.command_id)
                | (
                    (MeetingAnalysisCommand.project_id == command.project_id)
                    & (MeetingAnalysisCommand.meeting_id == command.meeting_id)
                )
            )
        ).scalars().all()
        if existing:
            row = existing[0]
            if row.command_id != command.command_id or row.payload_hash != payload_hash:
                raise CommandPayloadConflictError(
                    "commandId or project/meeting identity was reused with another payload"
                )
            session.rollback()
            return row, False
        recording_exists = session.execute(
            select(RecordingReadyEvent.id).where(
                RecordingReadyEvent.project_id == command.project_id,
                RecordingReadyEvent.room_name == command.room_name,
                RecordingReadyEvent.status.in_(["WAITING_FOR_COMMAND", "READY"]),
            )
        ).scalar_one_or_none() is not None
        row = MeetingAnalysisCommand(
            command_id=command.command_id,
            project_id=command.project_id,
            meeting_id=command.meeting_id,
            room_name=command.room_name,
            generate_summary=command.generate_summary,
            generate_nodes=command.generate_nodes,
            requested_at=command.requested_at,
            status="READY" if recording_exists else "WAITING_FOR_RECORDING",
            payload_hash=payload_hash,
        )
        session.add(row)
        session.flush()
        for task_type, selected in (
            ("SUMMARY", command.generate_summary),
            ("NODES", command.generate_nodes),
        ):
            session.add(
                MeetingAnalysisTask(
                    command_id=command.command_id,
                    task_type=task_type,
                    status=_task_status(selected, recording_exists),
                )
            )
        session.flush()
        _join(session, project_id=command.project_id, room_name=command.room_name)
        session.commit()
        return row, True
    except IntegrityError:
        session.rollback()
        return persist_analysis_command(session_factory, command=command)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "CommandPayloadConflictError",
    "RecordingPayloadConflictError",
    "persist_analysis_command",
    "persist_recording_ready",
]
