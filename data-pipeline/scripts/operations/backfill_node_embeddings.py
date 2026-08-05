#!/usr/bin/env python3
"""Project-scoped Node embedding backfill CLI (dry-run by default)."""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from data_pipeline.config import load_settings  # noqa: E402
from data_pipeline.operations.embedding_backfill import (  # noqa: E402
    BackfillOptions,
    run_embedding_backfill,
    write_backfill_report,
)
from data_pipeline.retrieval.embedding_client import (  # noqa: E402
    build_embedding_client,
)
from data_pipeline.storage.db import make_engine, make_session_factory  # noqa: E402


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return parsed


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a UUID") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill current-Revision Node embeddings. "
            "The default mode is a non-mutating dry-run."
        )
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--states", default="ACTIVE,UNATTACHED")
    parser.add_argument("--node-id", type=_uuid)
    parser.add_argument("--limit", type=_positive_int)
    parser.add_argument("--batch-size", type=_positive_int, default=100)
    parser.add_argument("--after-node-id", type=_uuid)
    parser.add_argument("--max-calls", type=_positive_int)
    parser.add_argument("--sleep-seconds", type=_non_negative_float, default=0.0)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("outputs/embedding-backfill"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Allow provider calls and node_embedding writes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.env_file.is_file():
        load_dotenv(args.env_file, override=False)
    load_settings.cache_clear()
    settings = load_settings()
    states = tuple(
        state.strip().upper()
        for state in args.states.split(",")
        if state.strip()
    )
    try:
        options = BackfillOptions(
            project_id=args.project_id,
            states=states,
            node_id=args.node_id,
            limit=args.limit,
            batch_size=args.batch_size,
            after_node_id=args.after_node_id,
            max_calls=args.max_calls,
            sleep_seconds=args.sleep_seconds,
            apply=args.apply,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    engine = make_engine(settings.database_url)
    try:
        report = run_embedding_backfill(
            make_session_factory(engine),
            options=options,
            embedding_client_factory=(
                (lambda: build_embedding_client()) if args.apply else None
            ),
            settings=settings.retrieval,
            run_id=run_id,
        )
    finally:
        engine.dispose()
    report_directory = args.report_dir / run_id
    write_backfill_report(report, report_directory=report_directory)
    counts = report.counts()
    print(
        "mode={mode} scanned={scanned} reusable={reusable} "
        "would_generate={would_generate} generated={generated} "
        "deferred={deferred} failed={failed}".format(
            mode=report.mode,
            scanned=counts["scanned"],
            reusable=counts["reusable"],
            would_generate=counts["wouldGenerate"],
            generated=counts["generated"],
            deferred=counts["deferred"],
            failed=counts["failed"],
        )
    )
    print(f"report={report_directory}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
