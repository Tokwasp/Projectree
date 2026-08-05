#!/usr/bin/env python3
"""노드 생성 회귀 실행 (실 LLM). ①② 종단 실행 → PG 반영 → 채점.

기본 profile은 A의 완전한 PoC LTS pair(`poc-lts`)다. 기존 재작성 체인은
`m2-current-candidate`를 명시해야만 실행된다.

예:
  DATABASE_URL 는 이 스크립트가 임시 파일 DB 로 자동 설정한다(별도 불필요).
  python tests/tools/evaluation/run_node_generation_regression.py --meetings M2X --env-file /home/ssafy/poc-node-extraction/.env
  python tests/tools/evaluation/run_node_generation_regression.py --meetings M2X,M2Y,M1,M2,M3 --max-credits 8000

키는 --env-file 의 .env(GMS_KEY)에서만 읽는다(커밋 금지).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from data_pipeline.config import load_settings  # noqa: E402
from data_pipeline.contracts import CategorySet  # noqa: E402
from data_pipeline.llm import OpenAIChatClient, load_llm_settings  # noqa: E402
from data_pipeline.storage.db import make_engine, make_session_factory  # noqa: E402
from tests.fixtures.evaluation.regression import run_regression  # noqa: E402


def _build_schema(db_url: str) -> None:
    os.environ["DATABASE_URL"] = db_url
    load_settings.cache_clear()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "data_pipeline" / "storage" / "migrations"))
    command.upgrade(cfg, "head")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meetings", default="M2X,M2Y,M1,M2,M3")
    ap.add_argument("--env-file", default="/home/ssafy/poc-node-extraction/.env")
    ap.add_argument("--max-credits", type=float, default=8000.0)
    ap.add_argument("--profile", default="poc-lts",
                    choices=["poc-lts", "m2-current-candidate", "poc-v4-lts", "m2-current"])
    ap.add_argument("--out-subdir", default=None)
    ap.add_argument("--db", default=None, help="기본: outputs 아래 임시 sqlite 파일")
    args = ap.parse_args()

    llm_settings = load_llm_settings(env_file=args.env_file, require_api_key=True)
    client = OpenAIChatClient(llm_settings)

    out_root = ROOT / "outputs" / (args.out_subdir or f"regression_{args.profile}")
    out_root.mkdir(parents=True, exist_ok=True)
    db_path = args.db or str(out_root / "graph.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    db_url = f"sqlite:///{db_path}"
    _build_schema(db_url)

    session_factory = make_session_factory(make_engine(db_url))
    meetings = [m.strip() for m in args.meetings.split(",") if m.strip()]
    print(f"model={llm_settings.model} profile={args.profile} meetings={meetings} max_credits={args.max_credits}")

    report = run_regression(session_factory, meetings, client, category_set=CategorySet.load(),
                            output_dir=out_root, max_credits=args.max_credits,
                            prompt_profile=args.profile)
    (out_root / "regression_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== node-generation regression ===")
    hdr = f"{'meeting':7} {'proposal':14} {'covF1':6} {'rClass':7} {'confirm':8} {'attach':7} {'offset':7} {'cred':7}"
    print(hdr)
    for m in report["perMeeting"]:
        print(f"{m['meetingId']:7} {m['proposalStatus']:14} {m['coverageF1']:<6} {m['resultClassAccuracy']:<7} "
              f"{m['confirmationAccuracy']:<8} {m['withinAttach']:7} {m['offsetStorage']:7} {m['credits']:<7}")
    print(f"macro: {report['macro']}")
    print(f"skipped(credit gate): {report['skipped']}")
    print(f"TOTAL credits={report['totalCredits']} in={report['totalInputTokens']} out={report['totalOutputTokens']}")
    print(f"report: {out_root / 'regression_report.json'}")


if __name__ == "__main__":
    main()
