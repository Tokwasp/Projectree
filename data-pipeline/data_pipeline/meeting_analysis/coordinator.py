"""DB coordinator: join durable inputs, share STT, run tasks independently."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from sqlalchemy import select

from data_pipeline.storage import (
    MeetingAnalysisCommand,
    MeetingAnalysisTask,
    RecordingReadyEvent,
)

from .result_events import stage_task_failed_v3
from .task_errors import TaskProcessingError


class TranscriptLoader(Protocol):
    def __call__(
        self,
        command: MeetingAnalysisCommand,
        recording: RecordingReadyEvent,
    ) -> object: ...


TaskProcessor = Callable[[MeetingAnalysisCommand, RecordingReadyEvent, object], None]


@dataclass(frozen=True)
class CoordinatorRunResult:
    claimed: bool
    command_id: uuid.UUID | None
    transcript_loads: int
    succeeded: tuple[str, ...]
    retrying: tuple[str, ...]
    failed: tuple[str, ...]


@dataclass(frozen=True)
class _Claim:
    command_id: uuid.UUID
    recording_id: uuid.UUID
    claim_token: uuid.UUID
    task_types: tuple[str, ...]


class MeetingAnalysisCoordinator:
    def __init__(
        self,
        *,
        session_factory,
        transcript_loader: TranscriptLoader,
        summary_processor: TaskProcessor,
        nodes_processor: TaskProcessor,
        claim_timeout_seconds: float = 900.0,
    ) -> None:
        self._session_factory = session_factory
        self._transcript_loader = transcript_loader
        self._processors = {
            "SUMMARY": summary_processor,
            "NODES": nodes_processor,
        }
        self._claim_timeout = timedelta(seconds=claim_timeout_seconds)

    def run_once(self) -> CoordinatorRunResult:
        claim = self._claim_ready()
        if claim is None:
            return CoordinatorRunResult(False, None, 0, (), (), ())
        command, recording = self._load_inputs(claim)
        if not claim.task_types:
            self._finish_inputs_if_terminal(claim.command_id, claim.recording_id)
            return CoordinatorRunResult(True, claim.command_id, 0, (), (), ())
        try:
            transcript = self._transcript_loader(command, recording)
        except Exception as exc:
            retrying: list[str] = []
            failed: list[str] = []
            for task_type in claim.task_types:
                terminal = self._record_failure(
                    claim,
                    task_type=task_type,
                    error=exc,
                    failure_code="STT_FAILED",
                )
                (failed if terminal else retrying).append(task_type)
            self._finish_inputs_if_terminal(claim.command_id, claim.recording_id)
            return CoordinatorRunResult(
                True,
                claim.command_id,
                1,
                (),
                tuple(retrying),
                tuple(failed),
            )

        outcomes: dict[str, str] = {}
        with ThreadPoolExecutor(
            max_workers=len(claim.task_types),
            thread_name_prefix="meeting-analysis",
        ) as executor:
            futures = {
                executor.submit(
                    self._processors[task_type],
                    command,
                    recording,
                    transcript,
                ): task_type
                for task_type in claim.task_types
            }
            for future in as_completed(futures):
                task_type = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    if isinstance(exc, TaskProcessingError):
                        failure_code = exc.failure_code
                        retryable = exc.retryable
                        emit_failure_event = exc.emit_failure_event
                    else:
                        failure_code = (
                            "SUMMARY_GENERATION_FAILED"
                            if task_type == "SUMMARY"
                            else f"{task_type}_FAILED"
                        )
                        retryable = True
                        emit_failure_event = True
                    terminal = self._record_failure(
                        claim,
                        task_type=task_type,
                        error=exc,
                        failure_code=failure_code,
                        retryable=retryable,
                        emit_failure_event=emit_failure_event,
                    )
                    outcomes[task_type] = "failed" if terminal else "retrying"
                else:
                    self._record_success(claim, task_type=task_type)
                    outcomes[task_type] = "succeeded"
        self._finish_inputs_if_terminal(claim.command_id, claim.recording_id)
        return CoordinatorRunResult(
            True,
            claim.command_id,
            1,
            tuple(
                task_type
                for task_type in claim.task_types
                if outcomes[task_type] == "succeeded"
            ),
            tuple(
                task_type
                for task_type in claim.task_types
                if outcomes[task_type] == "retrying"
            ),
            tuple(
                task_type
                for task_type in claim.task_types
                if outcomes[task_type] == "failed"
            ),
        )

    def _claim_ready(self) -> _Claim | None:
        session = self._session_factory()
        try:
            now = datetime.now(timezone.utc)
            stale_before = now - self._claim_timeout
            statement = (
                select(MeetingAnalysisCommand)
                .where(
                    MeetingAnalysisCommand.status.in_(["READY", "PROCESSING"]),
                )
                .order_by(MeetingAnalysisCommand.requested_at)
                .with_for_update(skip_locked=True)
            )
            commands = list(session.execute(statement).scalars())
            for command in commands:
                recording = session.execute(
                    select(RecordingReadyEvent)
                    .where(
                        RecordingReadyEvent.project_id == command.project_id,
                        RecordingReadyEvent.room_name == command.room_name,
                        RecordingReadyEvent.status.in_(["READY", "PROCESSING"]),
                    )
                    .with_for_update(skip_locked=True)
                ).scalar_one_or_none()
                if recording is None:
                    continue
                tasks = list(
                    session.execute(
                        select(MeetingAnalysisTask)
                        .where(MeetingAnalysisTask.command_id == command.command_id)
                        .order_by(MeetingAnalysisTask.task_type)
                        .with_for_update()
                    ).scalars()
                )
                claimable = [
                    task
                    for task in tasks
                    if task.status == "READY"
                    or (
                        task.status == "PROCESSING"
                        and task.claimed_at is not None
                        and task.claimed_at < stale_before
                    )
                ]
                if not claimable and not all(
                    task.status == "SKIPPED" for task in tasks
                ):
                    continue
                token = uuid.uuid4()
                for task in claimable:
                    task.status = "PROCESSING"
                    task.claim_token = token
                    task.claimed_at = now
                    task.attempt_count += 1
                    task.failure_code = None
                    task.last_error = None
                command.status = "PROCESSING"
                recording.status = "PROCESSING"
                session.commit()
                return _Claim(
                    command_id=command.command_id,
                    recording_id=recording.id,
                    claim_token=token,
                    task_types=tuple(task.task_type for task in claimable),
                )
            session.rollback()
            return None
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _load_inputs(
        self,
        claim: _Claim,
    ) -> tuple[MeetingAnalysisCommand, RecordingReadyEvent]:
        session = self._session_factory()
        try:
            command = session.execute(
                select(MeetingAnalysisCommand).where(
                    MeetingAnalysisCommand.command_id == claim.command_id
                )
            ).scalar_one()
            recording = session.get(RecordingReadyEvent, claim.recording_id)
            if recording is None or (
                recording.project_id != command.project_id
                or recording.room_name != command.room_name
            ):
                raise RuntimeError("claimed recording no longer matches command")
            session.expunge(command)
            session.expunge(recording)
            return command, recording
        finally:
            session.close()

    def _record_success(self, claim: _Claim, *, task_type: str) -> None:
        session = self._session_factory()
        try:
            task = session.execute(
                select(MeetingAnalysisTask)
                .where(
                    MeetingAnalysisTask.command_id == claim.command_id,
                    MeetingAnalysisTask.task_type == task_type,
                    MeetingAnalysisTask.status == "PROCESSING",
                    MeetingAnalysisTask.claim_token == claim.claim_token,
                )
                .with_for_update()
            ).scalar_one()
            task.status = "SUCCEEDED"
            task.claim_token = None
            task.claimed_at = None
            task.updated_at = datetime.now(timezone.utc)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _record_failure(
        self,
        claim: _Claim,
        *,
        task_type: str,
        error: Exception,
        failure_code: str,
        retryable: bool = True,
        emit_failure_event: bool = True,
    ) -> bool:
        session = self._session_factory()
        try:
            task = session.execute(
                select(MeetingAnalysisTask)
                .where(
                    MeetingAnalysisTask.command_id == claim.command_id,
                    MeetingAnalysisTask.task_type == task_type,
                    MeetingAnalysisTask.status == "PROCESSING",
                    MeetingAnalysisTask.claim_token == claim.claim_token,
                )
                .with_for_update()
            ).scalar_one()
            task.claim_token = None
            task.claimed_at = None
            task.failure_code = failure_code
            task.last_error = f"{type(error).__name__}: {error}"[:2000]
            terminal = not retryable or task.attempt_count >= task.max_attempts
            if terminal:
                task.status = "FAILED"
                if emit_failure_event:
                    command = session.execute(
                        select(MeetingAnalysisCommand).where(
                            MeetingAnalysisCommand.command_id == claim.command_id
                        )
                    ).scalar_one()
                    stage_task_failed_v3(
                        session,
                        command=command,
                        task_type=task_type,
                        failure_code=failure_code,
                        failure_message=str(error),
                    )
            else:
                task.status = "READY"
                task.available_at = datetime.now(timezone.utc)
            task.updated_at = datetime.now(timezone.utc)
            session.commit()
            return terminal
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _finish_inputs_if_terminal(
        self,
        command_id: uuid.UUID,
        recording_id: uuid.UUID,
    ) -> None:
        session = self._session_factory()
        try:
            command = session.execute(
                select(MeetingAnalysisCommand)
                .where(MeetingAnalysisCommand.command_id == command_id)
                .with_for_update()
            ).scalar_one()
            recording = session.execute(
                select(RecordingReadyEvent)
                .where(RecordingReadyEvent.id == recording_id)
                .with_for_update()
            ).scalar_one()
            tasks = list(
                session.execute(
                    select(MeetingAnalysisTask).where(
                        MeetingAnalysisTask.command_id == command_id
                    )
                ).scalars()
            )
            if all(task.status in {"SUCCEEDED", "FAILED", "SKIPPED"} for task in tasks):
                command.status = "COMPLETED"
                recording.status = "COMPLETED"
            elif any(task.status == "READY" for task in tasks):
                command.status = "READY"
                recording.status = "READY"
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


__all__ = ["CoordinatorRunResult", "MeetingAnalysisCoordinator"]
