"""Single-concurrency SQS long-polling worker for S3 ObjectCreated events."""

from __future__ import annotations

import hashlib
import logging
import threading
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Protocol

from sqlalchemy.orm import sessionmaker

from data_pipeline.llm import ChatClient
from data_pipeline.pipeline import run_meeting
from data_pipeline.stt import Transcriber

from .errors import PipelineProcessingError, UploadAlreadyProcessing
from .message_router import SqsMessageRouter
from .s3_download import S3TemporaryDownloader
from .s3_events import S3EventParser, S3ObjectRecord
from .uploads import (
    claim_upload_event,
    complete_upload_event,
    fail_upload_event,
)

logger = logging.getLogger(__name__)

_PIPELINE_SUCCESS_STATUSES = {
    "REVIEW_PENDING",
    "REVIEW_COMPLETED",
    "COMPLETED",
}


class SqsClient(Protocol):
    def receive_message(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_message(self, **kwargs: Any) -> Any: ...

    def change_message_visibility(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class WorkerPollResult:
    received: int
    deleted: int
    failed: int


class _VisibilityHeartbeat(AbstractContextManager):
    def __init__(
        self,
        *,
        client: SqsClient,
        queue_url: str,
        receipt_handle: str,
        visibility_timeout_seconds: int,
        interval_seconds: float,
        max_extensions: int,
    ):
        self._client = client
        self._queue_url = queue_url
        self._receipt_handle = receipt_handle
        self._visibility_timeout_seconds = visibility_timeout_seconds
        self._interval_seconds = interval_seconds
        self._max_extensions = max_extensions
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        if (
            self._interval_seconds > 0
            and self._visibility_timeout_seconds > 0
            and self._max_extensions > 0
        ):
            self._thread = threading.Thread(
                target=self._run,
                name="sqs-visibility-heartbeat",
                daemon=True,
            )
            self._thread.start()
        return self

    def _run(self) -> None:
        for _ in range(self._max_extensions):
            if self._stop.wait(self._interval_seconds):
                return
            try:
                self._client.change_message_visibility(
                    QueueUrl=self._queue_url,
                    ReceiptHandle=self._receipt_handle,
                    VisibilityTimeout=self._visibility_timeout_seconds,
                )
            except Exception:
                logger.exception("SQS visibility heartbeat failed")

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=min(self._interval_seconds, 1.0) + 0.1)
        return None


class SqsAudioWorker:
    """Process at most one SQS message at a time."""

    def __init__(
        self,
        *,
        sqs_client: SqsClient,
        queue_url: str,
        parser: S3EventParser,
        downloader: S3TemporaryDownloader,
        session_factory: sessionmaker,
        transcriber: Transcriber,
        llm_client_factory: Callable[[S3ObjectRecord], ChatClient],
        wait_time_seconds: int = 20,
        visibility_timeout_seconds: int = 900,
        heartbeat_interval_seconds: float = 300,
        heartbeat_max_extensions: int = 6,
        upload_processing_timeout_seconds: int = 1800,
        meeting_runner=run_meeting,
        router: SqsMessageRouter | None = None,
    ):
        self._sqs = sqs_client
        self._queue_url = queue_url
        # Without an explicit router the worker understands S3 events only,
        # which is exactly the behaviour that existed before OpenVidu support.
        self._router = router or SqsMessageRouter(s3_parser=parser)
        self._downloader = downloader
        self._session_factory = session_factory
        self._transcriber = transcriber
        self._llm_client_factory = llm_client_factory
        self._wait_time_seconds = wait_time_seconds
        self._visibility_timeout_seconds = visibility_timeout_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_max_extensions = heartbeat_max_extensions
        self._upload_processing_timeout = timedelta(
            seconds=upload_processing_timeout_seconds
        )
        self._meeting_runner = meeting_runner

    def poll_once(self) -> WorkerPollResult:
        response = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=self._wait_time_seconds,
            VisibilityTimeout=self._visibility_timeout_seconds,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        messages = response.get("Messages") or []
        deleted = failed = 0
        for message in messages:
            receipt_handle = message.get("ReceiptHandle")
            body = message.get("Body")
            if not isinstance(receipt_handle, str) or not isinstance(body, str):
                logger.error("SQS message is missing Body or ReceiptHandle")
                failed += 1
                continue
            try:
                with _VisibilityHeartbeat(
                    client=self._sqs,
                    queue_url=self._queue_url,
                    receipt_handle=receipt_handle,
                    visibility_timeout_seconds=self._visibility_timeout_seconds,
                    interval_seconds=self._heartbeat_interval_seconds,
                    max_extensions=self._heartbeat_max_extensions,
                ):
                    self._process_body(body)
                self._sqs.delete_message(
                    QueueUrl=self._queue_url,
                    ReceiptHandle=receipt_handle,
                )
                deleted += 1
            except Exception as exc:
                # The error type identifies which contract rejected the message;
                # bodies are never logged because they may reference meeting content.
                logger.exception(
                    "SQS audio message processing failed "
                    "message_id=%s error_type=%s",
                    message.get("MessageId"),
                    type(exc).__name__,
                )
                failed += 1
        return WorkerPollResult(
            received=len(messages),
            deleted=deleted,
            failed=failed,
        )

    def run_forever(self) -> None:
        while True:
            try:
                self.poll_once()
            except KeyboardInterrupt:
                return
            except Exception:
                logger.exception("SQS long poll failed; worker will continue")

    def _process_body(self, body: str) -> None:
        routed = self._router.route(body)
        if routed.is_test_event:
            return
        for record in routed.records:
            self._process_record(record)

    def _process_record(self, record: S3ObjectRecord) -> None:
        claim = claim_upload_event(
            self._session_factory,
            record=record,
            stale_after=self._upload_processing_timeout,
        )
        if claim.completed:
            return
        if not claim.claimed:
            raise UploadAlreadyProcessing(
                "The same S3 upload is already being processed"
            )

        request_id = self._request_id(record)
        try:
            with self._downloader.download(record) as audio_path:
                segments = self._transcriber.transcribe(
                    audio_path,
                    meeting_id=record.external_meeting_id,
                )
                result = self._meeting_runner(
                    self._session_factory,
                    meeting_input={
                        "requestId": request_id,
                        "recordingHash": request_id.removeprefix("s3-"),
                        "projectId": record.project_id,
                        "externalMeetingId": record.external_meeting_id,
                        "segments": segments,
                    },
                    client=self._llm_client_factory(record),
                    force_retry=claim.attempt > 1,
                )
            proposal = result.proposal_result
            if proposal.status not in _PIPELINE_SUCCESS_STATUSES:
                raise PipelineProcessingError(
                    "Meeting pipeline did not reach a durable success status "
                    f"(status={proposal.status}, outcome={proposal.outcome})"
                )
            complete_upload_event(
                self._session_factory,
                claim=claim,
                external_request_id=request_id,
                pipeline_status=proposal.status,
                pipeline_outcome=proposal.outcome,
            )
        except Exception as exc:
            fail_upload_event(
                self._session_factory,
                claim=claim,
                error=exc,
            )
            raise

    @staticmethod
    def _request_id(record: S3ObjectRecord) -> str:
        value = "\0".join(
            (record.bucket, record.object_key, record.object_identity)
        )
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"s3-{digest}"


__all__ = ["SqsAudioWorker", "SqsClient", "WorkerPollResult"]
