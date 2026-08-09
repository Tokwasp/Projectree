#!/usr/bin/env python3
"""Compare complete extraction+judgment pipeline profiles without PostgreSQL.

This is the correct comparison tool after Step 3 because each profile owns a
compatible extraction/judgment pair.  It performs two LLM calls per profile and
therefore spends more credits than ``compare_judgment_profiles.py``.

Example (run only the new default first to conserve credits):

  python tests/tools/evaluation/compare_pipeline_profiles.py \
    --segments tests/fixtures/evaluation/poc_frozen/meetings/M1_segments.json \
    --profiles poc-lts \
    --env-file .env \
    --out outputs/pipeline_compare_M1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from data_pipeline.llm import OpenAIChatClient, load_llm_settings  # noqa: E402
from data_pipeline.pipeline import run_generation_only  # noqa: E402


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _segments(path: Path) -> list[dict]:
    data = _read_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data.get("segments"), list):
        return data["segments"]
    raise ValueError(f"No segments array found in {path}")


def _stage(stage) -> dict:
    return {
        "promptSha256": stage.prompt_sha256,
        "attempts": stage.attempts,
        "error": stage.error,
        "inputTokens": stage.input_tokens,
        "outputTokens": stage.output_tokens,
        "totalTokens": stage.total_tokens,
        "latencyMs": stage.latency_ms,
        "rawResponse": stage.raw_response,
        "parsed": stage.parsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--profiles", default="poc-lts,m2-current-candidate")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--project-id", default="proj-01")
    parser.add_argument("--meeting-id", default=None)
    args = parser.parse_args()

    segments = _segments(args.segments)
    candidates = _read_json(args.candidates) if args.candidates else {"decisions": []}
    profiles = [value.strip() for value in args.profiles.split(",") if value.strip()]
    meeting_id = args.meeting_id or args.segments.stem.replace("_segments", "")

    client = OpenAIChatClient(load_llm_settings(env_file=args.env_file, require_api_key=True))
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {
        "segmentsSource": str(args.segments),
        "candidatesSource": str(args.candidates) if args.candidates else None,
        "segmentCount": len(segments),
        "profiles": [],
    }

    for profile in profiles:
        run = run_generation_only(
            meeting_input={
                "projectId": args.project_id,
                "externalMeetingId": meeting_id,
                "segments": segments,
                "candidates": candidates,
            },
            client=client,
            prompt_profile=profile,
        )
        profile_dir = args.out / run.profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "extraction_prompt.txt").write_text(run.extraction_prompt, encoding="utf-8")
        (profile_dir / "judgment_prompt.txt").write_text(run.judgment_prompt, encoding="utf-8")
        (profile_dir / "extraction.json").write_text(
            json.dumps(_stage(run.extraction), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (profile_dir / "judgment.json").write_text(
            json.dumps(
                {
                    **_stage(run.judgment),
                    "rawJudgments": run.raw_judgments,
                    "adaptedJudgments": run.judgments,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (profile_dir / "run.json").write_text(
            json.dumps(
                {
                    "pipelineProfile": run.profile_name,
                    "adapterVersion": run.adapter_version,
                    "itemCount": len(run.items),
                    "judgmentCount": len(run.judgments),
                    "droppedItemIds": run.dropped_item_ids,
                    "inputTokens": run.input_tokens,
                    "outputTokens": run.output_tokens,
                    "credits": round(run.credits, 2),
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
                "itemCount": len(run.items),
                "judgmentCount": len(run.judgments),
                "inputTokens": run.input_tokens,
                "outputTokens": run.output_tokens,
                "credits": round(run.credits, 2),
            }
        )

    summary["totalCredits"] = round(sum(row["credits"] for row in summary["profiles"]), 2)
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
