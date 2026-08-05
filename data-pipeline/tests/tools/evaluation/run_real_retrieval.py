#!/usr/bin/env python3
"""Bounded live Embedding backfill and PostgreSQL pgvector evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from data_pipeline.config import load_settings  # noqa: E402
from tests.evaluation_support.runner import run_read_only_pilot  # noqa: E402
from tests.evaluation_support.synthetic.labels import build_gold_labels  # noqa: E402
from tests.evaluation_support.synthetic.scenarios import (  # noqa: E402
    ISOLATION_PROJECT_ID,
    MAIN_PROJECT_ID,
    build_isolation_nodes,
    build_synthetic_cases,
    stable_uuid,
)
from data_pipeline.operations.embedding_backfill import (  # noqa: E402
    BackfillOptions,
    run_embedding_backfill,
)
from data_pipeline.retrieval.embedding_client import (  # noqa: E402
    build_embedding_client,
)
from data_pipeline.storage import (  # noqa: E402
    Node,
    NodeEmbedding,
    make_engine,
    make_session_factory,
)

REAL_CALL_CAP = 60


class _NoCallClient:
    def embed(self, **_kwargs):
        raise AssertionError("idempotent replay attempted a provider call")


def _selected_nodes():
    cases = build_synthetic_cases()
    selected_cases = cases[:34]
    labels = build_gold_labels(selected_cases)
    node_ids = {label.source_node_id for label in labels}
    node_ids.update(
        label.expected_target_node_id
        for label in labels
        if label.expected_target_node_id is not None
    )
    node_ids.update(
        label.expected_parent_node_id
        for label in labels
        if label.expected_parent_node_id is not None
    )
    # Two READY near-duplicates are enough to make cross-project leakage
    # observable while keeping the total live-call budget at exactly 60.
    isolation = build_isolation_nodes()[:2]
    node_ids.update(row.node_id for row in isolation)
    return selected_cases, labels, sorted(node_ids, key=str)


def _usage_summary(rows: list[dict], latencies: list[int]) -> dict:
    ordered = sorted(latencies)

    def percentile(value: float) -> int | None:
        if not ordered:
            return None
        index = min(len(ordered) - 1, math.ceil(value * len(ordered)) - 1)
        return ordered[index]

    def total(field: str):
        values = [row.get(field) for row in rows if row.get(field) is not None]
        return sum(values) if values else None

    return {
        "callsAttempted": len(latencies),
        "callsSucceeded": len(rows),
        "callsFailed": len(latencies) - len(rows),
        "inputTokens": total("inputTokens"),
        "outputTokens": total("outputTokens"),
        "totalTokens": total("totalTokens"),
        "credit": total("credit"),
        "averageLatencyMs": (
            int(sum(ordered) / len(ordered)) if ordered else None
        ),
        "p50LatencyMs": percentile(0.50),
        "p95LatencyMs": percentile(0.95),
        "retryCount": sum(int(row.get("retryCount") or 0) for row in rows),
        "usageSources": sorted(
            {str(row.get("usageSource") or "UNAVAILABLE") for row in rows}
        ),
    }


def _retrieval_metrics(cases, results) -> dict:
    by_case = {row.case_id: row for row in results}
    positives = [
        row
        for row in cases
        if row.expected_target_node_id is not None
        and row.expected_action in {"MERGE", "LINK"}
    ]
    ranks: list[int] = []
    for case in positives:
        result = by_case[case.case_id]
        rank = next(
            (
                candidate.rank
                for candidate in result.candidates
                if candidate.node_id == case.expected_target_node_id
            ),
            0,
        )
        ranks.append(rank)
    all_candidates = [
        candidate
        for result in results
        for candidate in result.candidates
    ]
    isolation_ids = {row.node_id for row in build_isolation_nodes()}
    hard_negative_ids = {
        row.case_id for row in cases if row.category == "hard-negative"
    }
    hard_negative_top = [
        max(
            (candidate.similarity for candidate in by_case[case_id].candidates),
            default=None,
        )
        for case_id in hard_negative_ids
    ]
    return {
        "evaluatedCases": len(cases),
        "positiveCases": len(positives),
        "recallAt1": (
            sum(0 < rank <= 1 for rank in ranks) / len(ranks)
            if ranks
            else None
        ),
        "recallAt3": (
            sum(0 < rank <= 3 for rank in ranks) / len(ranks)
            if ranks
            else None
        ),
        "recallAt5": (
            sum(0 < rank <= 5 for rank in ranks) / len(ranks)
            if ranks
            else None
        ),
        "mrr": (
            sum(1 / rank if rank else 0 for rank in ranks) / len(ranks)
            if ranks
            else None
        ),
        "projectLeakageCount": sum(
            candidate.node_id in isolation_ids for candidate in all_candidates
        ),
        "typeFilterViolationCount": sum(
            not candidate.type_valid for candidate in all_candidates
        ),
        "hardNegativeTopSimilarity": hard_negative_top,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(args.env_file, override=False)
    load_settings.cache_clear()
    settings = load_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    selected_cases, labels, node_ids = _selected_nodes()
    if len(node_ids) > REAL_CALL_CAP:
        raise SystemExit(
            f"selected node count {len(node_ids)} exceeds cap {REAL_CALL_CAP}"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    client = build_embedding_client("gms")
    provider_usage: list[dict] = []
    provider_latencies: list[int] = []
    results: list[dict] = []
    started = time.monotonic()
    for node_id in node_ids:
        session = factory()
        try:
            project_id = session.execute(
                select(Node.project_id).where(Node.id == node_id)
            ).scalar_one()
            session.rollback()
        finally:
            session.close()
        report = run_embedding_backfill(
            factory,
            options=BackfillOptions(
                project_id=project_id,
                node_id=node_id,
                apply=True,
                max_calls=1,
            ),
            embedding_client_factory=lambda: client,
            settings=settings.retrieval,
        )
        provider_usage.extend(report.provider_usage)
        provider_latencies.extend(report.provider_latencies_ms)
        results.extend(row.as_dict() for row in report.results)
        if report.failed:
            break

    usage = _usage_summary(provider_usage, provider_latencies)
    usage["hardCap"] = REAL_CALL_CAP
    usage["selectedNodes"] = len(node_ids)
    usage["wallClockMs"] = int((time.monotonic() - started) * 1000)
    (args.output_dir / "embedding-usage.json").write_text(
        json.dumps(usage, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (args.output_dir / "embedding-usage.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "inputTokens",
                "outputTokens",
                "totalTokens",
                "credit",
                "usageSource",
                "latencyMs",
                "retryCount",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(provider_usage)
    (args.output_dir / "backfill-apply.md").write_text(
        "\n".join(
            [
                "# Live Embedding Backfill",
                "",
                f"- Selected Nodes: {len(node_ids)}",
                f"- Provider calls: {usage['callsAttempted']}",
                f"- Successful calls: {usage['callsSucceeded']}",
                f"- Failed calls: {usage['callsFailed']}",
                f"- Usage source: {', '.join(usage['usageSources'])}",
                f"- P95 latency: {usage['p95LatencyMs']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if usage["callsFailed"]:
        engine.dispose()
        print(json.dumps(usage))
        return 2

    replay_results: list[dict] = []
    for node_id in node_ids:
        session = factory()
        try:
            project_id = session.execute(
                select(Node.project_id).where(Node.id == node_id)
            ).scalar_one()
            session.rollback()
        finally:
            session.close()
        replay = run_embedding_backfill(
            factory,
            options=BackfillOptions(
                project_id=project_id,
                node_id=node_id,
                apply=True,
                max_calls=1,
            ),
            embedding_client_factory=lambda: _NoCallClient(),
            settings=settings.retrieval,
        )
        replay_results.extend(row.as_dict() for row in replay.results)
    reusable_count = sum(row["reason"] == "READY_REUSABLE" for row in replay_results)
    (args.output_dir / "backfill-idempotency.json").write_text(
        json.dumps(
            {
                "selectedNodes": len(node_ids),
                "readyReusable": reusable_count,
                "providerCalls": 0,
                "passed": reusable_count == len(node_ids),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    retrieval_cases = labels[:30]
    session = factory()
    try:
        pilot_results, mutation_proof = run_read_only_pilot(
            session,
            cases=retrieval_cases,
            settings=settings.retrieval,
        )
        ready_count = session.execute(
            select(func.count()).select_from(NodeEmbedding).where(
                NodeEmbedding.status == "READY"
            )
        ).scalar_one()
        session.rollback()
    finally:
        session.close()
        engine.dispose()
    metrics = _retrieval_metrics(retrieval_cases, pilot_results)
    metrics["readyEmbeddingCount"] = ready_count
    metrics["planOnlyDatabaseUnchanged"] = mutation_proof["unchanged"]
    (args.output_dir / "retrieval-results.jsonl").write_text(
        "\n".join(
            row.model_dump_json(by_alias=True) for row in pilot_results
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "retrieval-metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "retrieval-analysis.md").write_text(
        "\n".join(
            [
                "# Live pgvector Retrieval",
                "",
                f"- Recall@1: {metrics['recallAt1']}",
                f"- Recall@3: {metrics['recallAt3']}",
                f"- Recall@5: {metrics['recallAt5']}",
                f"- MRR: {metrics['mrr']}",
                f"- Project leakage: {metrics['projectLeakageCount']}",
                f"- Type violations in raw Top-K: {metrics['typeFilterViolationCount']}",
                f"- Read-only proof: {metrics['planOnlyDatabaseUnchanged']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"usage": usage, "retrieval": metrics}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
