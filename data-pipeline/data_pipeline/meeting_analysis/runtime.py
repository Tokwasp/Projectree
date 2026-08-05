"""Environment-backed assembly for the two consumers and DB coordinator."""

from __future__ import annotations

import os
from dataclasses import dataclass

from data_pipeline.config import load_settings
from data_pipeline.meeting_summary import build_meeting_summary_generator
from data_pipeline.storage import make_engine, make_session_factory
from data_pipeline.stt import build_transcriber
from data_pipeline.worker.config import load_worker_settings
from data_pipeline.worker.fakes import (
    FakeBModelClient,
    FakeEmbeddingClient,
    FakeMeetingChatClient,
)
from data_pipeline.worker.openvidu_events import OpenViduEgressEventParser
from data_pipeline.worker.s3_download import S3TemporaryDownloader

from .consumers import AnalysisCommandConsumer, RecordingReadyConsumer
from .coordinator import MeetingAnalysisCoordinator
from .runtime_adapters import (
    S3SharedTranscriptLoader,
    nodes_processor,
    summary_processor,
)


@dataclass
class MeetingAnalysisRuntime:
    component: object
    engine: object

    def close(self) -> None:
        self.engine.dispose()


def _aws_clients(region: str):
    import boto3

    return (
        boto3.client("s3", region_name=region),
        boto3.client("sqs", region_name=region),
    )


def build_recording_consumer_runtime() -> MeetingAnalysisRuntime:
    worker = load_worker_settings()
    app = load_settings()
    queue_url = os.getenv("RECORDING_READY_QUEUE_URL", "").strip()
    if not queue_url or not worker.openvidu_recording_bucket:
        raise ValueError(
            "RECORDING_READY_QUEUE_URL and OPENVIDU_RECORDING_BUCKET are required"
        )
    _, sqs = _aws_clients(worker.aws_region)
    engine = make_engine(app.database_url)
    component = RecordingReadyConsumer(
        sqs_client=sqs,
        queue_url=queue_url,
        session_factory=make_session_factory(engine),
        parser=OpenViduEgressEventParser(
            recording_prefix=worker.openvidu_recording_prefix,
            allowed_extensions=frozenset(worker.allowed_extensions),
            supported_kinds=frozenset(worker.openvidu_supported_kinds),
        ),
        recording_bucket=worker.openvidu_recording_bucket,
        wait_time_seconds=worker.wait_time_seconds,
    )
    return MeetingAnalysisRuntime(component, engine)


def build_command_consumer_runtime() -> MeetingAnalysisRuntime:
    worker = load_worker_settings()
    app = load_settings()
    queue_url = os.getenv("ANALYSIS_COMMAND_QUEUE_URL", "").strip()
    if not queue_url:
        raise ValueError("ANALYSIS_COMMAND_QUEUE_URL is required")
    _, sqs = _aws_clients(worker.aws_region)
    engine = make_engine(app.database_url)
    component = AnalysisCommandConsumer(
        sqs_client=sqs,
        queue_url=queue_url,
        session_factory=make_session_factory(engine),
        wait_time_seconds=worker.wait_time_seconds,
    )
    return MeetingAnalysisRuntime(component, engine)


def build_coordinator_runtime() -> MeetingAnalysisRuntime:
    worker = load_worker_settings()
    app = load_settings()
    s3, _ = _aws_clients(worker.aws_region)
    engine = make_engine(app.database_url)
    sessions = make_session_factory(engine)
    downloader = S3TemporaryDownloader(
        s3,
        max_audio_bytes=worker.max_audio_bytes,
        temp_directory=worker.temp_directory,
    )
    transcript_loader = S3SharedTranscriptLoader(
        session_factory=sessions,
        s3_client=s3,
        downloader=downloader,
        transcriber=build_transcriber(app.stt),
        max_audio_bytes=worker.max_audio_bytes,
        stale_after_seconds=worker.upload_processing_timeout_seconds,
    )
    if worker.llm_adapter == "fake":
        llm_client = None
        llm_client_factory = lambda command: FakeMeetingChatClient(
            command.meeting_id
        )
    elif worker.llm_adapter in {"gms", "openai"}:
        from data_pipeline.llm import OpenAIChatClient, load_llm_settings

        llm_client = OpenAIChatClient(load_llm_settings())
        llm_client_factory = None
    else:
        raise ValueError("LLM_ADAPTER must be fake, gms, or openai")
    if worker.embedding_adapter == "fake":
        embedding_client = FakeEmbeddingClient()
    else:
        from data_pipeline.retrieval.embedding_client import build_embedding_client

        embedding_client = build_embedding_client(worker.embedding_adapter)
    if worker.b_model_adapter == "fake":
        b_model_client = FakeBModelClient()
    else:
        from data_pipeline.b_model.client import build_b_model_client

        b_model_client = build_b_model_client(worker.b_model_adapter)
    local_environment = worker.app_env in {
        "test",
        "local",
        "development",
        "dev",
    }
    if not local_environment:
        configured = {
            "STT_ADAPTER": app.stt.adapter,
            "LLM_ADAPTER": worker.llm_adapter,
            "EMBEDDING_ADAPTER": worker.embedding_adapter,
            "B_MODEL_ADAPTER": worker.b_model_adapter,
        }
        fake_adapters = [name for name, value in configured.items() if value == "fake"]
        if fake_adapters:
            raise RuntimeError(
                "production coordinator forbids fake adapters: "
                + ", ".join(fake_adapters)
            )
    summary_generator = build_meeting_summary_generator(
        os.getenv("SUMMARY_ADAPTER", "fake"),
        app_env=worker.app_env,
    )
    component = MeetingAnalysisCoordinator(
        session_factory=sessions,
        transcript_loader=transcript_loader,
        summary_processor=summary_processor(
            session_factory=sessions,
            generator=summary_generator,
        ),
        nodes_processor=nodes_processor(
            session_factory=sessions,
            llm_client=llm_client,
            llm_client_factory=llm_client_factory,
            embedding_client=embedding_client,
            b_model_client=b_model_client,
            retrieval_settings=app.retrieval,
            b_model=os.getenv("B_MODEL_NAME", "automatic-b-model"),
        ),
        claim_timeout_seconds=float(
            os.getenv("ANALYSIS_COORDINATOR_CLAIM_TIMEOUT_SECONDS", "900")
        ),
    )
    return MeetingAnalysisRuntime(component, engine)


__all__ = [
    "MeetingAnalysisRuntime",
    "build_command_consumer_runtime",
    "build_coordinator_runtime",
    "build_recording_consumer_runtime",
]
