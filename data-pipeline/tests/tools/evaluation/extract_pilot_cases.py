#!/usr/bin/env python3
"""Extract a content-free, read-only Graph pilot queue."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from data_pipeline.config import load_settings  # noqa: E402
from tests.evaluation_support.extraction import extract_pilot_cases  # noqa: E402
from tests.evaluation_support.reporting import write_jsonl  # noqa: E402
from data_pipeline.storage.db import make_engine, make_session_factory  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract up to 50 unlabeled Node IDs without product mutation."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--limit", type=int, default=45)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/evaluation/review-queue.jsonl"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.env_file.is_file():
        load_dotenv(args.env_file, override=False)
    load_settings.cache_clear()
    settings = load_settings()
    engine = make_engine(settings.database_url)
    try:
        session = make_session_factory(engine)()
        try:
            cases = extract_pilot_cases(
                session,
                project_id=args.project_id,
                limit=args.limit,
            )
            session.rollback()
        finally:
            session.close()
    finally:
        engine.dispose()
    write_jsonl(args.output, cases)
    print(f"cases={len(cases)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
