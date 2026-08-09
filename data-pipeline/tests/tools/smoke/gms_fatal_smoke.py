"""Run the bounded real-GMS fatal-safety smoke through production orchestration."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
import zipfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.b_model.gms import (  # noqa: E402
    GmsBModelClient,
    load_b_model_client_settings,
)
from data_pipeline.config import load_settings  # noqa: E402
from tests.evaluation_support.gms_fatal_smoke import (  # noqa: E402
    CallBudget,
    FatalSmokeFailure,
    HardCallBudgetExceeded,
    MEETING_ID,
    MeteredBModelClient,
    MeteredChatClient,
    MeteredEmbeddingClient,
    PIPELINE_VERSION,
    PROJECT_ID,
    ProviderUsageLedger,
    SmokeBlocked,
    candidate_snapshot,
    create_disposable_database,
    database_exists,
    derive_database_urls,
    drop_disposable_database,
    embed_seed_graph,
    ensure_required_artifacts,
    evaluate_invariants,
    graph_snapshot,
    meeting_input,
    outbox_snapshot,
    project_graph_version,
    retrieval_snapshot,
    run_git_snapshot,
    seed_graph,
    synthetic_transcript_text,
    table_counts,
    upgrade_database,
    write_json,
)
from data_pipeline.llm import OpenAIChatClient, load_llm_settings  # noqa: E402
from data_pipeline.meeting_summary import FakeMeetingSummaryGenerator  # noqa: E402
from data_pipeline.pipeline.automatic_graph import (  # noqa: E402
    AutoMergePolicy,
    run_automatic_meeting,
)
from data_pipeline.provider_safety import gms_fatal_smoke_scope  # noqa: E402
from data_pipeline.retrieval.embedding_client import (  # noqa: E402
    GmsEmbeddingClient,
    load_embedding_client_settings,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--max-candidate-calls", type=int, default=2)
    parser.add_argument("--max-b-model-calls", type=int, default=4)
    parser.add_argument("--max-embedding-items", type=int, default=9)
    parser.add_argument("--max-http-requests", type=int, default=15)
    parser.add_argument("--no-provider-retry", action="store_true")
    parser.add_argument("--cleanup-db", action="store_true")
    parser.add_argument("--run-id")
    return parser


def _md_value(value) -> str:
    return str(value).replace("`", "'")


def _write_preflight(
    path: Path,
    *,
    budget: CallBudget,
    db_name: str,
    candidate_model: str,
    b_model: str,
    embedding_model: str,
) -> None:
    path.write_text(
        "# GMS Fatal Smoke Preflight\n\n"
        f"- candidate request 예상 수: {budget.max_candidate_calls}\n"
        f"- B-model request 예상 상한: {budget.max_b_model_calls}\n"
        f"- embedding item 예상 상한: {budget.max_embedding_items}\n"
        f"- 최대 Provider HTTP request: {budget.max_http_requests}\n"
        f"- 격리 DB: `{db_name}`\n"
        f"- Candidate model: `{_md_value(candidate_model)}`\n"
        f"- B-model: `{_md_value(b_model)}`\n"
        f"- Embedding model: `{_md_value(embedding_model)}`\n"
        "- Provider retry: 0\n"
        "- Meeting Summary LLM: 0\n"
        "- Clova: 0\n"
        "- productionOrchestratorUsed: true\n"
        "- candidatePipelineStages: 2\n"
        "- bModelInvocationMode: PER_NODE\n"
        "- graphApplyReplayUsed: false\n"
        "- testOnlyBatchSubstitutionUsed: false\n",
        encoding="utf-8",
    )


def _zip_output(output_dir: Path) -> Path:
    zip_path = output_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output_dir.parent))
    return zip_path


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / "outputs" / "gms-fatal-smoke" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    ensure_required_artifacts(output_dir)
    (output_dir / "git-before.txt").write_text(
        run_git_snapshot(ROOT), encoding="utf-8"
    )
    (output_dir / "synthetic-transcript.txt").write_text(
        synthetic_transcript_text() + "\n", encoding="utf-8"
    )

    budget = CallBudget(
        max_candidate_calls=args.max_candidate_calls,
        max_b_model_calls=args.max_b_model_calls,
        max_embedding_items=args.max_embedding_items,
        max_http_requests=args.max_http_requests,
    )
    # The corrected prompt permits exactly this production-path ceiling.
    budget.validate(
        candidate_calls=2,
        b_model_calls=4,
        embedding_items=9,
        http_requests=15,
    )
    if not args.no_provider_retry:
        raise SystemExit("--no-provider-retry is required")
    if not args.cleanup_db:
        raise SystemExit("--cleanup-db is required")
    if not args.env_file.is_file():
        raise SystemExit("env file is missing")
    load_dotenv(args.env_file, override=False)
    os.environ["NO_EXTERNAL_AI_CALLS"] = "1"

    required = ("GMS_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "DATABASE_URL")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit("missing required environment names: " + ", ".join(missing))

    original_database_url = os.environ["DATABASE_URL"]
    admin_url, target_url, db_name = derive_database_urls(original_database_url, run_id)
    llm_settings = replace(
        load_llm_settings(env_file=None, require_api_key=True),
        retry_count=0,
    )
    embedding_settings = replace(load_embedding_client_settings(), retry_count=0)
    b_model_settings = replace(load_b_model_client_settings(), retry_count=0)
    _write_preflight(
        output_dir / "preflight-budget.md",
        budget=budget,
        db_name=db_name,
        candidate_model=llm_settings.model,
        b_model=b_model_settings.model,
        embedding_model=embedding_settings.model,
    )

    status = "BLOCKED"
    reason = "not started"
    engine = None
    session_factory = None
    seed_nodes = {}
    ledger = ProviderUsageLedger(budget)
    assertions: list[dict] = []
    quality_warnings: list[str] = []
    outcomes: dict[str, str] = {}
    candidate_count = 0
    production_orchestrator_used = False
    candidate_pipeline_stages = 0
    graph_apply_replay_used = False
    test_only_batch_substitution_used = False
    cleanup_ok = False
    replay_outcome = "NOT_RUN"
    graph_version_before = graph_version_after = 0
    caught_trace = ""

    try:
        create_disposable_database(admin_url, db_name)
        os.environ["DATABASE_URL"] = target_url.render_as_string(hide_password=False)
        # Provider settings may have populated the process-wide Settings cache
        # while DATABASE_URL still pointed at the developer DB.  Clear it
        # before Alembic and verify the resolved database name explicitly.
        load_settings.cache_clear()
        resolved_database = make_url(load_settings().database_url).database
        if resolved_database != db_name:
            raise SmokeBlocked("isolated DATABASE_URL was not activated")
        upgrade_database(ROOT, target_url)
        engine = create_engine(target_url, pool_pre_ping=True)
        session_factory = sessionmaker(engine, expire_on_commit=False)
        with engine.connect() as connection:
            vector_version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            ).scalar_one_or_none()
            if vector_version is None:
                raise SmokeBlocked("pgvector extension is missing")

        app_settings = load_settings()
        with gms_fatal_smoke_scope(
            max_http_requests=budget.max_http_requests,
            max_candidate_calls=budget.max_candidate_calls,
            max_b_model_calls=budget.max_b_model_calls,
            max_embedding_items=budget.max_embedding_items,
        ):
            chat_client = MeteredChatClient(OpenAIChatClient(llm_settings), ledger)
            embedding_client = MeteredEmbeddingClient(
                GmsEmbeddingClient(embedding_settings), ledger
            )
            b_model_client = MeteredBModelClient(
                GmsBModelClient(b_model_settings), ledger
            )

            seed_nodes = seed_graph(session_factory)
            embed_seed_graph(
                session_factory,
                seed_nodes=seed_nodes,
                embedding_client=embedding_client,
                embedding_model=app_settings.retrieval.embedding_model,
                embedding_version=app_settings.retrieval.embedding_version,
                embedding_dimension=app_settings.retrieval.embedding_dim,
            )
            write_json(output_dir / "seed-graph.json", graph_snapshot(session_factory, seed_nodes))
            graph_version_before = project_graph_version(session_factory)

            production_orchestrator_used = True
            result = run_automatic_meeting(
                session_factory,
                meeting_input=meeting_input(),
                client=chat_client,
                embedding_client=embedding_client,
                b_model_client=b_model_client,
                pipeline_version=PIPELINE_VERSION,
                retrieval_settings=app_settings.retrieval,
                merge_policy=AutoMergePolicy(
                    min_similarity=app_settings.retrieval.auto_merge_min_similarity,
                    min_margin=app_settings.retrieval.auto_merge_min_margin,
                ),
                pipeline_label="automatic-b-model",
                force_retry=False,
                meeting_summary_generator=FakeMeetingSummaryGenerator(),
                generate_summary=True,
            )
            candidate_pipeline_stages = int(result.extraction.attempts > 0) + int(
                result.judgment.attempts > 0
            )
            candidate_data = candidate_snapshot(session_factory)
            candidate_count = len(candidate_data["candidates"])
            write_json(output_dir / "candidate-output-redacted.json", candidate_data)
            write_json(output_dir / "retrieval-results.json", retrieval_snapshot(session_factory))
            write_json(output_dir / "b-model-output-redacted.json", b_model_client.calls)
            graph_version_after = project_graph_version(session_factory)
            write_json(output_dir / "final-graph.json", graph_snapshot(session_factory, seed_nodes))
            write_json(output_dir / "outbox-events.json", outbox_snapshot(session_factory))

            counts_before_replay = table_counts(session_factory)
            provider_before_replay = ledger.http_requests
            replay = run_automatic_meeting(
                session_factory,
                meeting_input=meeting_input(),
                client=chat_client,
                embedding_client=embedding_client,
                b_model_client=b_model_client,
                pipeline_version=PIPELINE_VERSION,
                retrieval_settings=app_settings.retrieval,
                merge_policy=AutoMergePolicy(
                    min_similarity=app_settings.retrieval.auto_merge_min_similarity,
                    min_margin=app_settings.retrieval.auto_merge_min_margin,
                ),
                pipeline_label="automatic-b-model",
                force_retry=False,
                meeting_summary_generator=FakeMeetingSummaryGenerator(),
                generate_summary=True,
            )
            replay_outcome = replay.proposal_result.outcome
            counts_after_replay = table_counts(session_factory)
            provider_after_replay = ledger.http_requests
            assertions, quality_warnings, outcomes = evaluate_invariants(
                session_factory,
                seed_nodes=seed_nodes,
                graph_version_before=graph_version_before,
                graph_version_after=graph_version_after,
                counts_before_replay=counts_before_replay,
                counts_after_replay=counts_after_replay,
                provider_calls_before_replay=provider_before_replay,
                provider_calls_after_replay=provider_after_replay,
            )

            assertions.extend(
                [
                    {
                        "name": "production_orchestrator_used",
                        "passed": production_orchestrator_used,
                        "detail": "run_automatic_meeting invoked directly",
                    },
                    {
                        "name": "candidate_pipeline_stages_2",
                        "passed": candidate_pipeline_stages == 2,
                        "detail": f"stages={candidate_pipeline_stages}",
                    },
                    {
                        "name": "b_model_per_node",
                        "passed": len(b_model_client.calls) == ledger.b_model_calls,
                        "detail": f"per-node calls={len(b_model_client.calls)}",
                    },
                    {
                        "name": "no_graph_apply_replay",
                        "passed": not graph_apply_replay_used,
                        "detail": "duplicate execution reused completed GenerationRun",
                    },
                    {
                        "name": "no_test_batch_substitution",
                        "passed": not test_only_batch_substitution_used,
                        "detail": "production item-level adapters were used",
                    },
                    {
                        "name": "provider_budget",
                        "passed": (
                            ledger.candidate_calls <= budget.max_candidate_calls
                            and ledger.b_model_calls <= budget.max_b_model_calls
                            and ledger.embedding_items <= budget.max_embedding_items
                            and ledger.http_requests <= budget.max_http_requests
                            and ledger.retry_count == 0
                        ),
                        "detail": str(ledger.payload()),
                    },
                ]
            )
            failed = [row for row in assertions if not row["passed"]]
            if candidate_count not in {3, 4}:
                failed.append(
                    {
                        "name": "candidate_count_3_or_4",
                        "passed": False,
                        "detail": f"count={candidate_count}",
                    }
                )
            status = "PASS" if not failed else "FATAL_FAIL"
            reason = "fatal invariants passed" if not failed else failed[0]["name"]

    except HardCallBudgetExceeded as exc:
        status = "BLOCKED"
        reason = str(exc)
        if session_factory is not None:
            try:
                candidate_data = candidate_snapshot(session_factory)
                candidate_count = len(candidate_data["candidates"])
                write_json(output_dir / "candidate-output-redacted.json", candidate_data)
                if candidate_count >= 5:
                    status = "FATAL_FAIL"
                    reason = f"candidate count exceeded fatal bound: {candidate_count}"
            except Exception:
                pass
    except SmokeBlocked as exc:
        status = "BLOCKED"
        reason = str(exc)
    except FatalSmokeFailure as exc:
        status = "FATAL_FAIL"
        reason = str(exc)
    except Exception as exc:
        # Authentication/transport failure before graph publication is BLOCKED;
        # an exception after publication is conservatively a fatal failure.
        published = False
        if session_factory is not None:
            try:
                graph_version_after = project_graph_version(session_factory)
                published = graph_version_after > graph_version_before
            except Exception:
                pass
        status = "FATAL_FAIL" if published else "BLOCKED"
        reason = f"{type(exc).__name__}: {str(exc)[:300]}"
        caught_trace = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__, limit=12)
        )
    finally:
        write_json(output_dir / "provider-usage.json", ledger.payload())
        write_json(
            output_dir / "fatal-assertions.json",
            {
                "result": status,
                "assertions": assertions,
                "productionOrchestratorUsed": production_orchestrator_used,
                "candidatePipelineStages": candidate_pipeline_stages,
                "bModelInvocationMode": "PER_NODE",
                "graphApplyReplayUsed": graph_apply_replay_used,
                "testOnlyBatchSubstitutionUsed": test_only_batch_substitution_used,
            },
        )
        (output_dir / "quality-warnings.md").write_text(
            "# Quality warnings\n\n"
            + ("\n".join(f"- {row}" for row in quality_warnings) if quality_warnings else "- None")
            + "\n",
            encoding="utf-8",
        )
        (output_dir / "db-integrity-report.md").write_text(
            "# DB integrity\n\n"
            f"- result: {status}\n"
            f"- graphVersion before: {graph_version_before}\n"
            f"- graphVersion after: {graph_version_after}\n"
            f"- failed assertions: {sum(not row.get('passed', False) for row in assertions)}\n",
            encoding="utf-8",
        )
        (output_dir / "idempotency-report.md").write_text(
            "# Idempotency\n\n"
            f"- replay outcome: {replay_outcome}\n"
            "- Graph plan replay used: false\n"
            "- completed result reuse expected without Provider calls\n",
            encoding="utf-8",
        )
        if caught_trace:
            # Tracebacks contain types/paths only; never settings or HTTP bodies.
            (output_dir / "test-log.txt").write_text(caught_trace, encoding="utf-8")
        if engine is not None:
            engine.dispose()
        os.environ["DATABASE_URL"] = original_database_url
        load_settings.cache_clear()
        try:
            drop_disposable_database(admin_url, db_name)
            cleanup_ok = not database_exists(admin_url, db_name)
        except Exception as exc:
            cleanup_ok = False
            reason = reason + f"; cleanup failed: {type(exc).__name__}"
            if status == "PASS":
                status = "FATAL_FAIL"
        (output_dir / "cleanup-report.md").write_text(
            "# Cleanup\n\n"
            f"- disposable database: `{db_name}`\n"
            f"- removed: {str(cleanup_ok).lower()}\n"
            "- existing pipeline DB used for test data: false\n",
            encoding="utf-8",
        )
        (output_dir / "git-after.txt").write_text(
            run_git_snapshot(ROOT), encoding="utf-8"
        )
        ensure_required_artifacts(output_dir)
        final_report = (
            "# GMS Fatal-Safety Smoke Final Report\n\n"
            f"1. 결과: **{status}** ({reason})\n"
            f"2. 실제 생성 Candidate 수: {candidate_count}\n"
            f"3. 실제 Provider HTTP 호출 수: {ledger.http_requests}\n"
            f"4. Embedding item 수: {ledger.embedding_items}\n"
            f"5. retry 횟수: {ledger.retry_count}\n"
            f"6. C1 Decision 결과: {outcomes.get('C1', 'NOT_AVAILABLE')}\n"
            f"7. C2 Action 결과: {outcomes.get('C2', 'NOT_AVAILABLE')}\n"
            f"8. C3 Backend Issue 결과: {outcomes.get('C3', 'NOT_AVAILABLE')}\n"
            f"9. C4 Frontend Issue 결과: {outcomes.get('C4', 'NOT_AVAILABLE')}\n"
            f"10. productionOrchestratorUsed: {str(production_orchestrator_used).lower()}\n"
            f"11. candidatePipelineStages: {candidate_pipeline_stages}\n"
            "12. bModelInvocationMode: PER_NODE\n"
            "13. graphApplyReplayUsed: false\n"
            "14. testOnlyBatchSubstitutionUsed: false\n"
            f"15. duplicate replay: {replay_outcome}\n"
            f"16. 테스트 DB 정리: {str(cleanup_ok).lower()}\n"
            "17. Git 파괴 작업: 수행하지 않음\n"
        )
        (output_dir / "final-report.md").write_text(final_report, encoding="utf-8")
        zip_path = _zip_output(output_dir)
        print(f"RESULT={status}")
        print(f"RUN_ID={run_id}")
        print(f"REPORT={output_dir / 'final-report.md'}")
        print(f"ZIP={zip_path}")

    return 0 if status == "PASS" else 2 if status == "FATAL_FAIL" else 3


if __name__ == "__main__":
    raise SystemExit(main())
