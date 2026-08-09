"""Adapters that connect the coordinator to existing S3/STT/graph services."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import select

from data_pipeline.meeting_summary import (
    PermanentMeetingRecordCallbackError,
    RetryableMeetingRecordCallbackError,
    build_callback_body,
    generate_meeting_summary,
)
from data_pipeline.pipeline.automatic_graph import run_automatic_meeting
from data_pipeline.pipeline.chain import normalize_transcript_segments
from data_pipeline.pipeline.repository import upsert_meeting, upsert_segments
from data_pipeline.storage import TranscriptSegment
from data_pipeline.worker.errors import UploadAlreadyProcessing
from data_pipeline.worker.s3_events import S3ObjectRecord
from data_pipeline.worker.uploads import (
    claim_upload_event,
    complete_upload_event,
    fail_upload_event,
)

from .task_errors import TaskProcessingError


def _etag(value: object) -> str | None:
    return value.strip().strip('"') if isinstance(value, str) and value.strip() else None


class S3SharedTranscriptLoader:
    """Download/transcribe once and persist normalized segments for both tasks."""

    def __init__(
        self,
        *,
        session_factory,
        s3_client,
        downloader,
        transcriber,
        max_audio_bytes: int,
        stale_after_seconds: int = 1800,
    ) -> None:
        self._session_factory = session_factory
        self._s3 = s3_client
        self._downloader = downloader
        self._transcriber = transcriber
        self._max_audio_bytes = max_audio_bytes
        self._stale_after = timedelta(seconds=stale_after_seconds)

    def __call__(self, command, recording) -> list[dict]:
        head = self._s3.head_object(
            Bucket=recording.recording_bucket,
            Key=recording.object_key,
        )
        size = head.get("ContentLength")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= self._max_audio_bytes:
            raise ValueError("recording ContentLength is invalid")
        version_id = head.get("VersionId")
        version_id = version_id.strip() if isinstance(version_id, str) and version_id.strip() else None
        etag = _etag(head.get("ETag"))
        if version_id is None and etag is None:
            raise ValueError("recording has neither VersionId nor ETag")
        record = S3ObjectRecord(
            bucket=recording.recording_bucket,
            object_key=recording.object_key,
            version_id=version_id,
            etag=etag,
            size=size,
            project_id=command.project_id,
            external_meeting_id=command.meeting_id,
            upload_id=recording.egress_id,
            filename=recording.object_key.rsplit("/", 1)[-1],
        )
        claim = claim_upload_event(
            self._session_factory,
            record=record,
            stale_after=self._stale_after,
        )
        if claim.completed:
            return self._stored_segments(command.project_id, command.meeting_id)
        if not claim.claimed:
            raise UploadAlreadyProcessing("recording transcript is already processing")
        request_id = "s3-" + hashlib.sha256(
            f"{record.bucket}\0{record.object_key}\0{record.object_identity}".encode()
        ).hexdigest()
        try:
            with self._downloader.download(record) as audio_path:
                raw_segments = self._transcriber.transcribe(
                    audio_path,
                    meeting_id=command.meeting_id,
                )
            segments = normalize_transcript_segments(raw_segments)
            session = self._session_factory()
            try:
                upsert_meeting(session, command.project_id, command.meeting_id)
                upsert_segments(
                    session,
                    command.project_id,
                    command.meeting_id,
                    segments,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            complete_upload_event(
                self._session_factory,
                claim=claim,
                external_request_id=request_id,
                pipeline_status="TRANSCRIPT_READY",
                pipeline_outcome="STT_NORMALIZED",
            )
            return segments
        except Exception as exc:
            fail_upload_event(self._session_factory, claim=claim, error=exc)
            raise

    def _stored_segments(self, project_id: str, meeting_id: str) -> list[dict]:
        with self._session_factory() as session:
            rows = list(
                session.execute(
                    select(TranscriptSegment)
                    .where(
                        TranscriptSegment.project_id == project_id,
                        TranscriptSegment.external_meeting_id == meeting_id,
                    )
                    .order_by(TranscriptSegment.sequence_no, TranscriptSegment.segment_id)
                ).scalars()
            )
        if not rows:
            raise RuntimeError("completed upload has no stored transcript segments")
        return [
            {
                "segmentId": row.segment_id,
                "sequenceNo": row.sequence_no,
                "startMs": row.start_ms,
                "endMs": row.end_ms,
                "speakerLabel": row.speaker_label,
                "rawText": row.raw_text or row.text,
                "normalizedText": row.normalized_text or row.text,
                "text": row.normalized_text or row.text,
                "normalization": row.normalization_metadata,
            }
            for row in rows
        ]


def nodes_processor(
    *,
    session_factory,
    llm_client=None,
    llm_client_factory=None,
    embedding_client,
    b_model_client,
    retrieval_settings=None,
    merge_policy=None,
    pipeline_label: str = "automatic-b-model",
):
    if llm_client is None and llm_client_factory is None:
        raise ValueError("llm_client or llm_client_factory is required")

    def process(command, recording, transcript) -> None:
        del recording
        client = (
            llm_client_factory(command)
            if llm_client_factory is not None
            else llm_client
        )
        run_automatic_meeting(
            session_factory,
            meeting_input={
                "requestId": f"command-{command.command_id}",
                "recordingHash": hashlib.sha256(
                    f"{command.command_id}:{command.room_name}".encode()
                ).hexdigest(),
                "projectId": command.project_id,
                "externalMeetingId": command.meeting_id,
                "segments": transcript,
            },
            client=client,
            embedding_client=embedding_client,
            b_model_client=b_model_client,
            retrieval_settings=retrieval_settings,
            merge_policy=merge_policy,
            pipeline_label=pipeline_label,
            generate_summary=False,
        )

    return process


def summary_processor(*, session_factory, generator, callback_client):
    def process(command, recording, transcript) -> None:
        del recording, transcript
        try:
            result = generate_meeting_summary(
                session_factory,
                project_id=command.project_id,
                external_meeting_id=command.meeting_id,
                summary_version=1,
                generator=generator,
            )
            callback_body = build_callback_body(
                result,
                command_id=command.command_id,
            )
        except Exception as exc:
            raise TaskProcessingError(
                f"{type(exc).__name__}: {exc}",
                failure_code="SUMMARY_GENERATION_FAILED",
                retryable=True,
            ) from exc

        try:
            callback_client.send(
                meeting_id=command.meeting_id,
                body=callback_body,
                project_id=command.project_id,
            )
        except PermanentMeetingRecordCallbackError as exc:
            already_failed = (
                exc.error_code == "MEETING_RECORD_SUMMARY_ALREADY_FAILED"
            )
            raise TaskProcessingError(
                str(exc),
                failure_code="SUMMARY_CALLBACK_REJECTED",
                retryable=False,
                emit_failure_event=not already_failed,
            ) from exc
        except RetryableMeetingRecordCallbackError as exc:
            raise TaskProcessingError(
                str(exc),
                failure_code="SUMMARY_CALLBACK_DELIVERY_FAILED",
                retryable=exc.coordinator_retryable,
            ) from exc

    return process


__all__ = ["S3SharedTranscriptLoader", "nodes_processor", "summary_processor"]
