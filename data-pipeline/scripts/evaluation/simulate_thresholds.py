#!/usr/bin/env python3
"""Simulate thresholds from saved results without changing runtime config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from data_pipeline.evaluation.contracts import (  # noqa: E402
    EvaluationCase,
    PilotResult,
)
from data_pipeline.evaluation.reporting import write_json  # noqa: E402
from data_pipeline.evaluation.thresholds import simulate_thresholds  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline mechanics-only threshold simulation."
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/evaluation/threshold-simulation.json"),
    )
    return parser


def _read_jsonl(path: Path, model):
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = _read_jsonl(args.cases, EvaluationCase)
    results = _read_jsonl(args.results, PilotResult)
    payload = simulate_thresholds(cases, results)
    write_json(args.output, payload)
    print(
        f"cases={len(cases)} status={payload['status']} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
