"""테스트용 빌더 — 가짜 판정 JSON(IF-1~IF-4 모사) 조립 + 카운트 헬퍼."""

from __future__ import annotations

import json
import pathlib

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

PROJECT = "proj-01"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def seg(segment_id: str, text: str, start_ms: int | None = None, speaker: str = "SPK_1") -> dict:
    return {"segmentId": segment_id, "text": text, "startMs": start_ms, "speakerLabel": speaker}


def ev(segment_id: str, quote: str) -> dict:
    return {"segmentId": segment_id, "quote": quote}


def item(item_id: str, type_: str, title: str, content: str, evidence: list[dict],
         category: str = "BACKEND") -> dict:
    return {
        "id": item_id, "type": type_, "predictedCategory": category,
        "title": title, "content": content, "evidence": evidence,
    }


def judgment(item_id: str, result: str, **kw) -> dict:
    out = {"itemId": item_id, "result": result}
    out.update({k: v for k, v in kw.items() if v is not None})
    return out


def request_payload(*, meeting_id: str, segments: list[dict], items: list[dict],
                    judgments: list[dict], candidates: dict | None = None,
                    request_id: str | None = None, pipeline_version: str | None = None,
                    run_type: str = "NODE_GENERATION", project_id: str = PROJECT) -> dict:
    payload = {
        "requestId": request_id or f"req-{meeting_id}",
        "projectId": project_id,
        "externalMeetingId": meeting_id,
        "runType": run_type,
        "segments": segments,
        "items": items,
        "judgments": judgments,
        "candidates": candidates or {"decisions": []},
    }
    if pipeline_version:
        payload["pipelineVersion"] = pipeline_version
    return payload


def count(session_factory: sessionmaker, model) -> int:
    with session_factory() as s:
        return s.execute(select(func.count()).select_from(model)).scalar_one()
