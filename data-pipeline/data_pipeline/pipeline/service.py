"""파이프라인 apply 경로 진입점 (M1). LLM 없음 — 가짜 판정 JSON 을 입력으로 받는다.

process_request:
  0. 멱등성   — request UNIQUE(project, meeting, pipeline_version, run_type). 동일 재전송=DUPLICATE,
                같은 키에 다른 payload_hash=REJECTED. (규칙: UNIQUE + 처리 상태, advisory lock 없음)
  1. 저장     — meeting/segments upsert (세그먼트도 UNIQUE 로 멱등)
  2. 검증     — validate_judgments (규칙 1~6)
  3. Plan     — build_change_plan (규칙 8 생성)
  4. 반영     — apply_change_plan (규칙 7·8·9). 성공만 commit, STALE/REJECT 는 전체 롤백.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from data_pipeline.contracts import (
    ApplyResult,
    CategorySet,
    DemotedEntry,
    Lineage,
    ProposalPersistResult,
)
from data_pipeline.contracts.lineage import PIPELINE_VERSION
from data_pipeline.storage.models import NodeCandidate, Request
from data_pipeline.validation import SegmentInfo, build_change_plan, validate_judgments

from .apply import apply_change_plan
from .errors import ApplyError, StaleVersionError
from .repository import (
    create_generation_candidates,
    get_node,
    list_candidates_for_request,
    normalize_extraction_items,
    update_request_generation_metadata,
    upsert_meeting,
    upsert_segments,
)

_DEFAULT_RUN_TYPE = "NODE_GENERATION"
_PROPOSAL_RUN_TYPE = "CANDIDATE_GENERATION"
GENERATION_INPUT_HASH_VERSION = "generation-input-v1"


def payload_hash(payload: dict) -> str:
    """멱등성 판정용 해시. LLM 산출물(segments/items/candidates/judgments)만 대상."""
    core = {
        "segments": payload.get("segments", []),
        "items": payload.get("items", []),
        "candidates": payload.get("candidates", {}),
        "judgments": payload.get("judgments", []),
    }
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _segment_info(payload: dict) -> dict[str, SegmentInfo]:
    return {
        s["segmentId"]: SegmentInfo(text=s.get("text", ""), start_ms=s.get("startMs"))
        for s in payload.get("segments", [])
        if s.get("segmentId")
    }


def _candidate_allowlists(candidates: dict) -> tuple[set[str], dict[str, str]]:
    decision_ids = {
        d.get("decisionId") for d in candidates.get("decisions", []) if d.get("decisionId")
    }
    action_status = {
        a.get("actionId"): a.get("status", "IN_PROGRESS")
        for d in candidates.get("decisions", [])
        for a in d.get("actions", [])
        if a.get("actionId")
    }
    return decision_ids, action_status


@dataclass(frozen=True)
class GenerationClaim:
    outcome: str
    request_db_id: uuid.UUID
    result: ProposalPersistResult | None = None
    previous_usage: dict | None = None
    run_attempt: int = 1

    @property
    def claimed(self) -> bool:
        return self.outcome == "CLAIMED"


def _proposal_result_for_request(
    session,
    *,
    existing: Request,
) -> ProposalPersistResult:
    rows = list_candidates_for_request(session, existing.id)
    counts = Counter(row.suggested_disposition for row in rows)
    if existing.status == "REVIEW_PENDING":
        return ProposalPersistResult(
            requestId=existing.external_request_id,
            externalMeetingId=existing.external_meeting_id,
            status="REVIEW_PENDING",
            outcome="DUPLICATE_REVIEW_PENDING",
            candidateIds=[str(row.id) for row in rows],
            candidateCount=len(rows),
            suggestedDispositionCounts=dict(counts),
            warnings=list(existing.warnings or []),
        )
    if existing.status == "PROCESSING":
        return ProposalPersistResult(
            requestId=existing.external_request_id,
            externalMeetingId=existing.external_meeting_id,
            status="PROCESSING",
            outcome="IN_PROGRESS",
        )
    if existing.status == "FAILED":
        stage = existing.failure_stage or "PERSISTENCE"
        return ProposalPersistResult(
            requestId=existing.external_request_id,
            externalMeetingId=existing.external_meeting_id,
            status="FAILED",
            outcome=f"FAILED_{stage}",
            warnings=list(existing.warnings or []),
            detail={
                "failureStage": existing.failure_stage,
                "failureCode": existing.failure_code,
                "previouslyFailed": True,
            },
        )
    return ProposalPersistResult(
        requestId=existing.external_request_id,
        externalMeetingId=existing.external_meeting_id,
        status=existing.status,
        outcome="DUPLICATE_READY",
    )


def _insert_generation_claim(session, request_row: Request) -> None:
    """Small seam used by the unique-conflict recovery test."""

    session.add(request_row)
    session.flush()


def claim_generation_request(
    session_factory: sessionmaker,
    *,
    project_id: str,
    external_meeting_id: str,
    external_request_id: str,
    pipeline_version: str,
    input_hash: str,
    input_hash_version: str = GENERATION_INPUT_HASH_VERSION,
    run_type: str = _PROPOSAL_RUN_TYPE,
    lineage: Lineage | dict | None = None,
    force_retry: bool = False,
) -> GenerationClaim:
    """Claim an input in a transaction that is committed before any LLM call."""

    lineage_dict = (
        lineage.model_dump(mode="json", exclude_none=True)
        if isinstance(lineage, Lineage)
        else dict(lineage or {})
    )
    session = session_factory()
    try:
        existing = session.execute(
            select(Request).where(
                Request.project_id == project_id,
                Request.external_meeting_id == external_meeting_id,
                Request.input_hash == input_hash,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == "FAILED" and force_retry:
                had_previous_usage = existing.usage is not None
                previous_usage = dict(existing.usage or {})
                previous_runs = list(previous_usage.get("runs") or [])
                run_attempt = len(previous_runs) + 1
                if had_previous_usage and not previous_runs:
                    run_attempt = 2
                session.execute(
                    delete(NodeCandidate).where(NodeCandidate.request_id == existing.id)
                )
                existing.status = "PROCESSING"
                existing.failure_stage = None
                existing.failure_code = None
                existing.failure_message = None
                existing.completed_at = None
                existing.warnings = None
                existing.raw_extraction = None
                existing.raw_judgment = None
                existing.payload_hash = None
                existing.lineage = lineage_dict
                session.commit()
                return GenerationClaim(
                    "CLAIMED",
                    existing.id,
                    previous_usage=previous_usage,
                    run_attempt=run_attempt,
                )
            result = _proposal_result_for_request(session, existing=existing)
            session.rollback()
            semantic_outcome = {
                "REVIEW_PENDING": "DUPLICATE_READY",
                "PROCESSING": "IN_PROGRESS",
                "FAILED": "PREVIOUSLY_FAILED",
            }.get(existing.status, "DUPLICATE_READY")
            return GenerationClaim(semantic_outcome, existing.id, result)

        request_row = Request(
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            external_request_id=external_request_id,
            pipeline_version=pipeline_version,
            run_type=run_type,
            input_hash=input_hash,
            input_hash_version=input_hash_version,
            payload_hash=None,
            status="PROCESSING",
            lineage=lineage_dict,
        )
        try:
            _insert_generation_claim(session, request_row)
            session.commit()
            return GenerationClaim("CLAIMED", request_row.id)
        except IntegrityError:
            session.rollback()
            winner = session.execute(
                select(Request).where(
                    Request.project_id == project_id,
                    Request.external_meeting_id == external_meeting_id,
                    Request.input_hash == input_hash,
                )
            ).scalar_one()
            result = _proposal_result_for_request(session, existing=winner)
            session.rollback()
            semantic_outcome = {
                "REVIEW_PENDING": "DUPLICATE_READY",
                "PROCESSING": "IN_PROGRESS",
                "FAILED": "PREVIOUSLY_FAILED",
            }.get(winner.status, "DUPLICATE_READY")
            return GenerationClaim(semantic_outcome, winner.id, result)
    finally:
        session.close()


def finalize_generation_candidates(
    session_factory: sessionmaker,
    payload: dict,
    *,
    request_db_id: uuid.UUID,
    raw_items: list[dict] | None,
    raw_extraction: dict | list | str | None,
    raw_judgment: dict | list | str | None,
    lineage: Lineage | dict,
    usage: dict,
    warnings: list[str] | None = None,
    warning_failure_stage: str | None = None,
    warning_failure_code: str | None = None,
) -> ProposalPersistResult:
    """Finalize one claimed request in a single candidate transaction."""

    project_id = payload["projectId"]
    meeting_id = payload["externalMeetingId"]
    request_id = payload.get("requestId", f"req-{meeting_id}")
    phash = payload_hash(payload)
    lineage_dict = (
        lineage.model_dump(mode="json", exclude_none=True)
        if isinstance(lineage, Lineage)
        else dict(lineage)
    )
    raw_judgment_values = (
        raw_judgment.get("judgments") if isinstance(raw_judgment, dict) else None
    )
    raw_judgments = (
        [dict(value) for value in raw_judgment_values if isinstance(value, dict)]
        if isinstance(raw_judgment_values, list)
        else []
    )

    session = session_factory()
    try:
        request_row = session.get(Request, request_db_id)
        if request_row is None:
            raise RuntimeError("claimed request not found")
        if request_row.status != "PROCESSING":
            raise RuntimeError(f"claimed request is not PROCESSING: {request_row.status}")

        meeting = upsert_meeting(session, project_id, meeting_id)
        upsert_segments(session, project_id, meeting_id, payload.get("segments", []))

        items = payload.get("items", [])
        candidates = payload.get("candidates", {}) or {}
        decision_ids, action_status = _candidate_allowlists(candidates)
        segments_info = _segment_info(payload)
        validation = validate_judgments(
            items=items,
            raw_judgments=payload.get("judgments", []),
            decision_candidate_ids=decision_ids,
            action_candidate_status=action_status,
            segments=segments_info,
        )
        rows = create_generation_candidates(
            session,
            request=request_row,
            project_id=project_id,
            external_meeting_id=meeting_id,
            items=items,
            raw_items=raw_items,
            raw_judgments=raw_judgments,
            validated_judgments=validation.judgments,
            segments=segments_info,
            allowed_existing_node_ids=decision_ids | set(action_status),
        )

        completed_at = datetime.now(timezone.utc)
        update_request_generation_metadata(
            request_row,
            lineage=lineage_dict,
            usage=dict(usage),
            raw_extraction=raw_extraction,
            raw_judgment=raw_judgment,
            completed_at=completed_at,
        )
        request_row.status = "REVIEW_PENDING"
        request_row.payload_hash = phash
        request_row.warnings = list(warnings or [])
        request_row.failure_stage = warning_failure_stage
        request_row.failure_code = warning_failure_code
        request_row.failure_message = (
            "Judgment generation failed after retries"
            if warning_failure_stage == "JUDGMENT"
            else None
        )
        meeting.status = "REVIEW_PENDING"

        counts = Counter(row.suggested_disposition for row in rows)
        result = ProposalPersistResult(
            requestId=request_id,
            externalMeetingId=meeting_id,
            status="REVIEW_PENDING",
            outcome=(
                "REVIEW_PENDING_WITH_JUDGMENT_WARNING"
                if warnings
                else "NEWLY_CREATED_REVIEW_PENDING"
            ),
            candidateIds=[str(row.id) for row in rows],
            candidateCount=len(rows),
            suggestedDispositionCounts=dict(counts),
            filled=validation.filled,
            dropped=validation.dropped,
            demoted=validation.demoted,
            invalidEvidence=validation.invalid_evidence,
            warnings=list(warnings or []),
            detail={
                "sequentialOrder": validation.sequential_order,
                "responseInvalid": validation.response_invalid,
            },
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_generation_failed(
    session_factory: sessionmaker,
    *,
    request_db_id: uuid.UUID,
    stage: str,
    code: str,
    message: str,
    usage: dict,
    raw_extraction: dict | list | str | None = None,
    raw_judgment: dict | list | str | None = None,
    lineage: Lineage | dict | None = None,
) -> ProposalPersistResult:
    """Persist a sanitized failure in a transaction separate from generation."""

    session = session_factory()
    try:
        request_row = session.get(Request, request_db_id)
        if request_row is None:
            raise RuntimeError("claimed request not found while recording failure")
        request_row.status = "FAILED"
        request_row.failure_stage = stage
        request_row.failure_code = code
        request_row.failure_message = message
        request_row.completed_at = datetime.now(timezone.utc)
        request_row.usage = dict(usage)
        request_row.raw_extraction = raw_extraction
        request_row.raw_judgment = raw_judgment
        if lineage is not None:
            request_row.lineage = (
                lineage.model_dump(mode="json", exclude_none=True)
                if isinstance(lineage, Lineage)
                else dict(lineage)
            )
        session.commit()
        return ProposalPersistResult(
            requestId=request_row.external_request_id,
            externalMeetingId=request_row.external_meeting_id,
            status="FAILED",
            outcome=f"FAILED_{stage}",
            detail={"failureStage": stage, "failureCode": code},
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def persist_generation_candidates(
    session_factory: sessionmaker,
    payload: dict,
    *,
    raw_extraction: dict | list | str | None,
    raw_judgment: dict | list | str | None,
    lineage: Lineage | dict,
    usage: dict,
) -> ProposalPersistResult:
    """Compatibility helper for already-generated artifacts.

    Production ``run_meeting`` uses ``claim_generation_request`` before any LLM
    call and then invokes ``finalize_generation_candidates`` directly.
    """

    normalized_payload = dict(payload)
    raw_items = list(payload.get("items") or [])
    normalized_payload["items"] = normalize_extraction_items(raw_items)
    direct_hash_blob = json.dumps(
        {"version": "direct-persist-v1", "payload": normalized_payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    direct_input_hash = hashlib.sha256(direct_hash_blob.encode("utf-8")).hexdigest()
    claim = claim_generation_request(
        session_factory,
        project_id=payload["projectId"],
        external_meeting_id=payload["externalMeetingId"],
        external_request_id=payload.get("requestId", f"req-{payload['externalMeetingId']}"),
        pipeline_version=payload.get("pipelineVersion", PIPELINE_VERSION),
        input_hash=direct_input_hash,
        input_hash_version="direct-persist-v1",
        run_type="DIRECT_CANDIDATE_PERSIST",
        lineage=lineage,
    )
    if not claim.claimed:
        assert claim.result is not None
        return claim.result
    return finalize_generation_candidates(
        session_factory,
        normalized_payload,
        request_db_id=claim.request_db_id,
        raw_items=raw_items,
        raw_extraction=raw_extraction,
        raw_judgment=raw_judgment,
        lineage=lineage,
        usage=usage,
    )


def process_request(
    session_factory: sessionmaker,
    payload: dict,
    *,
    category_set: CategorySet | None = None,
    plan_id: str | None = None,
    lineage: Lineage | None = None,
) -> ApplyResult:
    category_set = category_set or CategorySet.load()
    project_id = payload["projectId"]
    meeting_id = payload["externalMeetingId"]
    request_id = payload.get("requestId", f"req-{meeting_id}")
    pipeline_version = payload.get("pipelineVersion", PIPELINE_VERSION)
    run_type = payload.get("runType", _DEFAULT_RUN_TYPE)
    phash = payload_hash(payload)
    legacy_input_hash = hashlib.sha256(
        f"legacy-output-v1:{phash}".encode("utf-8")
    ).hexdigest()

    session = session_factory()
    try:
        # --- 0. 멱등성 ---------------------------------------------------------
        existing = session.execute(
            select(Request).where(
                Request.project_id == project_id,
                Request.external_meeting_id == meeting_id,
                Request.pipeline_version == pipeline_version,
                Request.run_type == run_type,
            )
        ).scalar_one_or_none()
        if existing is not None:
            status = "DUPLICATE" if existing.payload_hash == phash else "REJECTED"
            detail = {} if status == "DUPLICATE" else {"reason": "payload_hash mismatch for same request key"}
            session.rollback()
            return ApplyResult(requestId=request_id, externalMeetingId=meeting_id, status=status, detail=detail)

        request_row = Request(
            project_id=project_id, external_meeting_id=meeting_id,
            external_request_id=request_id,
            pipeline_version=pipeline_version, run_type=run_type,
            input_hash=legacy_input_hash, input_hash_version="legacy-output-v1",
            payload_hash=phash, status="PROCESSING",
        )
        session.add(request_row)
        try:
            session.flush()
        except IntegrityError:  # 동시 삽입 경쟁 → 중복으로 처리 (UNIQUE 백스톱)
            session.rollback()
            return ApplyResult(requestId=request_id, externalMeetingId=meeting_id, status="DUPLICATE",
                               detail={"reason": "concurrent duplicate request"})

        # --- 1. 저장 -----------------------------------------------------------
        upsert_meeting(session, project_id, meeting_id)
        upsert_segments(session, project_id, meeting_id, payload.get("segments", []))

        # --- 2. 검증 -----------------------------------------------------------
        items = payload.get("items", [])
        raw_judgments = payload.get("judgments", [])
        candidates = payload.get("candidates", {}) or {}
        decision_ids, action_status = _candidate_allowlists(candidates)
        segments_info = _segment_info(payload)
        validation = validate_judgments(
            items=items,
            raw_judgments=raw_judgments,
            decision_candidate_ids=decision_ids,
            action_candidate_status=action_status,
            segments=segments_info,
        )

        # optimistic lock 기준 버전: UPDATE 대상 노드의 현재 DB version 을 plan 빌드 시점에 확보.
        action_versions: dict[str, int] = {}
        for j in validation.judgments:
            if str(j.get("result")) == "UPDATE_ACTION":
                target = str(j.get("targetActionId"))
                node = get_node(session, target)
                if node is not None:
                    action_versions[target] = node.version

        # --- 3. Plan -----------------------------------------------------------
        effective_lineage = lineage or Lineage(
            extractionPromptVersion="fixture-m1",
            judgmentPromptVersion="fixture-m1",
            categorySchemaVersion=category_set.schema_version,
            generatedBy="FIXTURE",
        )
        plan = build_change_plan(
            plan_id=plan_id or f"plan-{meeting_id}",
            project_id=project_id,
            external_meeting_id=meeting_id,
            request_id=request_id,
            items=items,
            validation=validation,
            segments=segments_info,
            lineage=effective_lineage,
            category_set=category_set,
            action_versions=action_versions,
        )

        # --- 4. 반영 (원자) ---------------------------------------------------
        result = apply_change_plan(session, plan, category_set)
        result.demoted = [
            DemotedEntry(itemId=d["itemId"], fromResult=d.get("from"), rule=d["rule"])
            for d in validation.demoted
        ]
        result.detail = {
            **result.detail,
            "filled": validation.filled,
            "dropped": validation.dropped,
            "invalidEvidence": validation.invalid_evidence,
            "sequentialOrder": validation.sequential_order,
            "responseInvalid": validation.response_invalid,
        }
        request_row.status = "COMPLETED"
        session.commit()
        return result

    except StaleVersionError as exc:  # 규칙 9 — 전체 롤백, 재생성 경로
        session.rollback()
        return ApplyResult(
            requestId=request_id, externalMeetingId=meeting_id, status="STALE",
            detail={"reason": str(exc), "nodeId": exc.node_id, "expected": exc.expected, "actual": exc.actual},
        )
    except ApplyError as exc:  # 규칙 8 — 부분 성공 없이 전체 롤백
        session.rollback()
        return ApplyResult(
            requestId=request_id, externalMeetingId=meeting_id, status="REJECTED",
            detail={"reason": str(exc)},
        )
    finally:
        session.close()
