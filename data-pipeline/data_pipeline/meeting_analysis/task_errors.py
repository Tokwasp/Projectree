"""Task failure metadata consumed by the durable analysis coordinator."""

from __future__ import annotations


class TaskProcessingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_code: str,
        retryable: bool,
        emit_failure_event: bool = True,
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.retryable = retryable
        self.emit_failure_event = emit_failure_event


__all__ = ["TaskProcessingError"]
