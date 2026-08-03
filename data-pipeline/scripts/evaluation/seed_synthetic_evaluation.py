#!/usr/bin/env python3
"""Seed and verify the permanent synthetic evaluation projects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from data_pipeline.config import load_settings  # noqa: E402
from data_pipeline.evaluation.synthetic.labels import build_gold_labels  # noqa: E402
from data_pipeline.evaluation.synthetic.scenarios import build_synthetic_cases  # noqa: E402
from data_pipeline.evaluation.synthetic.seed import seed_synthetic_evaluation  # noqa: E402
from data_pipeline.storage import make_engine, make_session_factory  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.env_file.is_file():
        load_dotenv(args.env_file, override=False)
    load_settings.cache_clear()
    engine = make_engine(load_settings().database_url)
    factory = make_session_factory(engine)
    session = factory()
    try:
        report = seed_synthetic_evaluation(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    labels = build_gold_labels(build_synthetic_cases())
    (args.output_dir / "synthetic-labels.jsonl").write_text(
        "\n".join(
            row.model_dump_json(by_alias=True, exclude_none=False)
            for row in labels
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "synthetic-seed-report.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "synthetic-dataset-summary.md").write_text(
        "\n".join(
            [
                "# Synthetic Gold Dataset",
                "",
                f"- Dataset version: `{report.dataset_version}`",
                f"- Main project Nodes: {report.main_node_count}",
                f"- Isolation project Nodes: {report.isolation_node_count}",
                f"- CONFIRMED gold cases: {report.gold_case_count}",
                f"- Created Nodes: {report.created_nodes}",
                f"- Reused Nodes: {report.reused_nodes}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
