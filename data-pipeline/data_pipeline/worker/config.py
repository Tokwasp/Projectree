"""Environment settings for the standalone S3/SQS worker."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value in (None, "") else value


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in _env(name, default).split(",")
        if value.strip()
    )


@dataclass(frozen=True)
class WorkerSettings:
    app_env: str
    aws_region: str
    sqs_queue_url: str
    allowed_buckets: tuple[str, ...]
    input_prefix: str
    allowed_extensions: tuple[str, ...]
    max_audio_bytes: int
    temp_directory: Path | None
    wait_time_seconds: int
    visibility_timeout_seconds: int
    heartbeat_interval_seconds: float
    heartbeat_max_extensions: int
    upload_processing_timeout_seconds: int
    llm_adapter: str
    embedding_adapter: str
    openvidu_recording_bucket: str
    openvidu_recording_prefix: str
    openvidu_supported_kinds: tuple[str, ...]

    @property
    def openvidu_enabled(self) -> bool:
        """OpenVidu ingestion is opt-in: it needs an explicit recording bucket."""

        return bool(self.openvidu_recording_bucket)

    def validate_runtime(self) -> None:
        if not self.aws_region:
            raise ValueError("AWS_REGION is required")
        if not self.sqs_queue_url:
            raise ValueError("SQS_QUEUE_URL is required")
        if not self.allowed_buckets:
            raise ValueError("S3_ALLOWED_BUCKETS is required")
        if self.app_env == "test":
            if self.llm_adapter != "fake":
                raise ValueError("APP_ENV=test requires LLM_ADAPTER=fake")
            if self.embedding_adapter != "fake":
                raise ValueError(
                    "APP_ENV=test requires EMBEDDING_ADAPTER=fake"
                )


def load_worker_settings() -> WorkerSettings:
    prefix = _env("S3_INPUT_PREFIX", "audio-input/")
    if not prefix.endswith("/"):
        prefix += "/"
    openvidu_prefix = _env("OPENVIDU_RECORDING_PREFIX", "meetings/")
    if not openvidu_prefix.endswith("/"):
        openvidu_prefix += "/"
    temp_value = os.getenv("AUDIO_TEMP_DIRECTORY")
    return WorkerSettings(
        app_env=_env("APP_ENV", "local").strip().lower(),
        aws_region=_env("AWS_REGION"),
        sqs_queue_url=_env("SQS_QUEUE_URL"),
        allowed_buckets=_csv("S3_ALLOWED_BUCKETS", ""),
        input_prefix=prefix,
        allowed_extensions=tuple(
            value.lower()
            if value.startswith(".")
            else f".{value.lower()}"
            for value in _csv(
                "S3_ALLOWED_EXTENSIONS",
                ".wav,.mp3,.m4a,.flac,.ogg,.aac",
            )
        ),
        max_audio_bytes=int(_env("S3_MAX_AUDIO_BYTES", "104857600")),
        temp_directory=Path(temp_value) if temp_value else None,
        wait_time_seconds=int(_env("SQS_WAIT_TIME_SECONDS", "20")),
        visibility_timeout_seconds=int(
            _env("SQS_VISIBILITY_TIMEOUT_SECONDS", "900")
        ),
        heartbeat_interval_seconds=float(
            _env("SQS_HEARTBEAT_INTERVAL_SECONDS", "300")
        ),
        heartbeat_max_extensions=int(
            _env("SQS_HEARTBEAT_MAX_EXTENSIONS", "6")
        ),
        upload_processing_timeout_seconds=int(
            _env("UPLOAD_PROCESSING_TIMEOUT_SECONDS", "1800")
        ),
        llm_adapter=_env("LLM_ADAPTER", "fake").strip().lower(),
        embedding_adapter=_env("EMBEDDING_ADAPTER", "fake").strip().lower(),
        openvidu_recording_bucket=_env("OPENVIDU_RECORDING_BUCKET"),
        openvidu_recording_prefix=openvidu_prefix,
        openvidu_supported_kinds=_csv("OPENVIDU_SUPPORTED_KINDS", "MIXED"),
    )


__all__ = ["WorkerSettings", "load_worker_settings"]
