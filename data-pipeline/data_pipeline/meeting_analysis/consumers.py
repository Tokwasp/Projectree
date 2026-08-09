"""Short-lived SQS consumers that ACK only after durable input persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from data_pipeline.worker.openvidu_events import OpenViduEgressEventParser

from .contracts import JavaCommandParser
from .dispatcher import dispatch_java_command
from .persistence import persist_recording_ready

logger = logging.getLogger(__name__)


class SqsInputClient(Protocol):
    def receive_message(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_message(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class InputPollResult:
    received: int
    acknowledged: int
    failed: int


class _PersistingConsumer:
    def __init__(
        self,
        *,
        sqs_client: SqsInputClient,
        queue_url: str,
        persist_body: Callable[[str], object],
        wait_time_seconds: int = 20,
    ) -> None:
        if not queue_url:
            raise ValueError("queue_url is required")
        self._sqs = sqs_client
        self._queue_url = queue_url
        self._persist_body = persist_body
        self._wait_time_seconds = wait_time_seconds

    def poll_once(self) -> InputPollResult:
        response = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=self._wait_time_seconds,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        messages = response.get("Messages") or []
        acknowledged = failed = 0
        for message in messages:
            body = message.get("Body")
            receipt_handle = message.get("ReceiptHandle")
            if not isinstance(body, str) or not isinstance(receipt_handle, str):
                failed += 1
                continue
            try:
                self._persist_body(body)
            except Exception:
                logger.exception(
                    "input message persistence failed message_id=%s",
                    message.get("MessageId"),
                )
                failed += 1
                continue
            self._sqs.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle,
            )
            acknowledged += 1
        return InputPollResult(len(messages), acknowledged, failed)

    def run_forever(self) -> None:
        while True:
            try:
                self.poll_once()
            except KeyboardInterrupt:
                return
            except Exception:
                logger.exception("input queue long poll failed; continuing")


class RecordingReadyConsumer(_PersistingConsumer):
    def __init__(
        self,
        *,
        sqs_client: SqsInputClient,
        queue_url: str,
        session_factory,
        parser: OpenViduEgressEventParser,
        recording_bucket: str,
        wait_time_seconds: int = 20,
    ) -> None:
        def persist(body: str) -> None:
            event = parser.parse(body)
            persist_recording_ready(
                session_factory,
                event=event,
                recording_bucket=recording_bucket,
            )

        super().__init__(
            sqs_client=sqs_client,
            queue_url=queue_url,
            persist_body=persist,
            wait_time_seconds=wait_time_seconds,
        )


class AnalysisCommandConsumer(_PersistingConsumer):
    def __init__(
        self,
        *,
        sqs_client: SqsInputClient,
        queue_url: str,
        session_factory,
        parser: JavaCommandParser | None = None,
        wait_time_seconds: int = 20,
    ) -> None:
        command_parser = parser or JavaCommandParser()

        def persist(body: str) -> None:
            command = command_parser.parse(body)
            dispatch_java_command(session_factory, command=command)

        super().__init__(
            sqs_client=sqs_client,
            queue_url=queue_url,
            persist_body=persist,
            wait_time_seconds=wait_time_seconds,
        )


__all__ = [
    "AnalysisCommandConsumer",
    "InputPollResult",
    "RecordingReadyConsumer",
]
