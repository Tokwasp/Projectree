"""Offline candidate-quality evaluation against gold fixtures.

Scores captured extraction/judgment outputs (or, opt-in, a live provider run)
against ``evaluation/candidate_quality/gold/*.json``. LLM output is never
pinned to exact strings in CI: this script is a diagnostic, not a unit test.

Usage:
    # score previously captured outputs
    python scripts/evaluate_candidate_quality.py \
        --actual evaluation/candidate_quality/actual-20260801 \
        --out outputs/candidate-quality-eval/report.json

    # opt-in live run for every gold scenario (needs GMS_KEY etc.)
    python scripts/evaluate_candidate_quality.py --live --profile candidate-quality-v1 ...

Targets (documented, aspirational for the gold set):
    required recall            >= 95%
    noise candidates           <= 2%
    action lifecycle accuracy  >= 90%
    parent hint accuracy (Top) >= 95%
    false canonicalization     == 0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

GOLD_DIR = Path("evaluation/candidate_quality/gold")


def _match_required(required: dict, items: list[dict]) -> dict | None:
    for item in items:
        if str(item.get("type", "")).upper() != required["type"]:
            continue
        title = str(item.get("title", ""))
        if any(kw in title for kw in required["titleAnyOf"]):
            return item
    return None


def _judgment_for(item_id: str, judgments: list[dict]) -> dict | None:
    for j in judgments:
        if str(j.get("itemId")) == item_id:
            return j
    return None


def evaluate_scenario(gold: dict, actual: dict) -> dict:
    items = actual.get("items", [])
    judgments = actual.get("judgments", [])
    lifecycles = actual.get("storedLifecycles") or {}

    matched: dict[str, dict] = {}
    missing: list[str] = []
    lifecycle_hits = lifecycle_total = 0
    for required in gold.get("required", []):
        item = _match_required(required, items)
        if item is None:
            missing.append(required["key"])
            continue
        matched[required["key"]] = item
        expected_lc = required.get("lifecycle")
        if required["type"] == "ACTION":
            lifecycle_total += 1
            actual_lc = (
                lifecycles.get(str(item.get("id")))
                if lifecycles
                else item.get("lifecycleStatus")
            )
            if actual_lc == expected_lc:
                lifecycle_hits += 1

    noise = [
        str(item.get("title", ""))
        for item in items
        if any(kw in str(item.get("title", "")) for kw in gold.get("forbiddenTitleKeywords", []))
    ]

    parent_hits = parent_total = 0
    for edge in gold.get("expectedParentEdges", []):
        child = matched.get(edge["childKey"])
        parent = matched.get(edge["parentKey"])
        if child is None or parent is None:
            continue
        parent_total += 1
        j = _judgment_for(str(child.get("id")), judgments)
        if j and str(j.get("attachTo")) == str(parent.get("id")):
            parent_hits += 1

    canonical_violations: list[str] = []
    guard = gold.get("uncertainTermGuard")
    if guard:
        for item in items:
            text = f"{item.get('title','')} {item.get('content','')}"
            for bad in guard["forbiddenCanonicalizations"]:
                if bad.lower() in text.lower():
                    canonical_violations.append(f"{item.get('id')}:{bad}")

    total_required = len(gold.get("required", []))
    return {
        "scenario": gold["scenario"],
        "requiredTotal": total_required,
        "requiredFound": total_required - len(missing),
        "requiredRecall": (
            round((total_required - len(missing)) / total_required, 4)
            if total_required else None
        ),
        "missing": missing,
        "candidateCount": len(items),
        "noiseCandidates": noise,
        "noiseRate": round(len(noise) / len(items), 4) if items else 0.0,
        "lifecycleTotal": lifecycle_total,
        "lifecycleHits": lifecycle_hits,
        "lifecycleAccuracy": (
            round(lifecycle_hits / lifecycle_total, 4) if lifecycle_total else None
        ),
        "parentEdgeTotal": parent_total,
        "parentEdgeHits": parent_hits,
        "parentEdgeAccuracy": (
            round(parent_hits / parent_total, 4) if parent_total else None
        ),
        "falseCanonicalizations": canonical_violations,
    }


def _live_generate(gold: dict, profile_name: str) -> dict:
    """Opt-in: run extraction+judgment against the live provider."""

    import os

    from data_pipeline.config import load_category_values
    from data_pipeline.llm import OpenAIChatClient, load_llm_settings
    from data_pipeline.prompts import render_extraction_prompt, render_judgment_prompt

    if not os.getenv("GMS_KEY"):
        raise SystemExit("blocked: GMS_KEY is not configured for a live run")
    client = OpenAIChatClient(load_llm_settings())
    meeting_id = f"eval-{gold['scenario']}"
    segments = gold["segments"]
    extraction_prompt = render_extraction_prompt(
        profile_name,
        segments=segments,
        category_values=load_category_values(),
        meeting_id=meeting_id,
    )
    extraction = json.loads(
        client.complete([{"role": "user", "content": extraction_prompt}]).raw_response
    )
    judgment_prompt = render_judgment_prompt(
        profile_name,
        items=extraction.get("items", []),
        candidates={"decisions": []},
        segments=segments,
        meeting_id=meeting_id,
    )
    judgments = json.loads(
        client.complete([{"role": "user", "content": judgment_prompt}]).raw_response
    )
    return {
        "meetingId": meeting_id,
        "profile": profile_name,
        "items": extraction.get("items", []),
        "judgments": judgments.get("judgments", []),
    }


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(Path(".env"), override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", type=Path, help="directory of captured outputs")
    parser.add_argument("--live", action="store_true", help="call the real provider (opt-in)")
    parser.add_argument("--profile", default="candidate-quality-v1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.actual and not args.live:
        raise SystemExit("provide --actual DIR and/or --live")

    scenario_reports = []
    for gold_path in sorted(GOLD_DIR.glob("*.json")):
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        actual = None
        source = None
        if args.live:
            actual = _live_generate(gold, args.profile)
            source = "live"
        elif args.actual:
            # captured file may be named after the scenario or the meeting id
            for candidate_name in (
                f"{gold['scenario']}.json",
                f"e2e-meeting-{gold['scenario'][-1].upper()}.json",
            ):
                path = args.actual / candidate_name
                if path.exists():
                    actual = json.loads(path.read_text(encoding="utf-8"))
                    source = str(path)
                    break
        if actual is None:
            scenario_reports.append(
                {"scenario": gold["scenario"], "skipped": "no actual output available"}
            )
            continue
        report = evaluate_scenario(gold, actual)
        report["source"] = source
        scenario_reports.append(report)

    summary = {
        "profile": args.profile,
        "targets": {
            "requiredRecall": ">=0.95",
            "noiseRate": "<=0.02",
            "lifecycleAccuracy": ">=0.90",
            "parentEdgeAccuracy": ">=0.95",
            "falseCanonicalizations": "==0",
        },
        "scenarios": scenario_reports,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
