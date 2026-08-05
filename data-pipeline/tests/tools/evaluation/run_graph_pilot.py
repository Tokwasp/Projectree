#!/usr/bin/env python3
"""Run read-only pgvector pilot cases and prove table immutability."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from data_pipeline.config import load_settings  # noqa: E402
from tests.evaluation_support.contracts import EvaluationCase  # noqa: E402
from tests.evaluation_support.metrics import compute_metrics  # noqa: E402
from tests.evaluation_support.reporting import write_json, write_jsonl  # noqa: E402
from tests.evaluation_support.runner import run_read_only_pilot  # noqa: E402
from data_pipeline.storage.db import make_engine, make_session_factory  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only Retrieval evaluation from a JSONL case queue."
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/evaluation/pilot"),
    )
    return parser


def _read_cases(path: Path) -> list[EvaluationCase]:
    return [
        EvaluationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.env_file.is_file():
        load_dotenv(args.env_file, override=False)
    load_settings.cache_clear()
    settings = load_settings()
    cases = _read_cases(args.cases)
    engine = make_engine(settings.database_url)
    try:
        session = make_session_factory(engine)()
        try:
            results, verification = run_read_only_pilot(
                session,
                cases=cases,
                settings=settings.retrieval,
            )
        finally:
            session.close()
    finally:
        engine.dispose()
    write_jsonl(args.output_dir / "evaluation-results.jsonl", results)
    write_json(
        args.output_dir / "metrics.json",
        compute_metrics(cases, results),
    )
    write_json(args.output_dir / "read-only-verification.json", verification)
    print(
        f"cases={len(cases)} unchanged={verification['unchanged']} "
        f"output={args.output_dir}"
    )
    return 0 if verification["unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
