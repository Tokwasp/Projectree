#!/usr/bin/env python3
"""Run paired stage-② comparison over one frozen extraction artifact.

Both profiles receive exactly the same items, segments, and candidates.  This
script spends LLM credits but does not touch PostgreSQL.

This is a diagnostic cross-contract tool.  Use compare_pipeline_profiles.py for
production profile evaluation because extraction and judgment must stay paired.

Examples:
  python tests/tools/evaluation/compare_judgment_profiles.py \
    --items outputs/run/M1/extraction.json \
    --segments tests/fixtures/evaluation/poc_frozen/meetings/M1_segments.json \
    --env-file .env --out outputs/p1_compare_M1

``--items`` accepts either ``{"items": [...]}`` or the chain artifact shape
``{"parsed": {"items": [...]}}``.  Candidates may be omitted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from data_pipeline.llm import OpenAIChatClient, load_llm_settings  # noqa: E402
from data_pipeline.pipeline import run_judgment_only  # noqa: E402


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _items(path: Path) -> list[dict]:
    data = _read_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data.get("items"), list):
        return data["items"]
    parsed = data.get("parsed") or {}
    if isinstance(parsed.get("items"), list):
        return parsed["items"]
    raise ValueError(f"No items array found in {path}")


def _segments(path: Path) -> list[dict]:
    data = _read_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data.get("segments"), list):
        return data["segments"]
    raise ValueError(f"No segments array found in {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--profiles", default="poc-lts,m2-current-candidate")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    items = _items(args.items)
    segments = _segments(args.segments)
    candidates = _read_json(args.candidates) if args.candidates else {"decisions": []}
    profiles = [value.strip() for value in args.profiles.split(",") if value.strip()]

    client = OpenAIChatClient(load_llm_settings(env_file=args.env_file, require_api_key=True))
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {
        "itemsSource": str(args.items),
        "segmentsSource": str(args.segments),
        "candidatesSource": str(args.candidates) if args.candidates else None,
        "itemCount": len(items),
        "profiles": [],
    }

    for profile in profiles:
        run = run_judgment_only(
            client=client,
            items=items,
            segments=segments,
            candidates=candidates,
            prompt_profile=profile,
        )
        profile_dir = args.out / run.profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "prompt.txt").write_text(run.prompt, encoding="utf-8")
        (profile_dir / "result.json").write_text(
            json.dumps(
                {
                    "profile": run.profile_name,
                    "adapterVersion": run.adapter_version,
                    "promptSha256": run.judgment.prompt_sha256,
                    "attempts": run.judgment.attempts,
                    "error": run.judgment.error,
                    "inputTokens": run.judgment.input_tokens,
                    "outputTokens": run.judgment.output_tokens,
                    "credits": round(run.credits, 2),
                    "rawJudgments": run.raw_judgments,
                    "adaptedJudgments": run.adapted_judgments,
                    "rawResponse": run.judgment.raw_response,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summary["profiles"].append(
            {
                "profile": run.profile_name,
                "adapterVersion": run.adapter_version,
                "promptSha256": run.judgment.prompt_sha256,
                "judgmentCount": len(run.adapted_judgments),
                "credits": round(run.credits, 2),
            }
        )

    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
