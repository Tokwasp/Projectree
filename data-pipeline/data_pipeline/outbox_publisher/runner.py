"""Poll the outbox and relay events to a transport."""

from __future__ import annotations

import logging
import time

from data_pipeline.jobs.outbox import OutboxTransport, PublishResult, publish_pending_events

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(
        self,
        *,
        session_factory,
        transport: OutboxTransport,
        batch_size: int = 20,
        stall_timeout_seconds: float = 300.0,
        schema_versions: tuple[str, ...] | None = None,
    ):
        self._session_factory = session_factory
        self._transport = transport
        self._batch_size = batch_size
        self._stall_timeout_seconds = stall_timeout_seconds
        self._schema_versions = schema_versions

    def run_once(self) -> PublishResult:
        result = publish_pending_events(
            self._session_factory,
            self._transport,
            batch_size=self._batch_size,
            stall_timeout_seconds=self._stall_timeout_seconds,
            schema_versions=self._schema_versions,
        )
        if result.claimed:
            logger.info(
                "outbox batch claimed=%d published=%d failed=%d dead=%d",
                result.claimed,
                result.published,
                result.failed,
                result.dead,
            )
        return result

    def run_forever(self, *, idle_sleep_seconds: float = 2.0) -> None:
        while True:
            try:
                result = self.run_once()
            except KeyboardInterrupt:
                return
            except Exception:
                logger.exception("outbox publisher loop failed; continuing")
                time.sleep(idle_sleep_seconds)
                continue
            if result.claimed == 0:
                time.sleep(idle_sleep_seconds)


__all__ = ["OutboxPublisher"]
