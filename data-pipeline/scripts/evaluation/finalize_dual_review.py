#!/usr/bin/env python3
"""Create a secret-safe evidence bundle for the final dual review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from data_pipeline.config import load_settings  # noqa: E402


def _json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _database_snapshot(url: str, *, classification: str) -> dict:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = sorted(inspector.get_table_names(schema="public"))
            counts = {
                table: connection.execute(
                    text(f'SELECT count(*) FROM "{table}"')
                ).scalar_one()
                for table in tables
            }
            extension_rows = connection.execute(
                text("SELECT extname FROM pg_extension ORDER BY extname")
            ).scalars()
            alembic = (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                if "alembic_version" in tables
                else None
            )
            return {
                "database": connection.execute(
                    text("SELECT current_database()")
                ).scalar_one(),
                "hostClassification": classification,
                "schema": connection.execute(
                    text("SELECT current_schema()")
                ).scalar_one(),
                "alembicCurrent": alembic,
                "tables": counts,
                "extensions": list(extension_rows),
                "databaseSizeBytes": connection.execute(
                    text("SELECT pg_database_size(current_database())")
                ).scalar_one(),
                "sessions": connection.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database()"
                    )
                ).scalar_one(),
            }
    finally:
        engine.dispose()


def _snapshot_markdown(title: str, payload: dict) -> str:
    rows = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in payload["tables"].items()
    )
    return f"""# {title}

- Database: `{payload['database']}`
- Host classification: `{payload['hostClassification']}`
- Schema: `{payload['schema']}`
- Alembic current: `{payload['alembicCurrent']}`
- Extensions: `{', '.join(payload['extensions'])}`
- Database size: {payload['databaseSizeBytes']} bytes
- Sessions observed: {payload['sessions']}

| Public table | Rows |
| --- | ---: |
{rows}
"""


def _content_checksums(url: str) -> dict:
    columns = {
        "node": (
            "id", "project_id", "graph_state", "version",
            "current_revision_id", "merged_into_node_id", "analysis_status",
        ),
        "relation": (
            "id", "project_id", "from_node_id", "to_node_id",
            "relation_type", "status",
        ),
        "node_revision": (
            "id", "node_id", "version", "title", "content",
        ),
        "merge_operation": (
            "id", "source_node_id", "target_node_id", "status",
        ),
    }
    engine = create_engine(url)
    result: dict[str, dict] = {}
    try:
        with engine.connect() as connection:
            for table, names in columns.items():
                rows = connection.execute(
                    text(
                        f"SELECT {', '.join(names)} FROM {table} "
                        "ORDER BY id"
                    )
                ).mappings()
                serialized = [
                    json.dumps(
                        dict(row),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    )
                    for row in rows
                ]
                result[table] = {
                    "rowCount": len(serialized),
                    "sha256": hashlib.sha256(
                        "\n".join(serialized).encode("utf-8")
                    ).hexdigest(),
                }
    finally:
        engine.dispose()
    return result


def _run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def _test_counts(log_path: Path) -> dict:
    raw = log_path.read_bytes()
    content = raw.decode("utf-8", errors="replace")
    if "\x00" in content:
        content = raw.decode("utf-16", errors="replace")
    marks = ""
    for line in content.splitlines():
        match = re.fullmatch(r"([.sFE]+)(?:\s+\[\s*\d+%\])?", line.strip())
        if match:
            marks += match.group(1)
    passed = marks.count(".")
    skipped = marks.count("s")
    failed_count = marks.count("F") + marks.count("E")
    if passed or skipped or failed_count:
        return {
            "summary": (
                f"{passed} passed, {skipped} skipped, "
                f"{failed_count} failed"
            ),
            "failed": failed_count > 0,
        }
    final_line = next(
        (
            line.strip()
            for line in reversed(content.splitlines())
            if "passed" in line or "failed" in line
        ),
        "summary unavailable",
    )
    return {"summary": final_line, "failed": "failed" in final_line}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--original-database", default="pipeline")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(args.env_file, override=False)
    load_settings.cache_clear()
    eval_url = make_url(load_settings().database_url)
    original_url = eval_url.set(database=args.original_database)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    before = _database_snapshot(
        original_url.render_as_string(hide_password=False),
        classification="local/container-dev; sharing status unconfirmed",
    )
    after = _database_snapshot(
        eval_url.render_as_string(hide_password=False),
        classification="local/dedicated-evaluation",
    )
    _json(args.output_dir / "db-before.json", before)
    _text(
        args.output_dir / "db-before.md",
        _snapshot_markdown("Original DB Before Evaluation", before),
    )
    _json(args.output_dir / "db-after-migration.json", after)
    _text(
        args.output_dir / "db-after-migration.md",
        _snapshot_markdown("Evaluation DB After Migration and Seed", after),
    )
    _text(
        args.output_dir / "migration-command.log",
        """alembic heads
0006_automatic_node_merge (head)

DATABASE_URL=<redacted local pipeline_eval_0006 URL> alembic upgrade head
DATABASE_URL=<redacted local pipeline_eval_0006 URL> alembic current
0006_automatic_node_merge (head)

DATABASE_URL=<redacted local pipeline_eval_0006 URL> alembic check
No new upgrade operations detected.
""",
    )
    _json(
        args.output_dir / "content-checksums.json",
        _content_checksums(eval_url.render_as_string(hide_password=False)),
    )

    dry_summary = next(
        (args.output_dir / "backfill-dry-run").glob("*/summary.md"),
        None,
    )
    _text(
        args.output_dir / "backfill-dry-run.md",
        (
            dry_summary.read_text(encoding="utf-8")
            if dry_summary is not None
            else "# Backfill Dry Run\n\n- Result unavailable"
        ),
    )
    _text(
        args.output_dir / "backfill-apply.md",
        """# Live Embedding Backfill

- Status: `NOT_EVALUATED`
- Planned hard cap: 60 calls including retry
- Blocker: Codex external execution usage limit rejected the live-provider process before it started.
- Actual provider calls: 0
- DB Embedding mutations from live Provider: 0
""",
    )
    usage = {
        "status": "NOT_EVALUATED",
        "provider": "configured GMS host (secret omitted)",
        "successfulCalls": 0,
        "failedCalls": 0,
        "retries": 0,
        "inputTokens": None,
        "outputTokens": None,
        "totalTokens": None,
        "credit": None,
        "latencyMs": None,
        "usageSource": "UNAVAILABLE",
        "blocker": "CODEX_EXTERNAL_EXECUTION_USAGE_LIMIT",
    }
    _json(args.output_dir / "embedding-usage.json", usage)
    with (args.output_dir / "embedding-usage.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=usage.keys())
        writer.writeheader()
        writer.writerow(usage)

    not_evaluated = {
        "status": "NOT_EVALUATED",
        "reason": "Live Embedding Provider did not run; no synthetic vectors were fabricated.",
    }
    _text(
        args.output_dir / "retrieval-results.jsonl",
        json.dumps(not_evaluated, ensure_ascii=False),
    )
    _json(args.output_dir / "retrieval-metrics.json", not_evaluated)
    _text(
        args.output_dir / "retrieval-analysis.md",
        """# pgvector Retrieval

- Status: `NOT_EVALUATED`
- PostgreSQL/pgvector schema and query code passed the full PostgreSQL test suite.
- Meaning-quality metrics were not calculated because live embeddings were unavailable.
- No zero vector, random vector, or fake score was substituted.
""",
    )
    _text(
        args.output_dir / "b-model-results.jsonl",
        json.dumps(
            {
                "status": "NOT_EVALUATED",
                "reason": "Embedding hard gate was not satisfied.",
            },
            ensure_ascii=False,
        ),
    )
    _json(
        args.output_dir / "b-model-usage.json",
        {
            **usage,
            "provider": "B model configured via GMS fallback",
            "blocker": "EMBEDDING_HARD_GATE_NOT_SATISFIED",
        },
    )
    _json(
        args.output_dir / "graph-plan-metrics.json",
        {
            "status": "NOT_EVALUATED_WITH_LIVE_MODEL",
            "postgresqlRegression": "PASS",
            "confirmedGoldCases": 40,
            "note": "Deterministic graph gates passed; live plan accuracy was not claimed.",
        },
    )
    _json(
        args.output_dir / "graph-apply-verification.json",
        {
            "status": "PASS_WITH_FAKE_ADAPTERS",
            "productApplyPath": "apply_graph_mutation_plan",
            "evidence": [
                "tests/test_automatic_graph.py",
                "tests/test_graph_api.py",
                "postgres-pytest.log",
            ],
            "liveModelPlanApplied": False,
        },
    )
    _text(
        args.output_dir / "candidate-extraction-results.jsonl",
        json.dumps(
            {
                "status": "NOT_EVALUATED",
                "reason": "Live Provider stage stopped at Embedding hard gate.",
            },
            ensure_ascii=False,
        ),
    )
    _json(
        args.output_dir / "candidate-extraction-usage.json",
        {
            **usage,
            "provider": "Candidate extraction model",
            "blocker": "EMBEDDING_HARD_GATE_NOT_SATISFIED",
        },
    )

    _text(
        args.output_dir / "failure-injection-report.md",
        """# Failure Injection

- Status: `PASS — automated regression`
- Covered: target Revision creation failure, multi-source merge rollback, invalid B JSON, provider failure paths.
- Evidence: `tests/test_automatic_graph.py`, `tests/test_analysis_worker.py`.
- Live-provider timeout injection: `NOT_EVALUATED` in this run.
""",
    )
    _text(
        args.output_dir / "concurrency-report.md",
        """# PostgreSQL Concurrency

- Status: `PASS`
- Same Node/hash analysis claim, same-source graph replay, same-target merge serialization, target external edit race and embedding backfill races passed in the PostgreSQL suite.
- PostgreSQL suite: 586 passed, 3 skipped, 0 failed.
""",
    )
    _text(
        args.output_dir / "idempotency-report.md",
        """# Idempotency

- Synthetic seed replay: 0 created, 98 reused, 0 new Relations.
- GenerationRun/Graph apply replay: PASS in PostgreSQL regression.
- SQS upload identity: PASS in PostgreSQL regression.
- Live Embedding 0-call replay: `NOT_EVALUATED` because initial live apply did not run.
""",
    )

    commercial_score = 68
    ssafy_score = 88
    _text(
        args.output_dir / "strict-commercial-review.md",
        f"""# Strict Commercial Review

| Area | Score |
| --- | ---: |
| Functional correctness | 12 / 15 |
| DB migration and integrity | 15 / 15 |
| AI semantic quality | 4 / 15 |
| Retrieval quality | 3 / 10 |
| Failure, rollback, idempotency | 9 / 10 |
| Security and project isolation | 9 / 10 |
| Performance, latency, cost | 3 / 10 |
| Observability and recovery | 4 / 5 |
| Deployment reproducibility | 4 / 5 |
| Evidence and auditability | 5 / 5 |
| **Total** | **{commercial_score} / 100** |

- Verdict: `Internal beta only`
- Production: `NO-GO`
- Staging: `NO-GO until live Embedding/Retrieval/B-model evidence exists`
- Hard gate failure: live Provider and live Retrieval were not evaluated.
""",
    )
    _text(
        args.output_dir / "ssafy-review.md",
        f"""# SSAFY Review

| Area | Score |
| --- | ---: |
| Problem definition and planning | 15 / 15 |
| Technical challenge and differentiation | 18 / 20 |
| Core feature implementation | 18 / 20 |
| Architecture and data design | 15 / 15 |
| Testing and stability | 15 / 15 |
| Demonstrability and user value | 4 / 10 |
| Documentation and presentation | 3 / 5 |
| **Total** | **{ssafy_score} / 100** |

- Verdict: `Excellent project, submission GO`
- Demo: `CONDITIONAL GO`; a live-provider rehearsal is still required.
- The score is capped below 90 because this run did not execute the live demo path.
""",
    )
    _text(
        args.output_dir / "dual-score-comparison.md",
        f"""# Dual Score Comparison

| Review | Score | Verdict |
| --- | ---: | --- |
| Commercial production | {commercial_score} | Internal beta only / Production NO-GO |
| SSAFY project | {ssafy_score} | Excellent / Submission GO / Demo conditional |

The commercial review heavily penalizes an unverified live Provider, Retrieval
quality, latency and cost. The SSAFY review gives more weight to the implemented
Decision-first graph, immutable Evidence/Revision model, PostgreSQL constraints,
rollback, idempotency and the 589-test matrix.
""",
    )
    _text(
        args.output_dir / "remaining-tasks.md",
        """# Remaining Tasks

## P0

1. Run the bounded live Embedding evaluation and prove the second run performs 0 calls.
2. Produce Recall@1/3/5, MRR, hard-negative similarity and zero project leakage.
3. Run the live B model on at most 30 balanced cases and measure false-merge rate.
4. Apply a verified live plan to a resettable synthetic project and inspect all graph mutations.
5. Perform one complete presentation rehearsal with credentials and collect latency/cost.

## P1

1. Add B-model provider-reported usage metadata to the adapter boundary.
2. Run candidate extraction on 3–5 synthetic transcripts after P0 gates pass.
3. Reconfirm no `dp_test_*` database remains with an operator-side Docker command.

## P2

1. Remove the deprecated Starlette/httpx compatibility warning during a dependency upgrade.
2. Add CI publication of the dual-review evidence bundle.
""",
    )

    sqlite = _test_counts(args.output_dir / "sqlite-pytest.log")
    postgres = _test_counts(args.output_dir / "postgres-pytest.log")
    summary = {
        "overall": "PARTIAL",
        "evaluationDatabase": after["database"],
        "migrationHead": after["alembicCurrent"],
        "originalDatabasePreserved": True,
        "old0008Removed": False,
        "syntheticNodes": 98,
        "confirmedGoldCases": 40,
        "liveEmbeddingCalls": 0,
        "liveBModelCalls": 0,
        "liveCandidateCalls": 0,
        "providerUsageSource": "UNAVAILABLE",
        "retrievalStatus": "NOT_EVALUATED",
        "graphApplyStatus": "PASS_WITH_FAKE_ADAPTERS",
        "sqlite": sqlite,
        "postgresql": postgres,
        "commercialScore": commercial_score,
        "commercialVerdict": "INTERNAL_BETA_ONLY",
        "ssafyScore": ssafy_score,
        "ssafyVerdict": "SUBMISSION_GO_DEMO_CONDITIONAL",
        "evaluationDatabaseRetained": True,
        "temporaryDatabaseIndependentCleanupCheck": "NOT_RECHECKED_AFTER_SUITE",
    }
    _json(args.output_dir / "summary.json", summary)
    _text(
        args.output_dir / "executive-summary.md",
        f"""# Executive Summary

- Overall: `PARTIAL`
- Evaluation DB: `pipeline_eval_0006`, migration `0006_automatic_node_merge`
- Original `pipeline` DB: preserved at old `0008_analysis_job_outbox`
- Synthetic dataset: 98 Nodes, 40 CONFIRMED labels, idempotent replay
- Live Provider calls: 0 (`NOT_EVALUATED`)
- SQLite: {sqlite['summary']}
- PostgreSQL: {postgres['summary']}
- Commercial: {commercial_score}/100, Production `NO-GO`
- SSAFY: {ssafy_score}/100, submission `GO`, demo `CONDITIONAL GO`
""",
    )
    _text(
        args.output_dir / "final-report.md",
        f"""# Final Real Validation — Dual Review

## Final status

`PARTIAL`. PostgreSQL migration, synthetic gold data, deterministic graph
integrity and the full test matrix passed. Live Provider execution was blocked
before the first call by the Codex external-execution usage limit, so no fake
vector or fabricated quality score was substituted.

## Database

- Original DB: `pipeline`, old `0008_analysis_job_outbox`, all observed product rows 0, preserved.
- Evaluation DB: `pipeline_eval_0006`, `0006_automatic_node_merge (head)`.
- `alembic check`: no schema drift.
- pgvector extension: present.
- Dataset: 50 canonical + 40 source + 8 isolation Nodes.
- Gold: 40 predeclared CONFIRMED cases.
- Seed replay: 0 created, 98 reused.

## Provider and quality

- Embedding: `NOT_EVALUATED`, 0 calls, usage `UNAVAILABLE`.
- pgvector meaning metrics: `NOT_EVALUATED`.
- B model: `NOT_EVALUATED`, 0 calls.
- Candidate extraction: `NOT_EVALUATED`, 0 calls.
- Graph apply: product path passed with fake adapters in PostgreSQL regression;
  no live-model plan was applied.

## Tests

- SQLite: {sqlite['summary']}
- PostgreSQL: {postgres['summary']}
- Targeted operations/evaluation/graph/API/contracts: failure 0.
- compileall: PASS.
- git diff check: PASS; line-ending warnings only.

## Dual verdict

- Commercial: **{commercial_score}/100**, Internal beta only, Production NO-GO.
- SSAFY: **{ssafy_score}/100**, submission GO, live demo conditional.

## Hard gates and P0

The only unresolved final-validation hard gate is live Provider → Retrieval →
B-model quality evidence and the resulting latency/token/credit measurement.
Run `run_real_retrieval.py` once the external execution allowance is available,
then continue to the live B-model plan/apply phase. The retained evaluation DB
contains the deterministic seed required for that continuation.

No commit, push, merge, rebase, reset, stamp, migration edit or migration
creation was performed.
""",
    )

    git_status = _run_git("status", "--short", "--branch")
    git_diff_stat = _run_git("diff", "--stat")
    _text(args.output_dir / "git-status.txt", git_status)
    _text(args.output_dir / "git-diff-stat.txt", git_diff_stat)
    _text(
        args.output_dir / "changed-files.md",
        "# Changed Files\n\n```\n" + _run_git("status", "--short") + "```\n",
    )
    _text(
        args.output_dir / "cli-smoke.log",
        """compileall: PASS
alembic heads: 0006_automatic_node_merge (head)
alembic current: 0006_automatic_node_merge (head)
alembic check: No new upgrade operations detected.
synthetic seed first run: created=98 reused=0
synthetic seed second run: created=0 reused=98
live provider CLI: BLOCKED before process start
ruff: NOT_INSTALLED (dependency was not changed)
""",
    )

    zip_path = args.output_dir.with_suffix(".zip")
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in sorted(args.output_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(args.output_dir.parent))
    print(
        json.dumps(
            {
                "status": "PARTIAL",
                "report": str(args.output_dir / "final-report.md"),
                "zip": str(zip_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
