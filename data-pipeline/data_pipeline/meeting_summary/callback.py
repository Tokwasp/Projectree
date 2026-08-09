"""Synchronous, reusable Java meeting-record callback client."""

from __future__ import annotations

import logging
import math
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from .contracts import (
    MeetingSummaryContractError,
    SUMMARY_SECTION_NAMES,
    json_array_size_bytes,
    normalize_summary_items,
)
from .service import MeetingSummaryResult

logger = logging.getLogger(__name__)

CALLBACK_SCHEMA_VERSION = 1
RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
SUMMARY_ALREADY_FAILED = "MEETING_RECORD_SUMMARY_ALREADY_FAILED"
SUMMARY_CONTENT_TOO_LARGE = "MEETING_RECORD_CONTENT_TOO_LARGE"
COMPACT_SECTION_TARGET_BYTES = 50_000


class MeetingRecordCallbackError(RuntimeError):
    pass


class PermanentMeetingRecordCallbackError(MeetingRecordCallbackError):
    def __init__(
        self,
        *,
        status_code: int,
        error_code: str | None,
        message: str,
    ) -> None:
        safe_message = message[:1000]
        super().__init__(
            "permanent callback error: "
            f"status={status_code}, errorCode={error_code}, "
            f"message={safe_message}"
        )
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = safe_message


class RetryableMeetingRecordCallbackError(MeetingRecordCallbackError):
    def __init__(self, message: str, *, coordinator_retryable: bool = True) -> None:
        super().__init__(message)
        self.coordinator_retryable = coordinator_retryable


@dataclass(frozen=True)
class CallbackResult:
    meeting_record_id: int
    meeting_id: str
    command_id: str
    version: int
    duplicated: bool


@dataclass(frozen=True)
class MeetingRecordCallbackSettings:
    base_url: str
    api_key: str
    timeout_seconds: float


def load_meeting_record_callback_settings() -> MeetingRecordCallbackSettings:
    base_url = os.getenv("JAVA_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("MEETING_RECORD_CALLBACK_API_KEY", "")
    raw_timeout = os.getenv("MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS", "10")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("JAVA_BASE_URL must be an absolute HTTP(S) URL")
    if not api_key.strip():
        raise ValueError("MEETING_RECORD_CALLBACK_API_KEY must not be blank")
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise ValueError(
            "MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS must be a number"
        ) from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(
            "MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS must be positive"
        )
    return MeetingRecordCallbackSettings(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )


def build_callback_body(
    summary: MeetingSummaryResult,
    *,
    command_id: str | uuid.UUID,
) -> dict[str, Any]:
    """Map both current and legacy stored summaries to callback schema v1."""

    structured = dict(summary.structured_summary or {})
    if "summary" in structured:
        summary_items = normalize_summary_items(structured["summary"], "summary")
    elif summary.body.strip():
        summary_items = normalize_summary_items([summary.body], "summary")
    else:
        summary_items = ()
    next_todos_source = (
        structured["nextTodos"]
        if "nextTodos" in structured
        else structured.get("actions", [])
    )
    try:
        canonical_command_id = str(uuid.UUID(str(command_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise MeetingSummaryContractError("commandId must be a UUID") from exc
    title = summary.title.strip()
    if not title or len(title) > 200:
        raise MeetingSummaryContractError(
            "stored summary title must be 1..200 characters"
        )
    return {
        "callbackSchemaVersion": CALLBACK_SCHEMA_VERSION,
        "commandId": canonical_command_id,
        "title": title,
        "summary": list(summary_items),
        "decisions": list(
            normalize_summary_items(structured.get("decisions", []), "decisions")
        ),
        "nextTodos": list(
            normalize_summary_items(next_todos_source, "nextTodos")
        ),
        "issues": list(
            normalize_summary_items(structured.get("issues", []), "issues")
        ),
    }


def compact_callback_body(body: dict[str, Any]) -> dict[str, Any]:
    """Deterministically reduce only callback arrays after Java rejects size."""

    expected = {
        "callbackSchemaVersion",
        "commandId",
        "title",
        *SUMMARY_SECTION_NAMES,
    }
    if set(body) != expected:
        raise MeetingSummaryContractError(
            "callback body keys do not match schema version 1"
        )
    compacted: dict[str, Any] = {
        "callbackSchemaVersion": body["callbackSchemaVersion"],
        "commandId": body["commandId"],
        "title": body["title"],
    }
    sections = {
        name: list(normalize_summary_items(body[name], name))
        for name in SUMMARY_SECTION_NAMES
    }
    original_sections = {name: list(items) for name, items in sections.items()}

    for name in sorted(
        SUMMARY_SECTION_NAMES,
        key=lambda item: (-json_array_size_bytes(sections[item]), item),
    ):
        items = sections[name]
        while len(items) > 1 and json_array_size_bytes(items) > COMPACT_SECTION_TARGET_BYTES:
            items.pop()
        if items and json_array_size_bytes(items) > COMPACT_SECTION_TARGET_BYTES:
            items[0] = _truncate_item_to_json_size(
                items[0],
                COMPACT_SECTION_TARGET_BYTES,
            )

    if sections == original_sections:
        nonempty = [name for name in SUMMARY_SECTION_NAMES if sections[name]]
        if not nonempty:
            raise MeetingSummaryContractError(
                "callback body cannot be compacted because every section is empty"
            )
        largest = min(
            nonempty,
            key=lambda item: (-json_array_size_bytes(sections[item]), item),
        )
        last = sections[largest][-1]
        if len(last) > 1:
            sections[largest][-1] = last[:-1]
        else:
            sections[largest].pop()

    for name in SUMMARY_SECTION_NAMES:
        compacted[name] = list(normalize_summary_items(sections[name], name))
        if json_array_size_bytes(compacted[name]) > COMPACT_SECTION_TARGET_BYTES:
            raise MeetingSummaryContractError(
                f"{name} could not be compacted to the safe delivery target"
            )
    if compacted == body:
        raise MeetingSummaryContractError("callback body could not be compacted")
    return compacted


def _truncate_item_to_json_size(text: str, max_bytes: int) -> str:
    low = 1
    high = len(text)
    best = ""
    while low <= high:
        middle = (low + high) // 2
        candidate = text[:middle]
        if json_array_size_bytes([candidate]) <= max_bytes:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    if not best:
        raise MeetingSummaryContractError(
            "a summary item cannot be compacted without becoming blank"
        )
    return best


class MeetingRecordCallbackClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        parsed = urlparse(normalized_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("JAVA_BASE_URL must be an absolute HTTP(S) URL")
        if not api_key.strip():
            raise ValueError("MEETING_RECORD_CALLBACK_API_KEY must not be blank")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError(
                "MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS must be positive"
            )
        self._base_url = normalized_base_url
        self._api_key = api_key
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds)
        )
        self._owns_client = http_client is None
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def send(
        self,
        *,
        meeting_id: str | int,
        body: dict[str, Any],
        project_id: str | int | None = None,
    ) -> CallbackResult:
        meeting_id_text = str(meeting_id)
        if not meeting_id_text.isdigit() or int(meeting_id_text) <= 0:
            raise ValueError("meetingId must be a positive integer")
        command_id = str(body.get("commandId", ""))
        url = (
            f"{self._base_url}/api/internal/meetings/"
            f"{meeting_id_text}/record"
        )
        attempts = len(RETRY_DELAYS_SECONDS) + 1
        started = time.monotonic()
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.put(
                    url,
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Internal-Api-Key": self._api_key,
                    },
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "meeting record callback network failure "
                    "commandId=%s projectId=%s meetingId=%s attempt=%d",
                    command_id,
                    project_id,
                    meeting_id_text,
                    attempt,
                )
                if attempt == attempts:
                    raise RetryableMeetingRecordCallbackError(
                        "callback network retry exhausted"
                    ) from exc
                self._sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue

            if response.status_code == 200:
                result = self._parse_success(
                    response,
                    expected_meeting_id=meeting_id_text,
                    expected_command_id=command_id,
                )
                logger.info(
                    "meeting record callback completed commandId=%s "
                    "projectId=%s meetingId=%s status=200 duplicated=%s "
                    "attempt=%d elapsedMs=%d",
                    command_id,
                    project_id,
                    meeting_id_text,
                    result.duplicated,
                    attempt,
                    int((time.monotonic() - started) * 1000),
                )
                return result

            error_body = _safe_error_body(response)
            error_code = _optional_text(error_body.get("errorCode"), limit=128)
            error_message = _optional_text(
                error_body.get("errorMessage"), limit=1000
            ) or "unknown callback error"
            logger.warning(
                "meeting record callback rejected commandId=%s projectId=%s "
                "meetingId=%s status=%d errorCode=%s attempt=%d",
                command_id,
                project_id,
                meeting_id_text,
                response.status_code,
                error_code,
                attempt,
            )
            if 500 <= response.status_code <= 599:
                if attempt == attempts:
                    raise RetryableMeetingRecordCallbackError(
                        "callback server retry exhausted: "
                        f"status={response.status_code}"
                    )
                self._sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue
            if error_code == SUMMARY_CONTENT_TOO_LARGE:
                return self._send_compacted_once(
                    url=url,
                    original_body=body,
                    meeting_id=meeting_id_text,
                    command_id=command_id,
                    project_id=project_id,
                    started=started,
                    original_status=response.status_code,
                )
            raise PermanentMeetingRecordCallbackError(
                status_code=response.status_code,
                error_code=error_code,
                message=error_message,
            )
        raise AssertionError("callback retry loop exited unexpectedly")

    def _send_compacted_once(
        self,
        *,
        url: str,
        original_body: dict[str, Any],
        meeting_id: str,
        command_id: str,
        project_id: str | int | None,
        started: float,
        original_status: int,
    ) -> CallbackResult:
        try:
            compacted_body = compact_callback_body(original_body)
        except MeetingSummaryContractError as exc:
            raise PermanentMeetingRecordCallbackError(
                status_code=original_status,
                error_code=SUMMARY_CONTENT_TOO_LARGE,
                message=f"callback body compaction failed: {exc}",
            ) from exc
        logger.warning(
            "meeting record callback retrying compacted payload "
            "commandId=%s projectId=%s meetingId=%s attempt=1",
            command_id,
            project_id,
            meeting_id,
        )
        try:
            response = self._client.put(
                url,
                json=compacted_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Api-Key": self._api_key,
                },
            )
        except httpx.RequestError as exc:
            raise RetryableMeetingRecordCallbackError(
                "compacted callback network delivery failed",
                coordinator_retryable=False,
            ) from exc
        if response.status_code == 200:
            result = self._parse_success(
                response,
                expected_meeting_id=meeting_id,
                expected_command_id=command_id,
            )
            logger.info(
                "meeting record compacted callback completed commandId=%s "
                "projectId=%s meetingId=%s status=200 duplicated=%s "
                "elapsedMs=%d",
                command_id,
                project_id,
                meeting_id,
                result.duplicated,
                int((time.monotonic() - started) * 1000),
            )
            return result
        error_body = _safe_error_body(response)
        error_code = _optional_text(error_body.get("errorCode"), limit=128)
        error_message = _optional_text(
            error_body.get("errorMessage"), limit=1000
        ) or "compacted callback was rejected"
        if 500 <= response.status_code <= 599:
            raise RetryableMeetingRecordCallbackError(
                f"compacted callback server delivery failed: status={response.status_code}",
                coordinator_retryable=False,
            )
        raise PermanentMeetingRecordCallbackError(
            status_code=response.status_code,
            error_code=error_code,
            message=error_message,
        )

    @staticmethod
    def _parse_success(
        response: httpx.Response,
        *,
        expected_meeting_id: str,
        expected_command_id: str,
    ) -> CallbackResult:
        try:
            payload = response.json()
            data = payload["data"]
            meeting_record_id = data["meetingRecordId"]
            meeting_id = data["meetingId"]
            command_id = data["commandId"]
            version = data["version"]
            duplicated = data["duplicated"]
        except (ValueError, TypeError, KeyError) as exc:
            raise PermanentMeetingRecordCallbackError(
                status_code=200,
                error_code="INVALID_CALLBACK_RESPONSE",
                message="callback success response is malformed",
            ) from exc
        if (
            isinstance(meeting_record_id, bool)
            or not isinstance(meeting_record_id, int)
            or isinstance(version, bool)
            or not isinstance(version, int)
            or not isinstance(duplicated, bool)
            or str(meeting_id) != expected_meeting_id
            or str(command_id) != expected_command_id
        ):
            raise PermanentMeetingRecordCallbackError(
                status_code=200,
                error_code="INVALID_CALLBACK_RESPONSE",
                message="callback success response does not match the request",
            )
        return CallbackResult(
            meeting_record_id=meeting_record_id,
            meeting_id=str(meeting_id),
            command_id=str(command_id),
            version=version,
            duplicated=duplicated,
        )


def build_meeting_record_callback_client(
    settings: MeetingRecordCallbackSettings | None = None,
) -> MeetingRecordCallbackClient:
    settings = settings or load_meeting_record_callback_settings()
    return MeetingRecordCallbackClient(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout_seconds=settings.timeout_seconds,
    )


def _safe_error_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _optional_text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:limit]


__all__ = [
    "CALLBACK_SCHEMA_VERSION",
    "COMPACT_SECTION_TARGET_BYTES",
    "CallbackResult",
    "MeetingRecordCallbackClient",
    "MeetingRecordCallbackError",
    "MeetingRecordCallbackSettings",
    "PermanentMeetingRecordCallbackError",
    "RETRY_DELAYS_SECONDS",
    "RetryableMeetingRecordCallbackError",
    "SUMMARY_ALREADY_FAILED",
    "SUMMARY_CONTENT_TOO_LARGE",
    "build_callback_body",
    "build_meeting_record_callback_client",
    "compact_callback_body",
    "load_meeting_record_callback_settings",
]
