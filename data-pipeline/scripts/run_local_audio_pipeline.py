"""Run the production STT and node-generation boundary from one local audio file.

This is an integration diagnostic, not an alternate production ingestion path.
It deliberately requires a disposable ``dp_test_*`` database so real provider
calls can be checked without mutating the development database.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

from data_pipeline.config import SttSettings, load_settings
from data_pipeline.llm import OpenAIChatClient, load_llm_settings
from data_pipeline.pipeline import run_meeting
from data_pipeline.storage import make_engine, make_session_factory
from data_pipeline.stt import build_transcriber
from data_pipeline.worker.fakes import FakeMeetingChatClient


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--meeting-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--segments-file",
        type=Path,
        help="Reuse a prior STT segment JSON file for provider-stage diagnosis.",
    )
    parser.add_argument(
        "--stt-adapter",
        choices=("fake", "clova"),
        required=True,
    )
    parser.add_argument(
        "--llm-adapter",
        choices=("fake", "openai"),
        required=True,
    )
    return parser.parse_args()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    args = _arguments()
    load_dotenv(args.env_file, override=False)
    database_url = os.getenv("DATABASE_URL", "")
    database_name = make_url(database_url).database or ""
    if not database_name.startswith("dp_test_"):
        raise RuntimeError(
            "Local integration runner requires a disposable dp_test_* database"
        )
    if not args.audio.is_file():
        raise FileNotFoundError(args.audio)

    load_settings.cache_clear()
    app_settings = load_settings()
    stt_settings = SttSettings(
        adapter=args.stt_adapter,
        fake_response_path=app_settings.stt.fake_response_path,
        clova_invoke_url=app_settings.stt.clova_invoke_url,
        clova_secret=app_settings.stt.clova_secret,
        clova_timeout_seconds=app_settings.stt.clova_timeout_seconds,
    )
    transcriber = build_transcriber(stt_settings)
    if args.llm_adapter == "fake":
        llm_client = FakeMeetingChatClient(args.meeting_id)
    else:
        llm_client = OpenAIChatClient(load_llm_settings())

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    metrics: dict[str, object] = {
        "projectId": args.project_id,
        "meetingId": args.meeting_id,
        "audioFile": args.audio.name,
        "audioBytes": args.audio.stat().st_size,
        "sttAdapter": args.stt_adapter,
        "llmAdapter": args.llm_adapter,
        "startedAt": started_at.isoformat(),
    }
    engine = make_engine(database_url)
    try:
        if args.segments_file is not None:
            loaded = json.loads(args.segments_file.read_text(encoding="utf-8"))
            if not isinstance(loaded, list) or not loaded:
                raise ValueError("segments file must contain a non-empty array")
            segments = loaded
            metrics["sttLatencyMs"] = 0
            metrics["sttReused"] = True
        else:
            stt_started = time.perf_counter()
            segments = transcriber.transcribe(
                args.audio,
                meeting_id=args.meeting_id,
            )
            metrics["sttLatencyMs"] = round(
                (time.perf_counter() - stt_started) * 1000
            )
            metrics["sttReused"] = False
        metrics["segmentCount"] = len(segments)
        _write_json(output_dir / "stt_segments.json", segments)

        pipeline_started = time.perf_counter()
        result = run_meeting(
            make_session_factory(engine),
            meeting_input={
                "requestId": f"local-integration-{args.meeting_id}",
                "projectId": args.project_id,
                "externalMeetingId": args.meeting_id,
                "segments": segments,
            },
            client=llm_client,
            output_dir=output_dir / "pipeline",
        )
        metrics["pipelineLatencyMs"] = round(
            (time.perf_counter() - pipeline_started) * 1000
        )
        metrics["pipelineStatus"] = result.proposal_result.status
        metrics["pipelineOutcome"] = result.proposal_result.outcome
        metrics["candidateCount"] = result.proposal_result.candidateCount
        metrics["inputTokens"] = result.input_tokens
        metrics["outputTokens"] = result.output_tokens
        metrics["credits"] = result.credits
        metrics["completedAt"] = datetime.now(timezone.utc).isoformat()
        _write_json(output_dir / "summary.json", metrics)
        print(json.dumps(metrics, ensure_ascii=False))
        if result.proposal_result.status not in {
            "REVIEW_PENDING",
            "REVIEW_COMPLETED",
            "COMPLETED",
        }:
            raise RuntimeError(
                "Pipeline ended without a durable success status: "
                f"{result.proposal_result.status}/"
                f"{result.proposal_result.outcome}"
            )
    except Exception as exc:
        metrics["failedAt"] = datetime.now(timezone.utc).isoformat()
        metrics["errorType"] = type(exc).__name__
        metrics["error"] = str(exc)
        _write_json(output_dir / "failure.json", metrics)
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
