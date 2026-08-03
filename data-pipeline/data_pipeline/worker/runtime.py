"""Assemble the standalone worker from environment-backed adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import Engine

from data_pipeline.config import load_settings
from data_pipeline.llm import OpenAIChatClient, load_llm_settings
from data_pipeline.storage import make_engine, make_session_factory
from data_pipeline.stt import build_transcriber

from .config import WorkerSettings, load_worker_settings
from .fakes import (
    FakeBModelClient,
    FakeEmbeddingClient,
    FakeMeetingChatClient,
)
from .meeting_context import (
    MeetingContextResolver,
    UnavailableMeetingContextResolver,
)
from .message_router import SqsMessageRouter
from .openvidu_events import OpenViduEgressEventParser
from .openvidu_ingest import OpenViduIngestAdapter
from .s3_download import S3TemporaryDownloader
from .s3_events import S3EventParser
from .sqs import SqsAudioWorker

logger = logging.getLogger(__name__)


@dataclass
class WorkerRuntime:
    worker: SqsAudioWorker
    engine: Engine

    def close(self) -> None:
        self.engine.dispose()


def build_worker_runtime(
    worker_settings: WorkerSettings | None = None,
    *,
    meeting_context_resolver: MeetingContextResolver | None = None,
) -> WorkerRuntime:
    settings = worker_settings or load_worker_settings()
    settings.validate_runtime()
    app_settings = load_settings()
    if settings.app_env == "test" and app_settings.stt.adapter != "fake":
        raise ValueError("APP_ENV=test requires STT_ADAPTER=fake")

    import boto3

    s3_client = boto3.client("s3", region_name=settings.aws_region)
    sqs_client = boto3.client("sqs", region_name=settings.aws_region)
    engine = make_engine(app_settings.database_url)
    session_factory = make_session_factory(engine)
    transcriber = build_transcriber(app_settings.stt)

    if settings.llm_adapter == "fake":
        llm_client_factory = lambda record: FakeMeetingChatClient(
            record.external_meeting_id
        )
    elif settings.llm_adapter == "openai":
        client = OpenAIChatClient(load_llm_settings())
        llm_client_factory = lambda record: client
    else:
        engine.dispose()
        raise ValueError(
            "LLM_ADAPTER must be either 'fake' or 'openai'"
        )

    parser = S3EventParser(
        allowed_buckets=frozenset(settings.allowed_buckets),
        input_prefix=settings.input_prefix,
        allowed_extensions=frozenset(settings.allowed_extensions),
        max_audio_bytes=settings.max_audio_bytes,
    )
    downloader = S3TemporaryDownloader(
        s3_client,
        max_audio_bytes=settings.max_audio_bytes,
        temp_directory=settings.temp_directory,
    )

    openvidu_parser = None
    openvidu_adapter = None
    if settings.openvidu_enabled:
        if meeting_context_resolver is None:
            # Enabled but unusable: every OpenVidu message will fail to resolve
            # and stay on the queue. Say so once at startup instead of only
            # once per redelivery.
            logger.warning(
                "OpenVidu ingestion is enabled (OPENVIDU_RECORDING_BUCKET is set) "
                "but no MeetingContextResolver was supplied, so every OpenVidu "
                "message will fail with MeetingContextUnresolvedError and remain "
                "on the queue. Supply a resolver before enabling this path."
            )
        openvidu_parser = OpenViduEgressEventParser(
            recording_prefix=settings.openvidu_recording_prefix,
            allowed_extensions=frozenset(settings.allowed_extensions),
            supported_kinds=frozenset(settings.openvidu_supported_kinds),
        )
        openvidu_adapter = OpenViduIngestAdapter(
            s3_client=s3_client,
            resolver=(
                meeting_context_resolver or UnavailableMeetingContextResolver()
            ),
            bucket=settings.openvidu_recording_bucket,
            max_audio_bytes=settings.max_audio_bytes,
        )

    router = SqsMessageRouter(
        s3_parser=parser,
        openvidu_parser=openvidu_parser,
        openvidu_adapter=openvidu_adapter,
    )
    # PIPELINE_PROMPT_PROFILE selects a registered prompt profile for ingestion
    # (e.g. candidate-quality-v1). Empty keeps run_meeting's default (poc-lts).
    # Validated eagerly so a typo fails at startup, not on the first meeting.
    import functools
    import os

    from data_pipeline.pipeline import run_meeting
    from data_pipeline.pipeline.automatic_graph import (
        AutoMergePolicy,
        run_automatic_meeting,
    )
    from data_pipeline.prompts import get_pipeline_profile

    profile_name = os.getenv("PIPELINE_PROMPT_PROFILE", "").strip()
    if profile_name:
        candidate_runner = functools.partial(
            run_meeting, prompt_profile=get_pipeline_profile(profile_name)
        )
    else:
        candidate_runner = run_meeting

    if settings.embedding_adapter == "fake":
        embedding_client = FakeEmbeddingClient()
    else:
        from data_pipeline.retrieval.embedding_client import (
            build_embedding_client,
        )

        embedding_client = build_embedding_client(settings.embedding_adapter)
    if settings.b_model_adapter == "fake":
        b_model_client = FakeBModelClient()
        b_model_name = "fake-b-model"
    else:
        from data_pipeline.b_model.client import build_b_model_client

        b_model_client = build_b_model_client(settings.b_model_adapter)
        b_model_name = (
            os.getenv("B_MODEL_NAME", "").strip()
            or os.getenv("OPENAI_MODEL", "").strip()
            or "configured-b-model"
        )
    meeting_runner = functools.partial(
        run_automatic_meeting,
        meeting_runner=candidate_runner,
        embedding_client=embedding_client,
        b_model_client=b_model_client,
        retrieval_settings=app_settings.retrieval,
        merge_policy=AutoMergePolicy(
            min_similarity=app_settings.retrieval.auto_merge_min_similarity,
            min_margin=app_settings.retrieval.auto_merge_min_margin,
        ),
        b_model=b_model_name,
    )

    worker = SqsAudioWorker(
        meeting_runner=meeting_runner,
        sqs_client=sqs_client,
        queue_url=settings.sqs_queue_url,
        parser=parser,
        router=router,
        downloader=downloader,
        session_factory=session_factory,
        transcriber=transcriber,
        llm_client_factory=llm_client_factory,
        wait_time_seconds=settings.wait_time_seconds,
        visibility_timeout_seconds=settings.visibility_timeout_seconds,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        heartbeat_max_extensions=settings.heartbeat_max_extensions,
        upload_processing_timeout_seconds=(
            settings.upload_processing_timeout_seconds
        ),
    )
    return WorkerRuntime(worker=worker, engine=engine)


__all__ = ["WorkerRuntime", "build_worker_runtime"]
