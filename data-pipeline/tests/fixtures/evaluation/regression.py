"""M2 회귀 오케스트레이션 — 회의별 ①② 실행 → 저장 후보에서 disposition 파생 → 채점.

크레딧 상한 게이트 포함: 실행 전 누적 추정이 상한을 넘기면 중단하고 축소 실행을 권고한다.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from data_pipeline.contracts import CategorySet
from data_pipeline.llm import ChatClient
from data_pipeline.pipeline import run_meeting
from data_pipeline.prompts import get_pipeline_profile
from data_pipeline.storage import NodeCandidate

from .gold_adapter import adapt_gold_judgments, load_gold_items, load_segments
from .m2_scorer import MeetingScore, score_meeting


def derive_dispositions(session_factory: sessionmaker, project_id: str, meeting_id: str) -> dict[str, dict]:
    """DB 후보에서 항목별 suggested disposition을 파생한다."""
    with session_factory() as s:
        candidates = s.query(NodeCandidate).filter_by(
            project_id=project_id, external_meeting_id=meeting_id
        ).all()
        by_id = {str(candidate.id): candidate for candidate in candidates}
        out: dict[str, dict] = {}
        for candidate in candidates:
            parent = by_id.get(str(candidate.suggested_parent_candidate_id))
            out[candidate.source_item_id] = {
                "result": candidate.suggested_disposition,
                "parentItemId": parent.source_item_id if parent else None,
            }
    return out


def offset_storage_ok(session_factory: sessionmaker, project_id: str, meeting_id: str) -> tuple[int, int]:
    """오프셋 역산 저장 검증: (quote_start 채워진 evidence 수, 전체 evidence 수)."""
    from data_pipeline.storage import NodeCandidateEvidence

    with session_factory() as s:
        candidates = s.query(NodeCandidate).filter_by(
            project_id=project_id, external_meeting_id=meeting_id
        ).all()
        candidate_ids = [candidate.id for candidate in candidates]
        if not candidate_ids:
            return (0, 0)
        evs = s.query(NodeCandidateEvidence).filter(
            NodeCandidateEvidence.candidate_id.in_(candidate_ids)
        ).all()
        filled = sum(1 for e in evs if e.quote_start is not None)
        return (filled, len(evs))


def run_regression(
    session_factory: sessionmaker,
    meetings: list[str],
    client: ChatClient,
    *,
    project_id: str = "proj-01",
    category_set: CategorySet | None = None,
    output_dir: Path | str | None = None,
    max_credits: float | None = None,
    prompt_profile: str | None = None,
) -> dict:
    cs = category_set or CategorySet.load()
    selected_profile = get_pipeline_profile(prompt_profile).name
    scores: list[MeetingScore] = []
    per_meeting: list[dict] = []
    skipped: list[str] = []
    total_credits = 0.0
    total_in = total_out = 0

    for meeting_id in meetings:
        if max_credits is not None and total_credits >= max_credits:
            skipped.append(meeting_id)  # 크레딧 상한 게이트 — 남은 회의 중단
            continue
        segments = load_segments(meeting_id)
        gold_items = load_gold_items(meeting_id)
        expected = adapt_gold_judgments(meeting_id)
        run = run_meeting(
            session_factory,
            meeting_input={"projectId": project_id, "externalMeetingId": meeting_id,
                           "requestId": f"req-{meeting_id}-{selected_profile}", "segments": segments},
            client=client, category_set=cs, output_dir=output_dir,
            prompt_profile=selected_profile,
        )
        disp = derive_dispositions(session_factory, project_id, meeting_id)
        score = score_meeting(meeting_id, gold_items, expected, run.items, disp)
        scores.append(score)
        filled, total_ev = offset_storage_ok(session_factory, project_id, meeting_id)
        total_credits += run.credits
        total_in += run.input_tokens
        total_out += run.output_tokens
        per_meeting.append({
            "meetingId": meeting_id,
            "proposalStatus": run.proposal_result.status,
            "coverageF1": score.coverage_f1,
            "coverageRecall": score.coverage_recall,
            "coveragePrecision": score.coverage_precision,
            "resultClassAccuracy": score.result_class_accuracy,
            "confirmationAccuracy": score.confirmation_accuracy,
            "withinAttach": f"{score.within_attach_correct}/{score.within_attach_total}",
            "offsetStorage": f"{filled}/{total_ev}",
            "candidateCount": run.proposal_result.candidateCount,
            "inputTokens": run.input_tokens, "outputTokens": run.output_tokens,
            "credits": round(run.credits, 1),
            "scoreDetail": score.detail,
        })

    n = len(scores) or 1
    macro = {
        "coverageF1": round(sum(s.coverage_f1 for s in scores) / n, 3),
        "resultClassAccuracy": round(sum(s.result_class_accuracy for s in scores) / n, 3),
        "confirmationAccuracy": round(sum(s.confirmation_accuracy for s in scores) / n, 3),
    }
    return {
        "pipelineProfile": selected_profile,
        "meetings": meetings,
        "skipped": skipped,
        "perMeeting": per_meeting,
        "macro": macro,
        "totalInputTokens": total_in,
        "totalOutputTokens": total_out,
        "totalCredits": round(total_credits, 1),
    }
