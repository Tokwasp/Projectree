"""B-model execution and durable final-confirmation Candidate creation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import func, select

from data_pipeline.b_model import BModelClient
from data_pipeline.contracts import (
    AnalysisCandidateStatus,
    AnalysisCandidateView,
    AnalysisRunStatus,
    AnalysisStatus,
    BModelDecision,
    BModelExecutionResult,
    BModelStatus,
    GraphState,
    NodeType,
    RecommendationType,
    RetrievalStageStatus,
)
from data_pipeline.storage import (
    AnalysisCandidate,
    BModelResult,
    Node,
    NodeAnalysisRun,
    RetrievalResult,
)

from .analysis import (
    _locked_run_and_node,
    _run_is_current,
    _run_view,
    _set_node_status,
    _set_run_status,
    _supersede_obsolete_run,
)
from .errors import (
    AnalysisRunStateError,
    BModelExecutionError,
    BModelResultValidationError,
    NodeValidationError,
)

_LINKABLE_STATES = frozenset(
    {GraphState.ACTIVE.value, GraphState.UNATTACHED.value}
)


def _candidate_view(candidate: AnalysisCandidate) -> AnalysisCandidateView:
    return AnalysisCandidateView(
        candidate_id=str(candidate.id),
        analysis_run_id=str(candidate.analysis_run_id),
        source_node_id=str(candidate.source_node_id),
        target_node_id=(
            str(candidate.target_node_id)
            if candidate.target_node_id is not None
            else None
        ),
        recommendation=RecommendationType(candidate.recommendation),
        relation_type=candidate.relation_type,
        suggested_title=candidate.suggested_title,
        suggested_content=candidate.suggested_content,
        reason=candidate.reason,
        status=AnalysisCandidateStatus(candidate.status),
        version=candidate.version,
        decided_by=candidate.decided_by,
        decided_at=candidate.decided_at,
    )


def _execution_result(
    session,
    *,
    run: NodeAnalysisRun,
    b_model_called: bool,
) -> BModelExecutionResult:
    candidate = session.execute(
        select(AnalysisCandidate).where(
            AnalysisCandidate.analysis_run_id == run.id,
        )
    ).scalar_one_or_none()
    return BModelExecutionResult(
        run=_run_view(run),
        candidate=_candidate_view(candidate) if candidate else None,
        b_model_called=b_model_called,
    )


def _retrieval_count(session, run_id: uuid.UUID) -> int:
    return session.execute(
        select(func.count(RetrievalResult.id)).where(
            RetrievalResult.analysis_run_id == run_id,
        )
    ).scalar_one()


def _require_retrieval_complete(session, run: NodeAnalysisRun) -> int:
    count = _retrieval_count(session, run.id)
    if (
        run.retrieval_status != RetrievalStageStatus.COMPLETED.value
        or run.retrieval_result_count is None
        or run.retrieval_completed_at is None
        or run.retrieval_result_count != count
    ):
        raise AnalysisRunStateError(
            "B model requires a complete and consistent Retrieval result"
        )
    return count


def _source_payload(node: Node) -> dict:
    return {
        "nodeId": str(node.id),
        "nodeVersion": node.version,
        "nodeType": node.node_type,
        "category": node.category,
        "title": node.title,
        "content": node.content,
        "evidence": [
            {
                "segmentId": row.segment_id,
                "quote": row.quote,
            }
            for row in node.evidence
        ],
    }


def _retrieval_payload(
    session,
    run_id: uuid.UUID,
    *,
    source_node: Node | None = None,
) -> list[dict]:
    from .parent_hint import resolve_same_meeting_parent_hint

    hint_node_id = None
    hint_origin = None
    if source_node is not None:
        hint = resolve_same_meeting_parent_hint(session, source_node)
        if hint is not None:
            hint_node_id = hint.node_id
            hint_origin = hint.origin

    rows = session.execute(
        select(RetrievalResult, Node)
        .join(Node, Node.id == RetrievalResult.target_node_id)
        .where(RetrievalResult.analysis_run_id == run_id)
        .order_by(RetrievalResult.rank)
    ).all()
    payload = []
    for result, node in rows:
        entry = {
            "nodeId": str(node.id),
            "nodeVersion": result.target_node_version,
            "nodeType": node.node_type,
            "category": node.category,
            "title": node.title,
            "content": node.content,
            "graphState": node.graph_state,
            "rank": result.rank,
            "similarity": result.similarity,
        }
        if hint_node_id is not None and node.id == hint_node_id:
            # Generation-stage evidence: this candidate was proposed as the
            # parent in the same meeting. The B model may weigh it, never
            # auto-attach on it.
            entry["sameMeetingSuggestedParent"] = True
            entry["parentHintOrigin"] = hint_origin
        payload.append(entry)
    return payload


def _validate_target(
    session,
    *,
    run: NodeAnalysisRun,
    source: Node,
    decision: BModelDecision,
) -> tuple[Node | None, int | None]:
    if decision.targetNodeId is None:
        return None, None
    if decision.targetNodeId == source.id:
        raise BModelResultValidationError(
            "B-model target must not be the source Node"
        )
    retrieval = session.execute(
        select(RetrievalResult)
        .where(
            RetrievalResult.analysis_run_id == run.id,
            RetrievalResult.target_node_id == decision.targetNodeId,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if retrieval is None:
        raise BModelResultValidationError(
            "B-model target is not in this Run's Retrieval results"
        )
    target = session.execute(
        select(Node)
        .where(
            Node.id == decision.targetNodeId,
            Node.project_id == source.project_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if target is None:
        raise BModelResultValidationError("B-model target does not exist")
    if (
        target.version != retrieval.target_node_version
        or target.graph_state not in _LINKABLE_STATES
        or target.merged_into_node_id is not None
    ):
        raise BModelResultValidationError(
            "B-model target changed after Retrieval"
        )
    if decision.recommendation is RecommendationType.MERGE:
        if target.node_type != source.node_type:
            raise BModelResultValidationError(
                "MERGE target must have the same Node type"
            )
    elif decision.relationType is not None:
        if decision.relationType.value == "ATTACHED_TO":
            allowed_parent_types = {
                NodeType.ACTION.value: {NodeType.DECISION.value},
                NodeType.ISSUE.value: {
                    NodeType.DECISION.value,
                    NodeType.ACTION.value,
                },
            }.get(source.node_type, set())
            if (
                target.graph_state != GraphState.ACTIVE.value
                or target.node_type not in allowed_parent_types
            ):
                raise BModelResultValidationError(
                    "ATTACHED_TO target is not a valid ACTIVE parent"
                )
    return target, retrieval.target_node_version


def _complete_locked(run: NodeAnalysisRun, node: Node) -> None:
    if not _run_is_current(run, node):
        raise AnalysisRunStateError(
            "analysis Run is no longer current"
        )
    _set_run_status(run, AnalysisRunStatus.COMPLETED)
    now = datetime.now(timezone.utc)
    run.completed_at = now
    run.updated_at = now
    _set_node_status(node, AnalysisStatus.ANALYZED)


def _mark_b_failure(
    session_factory,
    *,
    run_id: uuid.UUID,
    project_id: str,
    failure_code: str,
    failure_message: str,
) -> None:
    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            run_id,
            project_id=project_id,
        )
        if _supersede_obsolete_run(run, node):
            session.commit()
            return
        if run.b_model_status == BModelStatus.SUCCEEDED.value:
            session.rollback()
            return
        now = datetime.now(timezone.utc)
        run.b_model_status = BModelStatus.FAILED.value
        run.b_model_failure_code = failure_code
        run.b_model_failure_message = failure_message
        run.b_model_completed_at = now
        _set_run_status(run, AnalysisRunStatus.FAILED)
        run.failure_code = failure_code
        run.failure_message = failure_message
        run.completed_at = now
        _set_node_status(node, AnalysisStatus.FAILED)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def execute_b_model(
    session_factory,
    run_id: str | uuid.UUID,
    *,
    project_id: str,
    client: BModelClient,
    model: str,
    model_version: str,
) -> BModelExecutionResult:
    """Claim, call outside a transaction, validate, and persist B output."""

    if not model.strip() or not model_version.strip():
        raise NodeValidationError(
            "model and model_version must not be empty"
        )
    try:
        parsed_run_id = (
            run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
        )
    except (TypeError, ValueError) as exc:
        raise NodeValidationError("analysis_run_id must be a UUID") from exc

    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            parsed_run_id,
            project_id=project_id,
        )
        if run.status == AnalysisRunStatus.COMPLETED.value:
            result = _execution_result(
                session,
                run=run,
                b_model_called=False,
            )
            session.rollback()
            return result
        if _supersede_obsolete_run(run, node):
            session.commit()
            raise AnalysisRunStateError(
                "analysis Run is no longer current"
            )
        if run.status != AnalysisRunStatus.RUNNING.value:
            raise AnalysisRunStateError(
                "B model requires a RUNNING Analysis Run"
            )
        retrieval_count = _require_retrieval_complete(session, run)
        if retrieval_count == 0:
            now = datetime.now(timezone.utc)
            run.b_model_status = BModelStatus.SKIPPED.value
            run.b_model_skip_reason = "NO_RETRIEVAL_CANDIDATES"
            run.b_model_completed_at = now
            _complete_locked(run, node)
            session.commit()
            return _execution_result(
                session,
                run=run,
                b_model_called=False,
            )
        if run.b_model_status == BModelStatus.SUCCEEDED.value:
            result = _execution_result(
                session,
                run=run,
                b_model_called=False,
            )
            session.rollback()
            return result
        if run.b_model_status == BModelStatus.RUNNING.value:
            result = _execution_result(
                session,
                run=run,
                b_model_called=False,
            )
            session.rollback()
            return result
        if run.b_model_status not in {
            BModelStatus.PENDING.value,
            BModelStatus.FAILED.value,
        }:
            raise AnalysisRunStateError(
                f"B model is not executable: {run.b_model_status}"
            )
        source_payload = _source_payload(node)
        retrieval_payload = _retrieval_payload(session, run.id, source_node=node)
        now = datetime.now(timezone.utc)
        run.b_model_status = BModelStatus.RUNNING.value
        run.b_model_started_at = run.b_model_started_at or now
        run.b_model_failure_code = None
        run.b_model_failure_message = None
        run.updated_at = now
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    try:
        raw_decision = client.recommend(
            source_node=source_payload,
            retrieval_candidates=retrieval_payload,
            model=model,
        )
        decision = BModelDecision.model_validate(raw_decision)
    except ValidationError as exc:
        failure = BModelResultValidationError(
            f"invalid B-model result: {exc}"
        )
        _mark_b_failure(
            session_factory,
            run_id=parsed_run_id,
            project_id=project_id,
            failure_code="B_MODEL_RESULT_INVALID",
            failure_message=str(failure),
        )
        raise failure from exc
    except Exception as exc:
        failure = BModelExecutionError(f"B-model execution failed: {exc}")
        _mark_b_failure(
            session_factory,
            run_id=parsed_run_id,
            project_id=project_id,
            failure_code="B_MODEL_FAILED",
            failure_message=str(failure),
        )
        raise failure from exc

    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            parsed_run_id,
            project_id=project_id,
        )
        if _supersede_obsolete_run(run, node):
            session.commit()
            raise AnalysisRunStateError(
                "analysis input changed while B model was running"
            )
        if (
            run.status != AnalysisRunStatus.RUNNING.value
            or run.b_model_status != BModelStatus.RUNNING.value
        ):
            raise AnalysisRunStateError(
                "B-model stage changed while the response was in flight"
            )
        _require_retrieval_complete(session, run)
        target, target_version = _validate_target(
            session,
            run=run,
            source=node,
            decision=decision,
        )
        persisted = BModelResult(
            project_id=project_id,
            analysis_run_id=run.id,
            source_node_id=node.id,
            source_node_version=node.version,
            recommendation=decision.recommendation.value,
            target_node_id=target.id if target else None,
            target_node_version=target_version,
            relation_type=(
                decision.relationType.value
                if decision.relationType is not None
                else None
            ),
            suggested_title=decision.suggestedTitle.strip(),
            suggested_content=decision.suggestedContent,
            reason=decision.reason.strip(),
            model=model.strip(),
            model_version=model_version.strip(),
            metadata_json=decision.metadata,
            validation_status="VALIDATED",
        )
        session.add(persisted)
        session.flush()
        candidate = AnalysisCandidate(
            project_id=project_id,
            analysis_run_id=run.id,
            b_model_result_id=persisted.id,
            source_node_id=node.id,
            source_node_version=node.version,
            target_node_id=target.id if target else None,
            target_node_version=target_version,
            recommendation=decision.recommendation.value,
            relation_type=(
                decision.relationType.value
                if decision.relationType is not None
                else None
            ),
            suggested_title=decision.suggestedTitle.strip(),
            suggested_content=decision.suggestedContent,
            reason=decision.reason.strip(),
            status=AnalysisCandidateStatus.PENDING.value,
        )
        session.add(candidate)
        now = datetime.now(timezone.utc)
        run.b_model_status = BModelStatus.SUCCEEDED.value
        run.b_model_completed_at = now
        run.updated_at = now
        session.flush()
        _complete_locked(run, node)
        session.commit()
        return BModelExecutionResult(
            run=_run_view(run),
            candidate=_candidate_view(candidate),
            b_model_called=True,
        )
    except Exception as exc:
        session.rollback()
        if isinstance(exc, BModelResultValidationError):
            _mark_b_failure(
                session_factory,
                run_id=parsed_run_id,
                project_id=project_id,
                failure_code="B_MODEL_RESULT_INVALID",
                failure_message=str(exc),
            )
            raise
        if isinstance(exc, AnalysisRunStateError):
            raise
        failure = BModelExecutionError(
            f"B-model result persistence failed: {exc}"
        )
        _mark_b_failure(
            session_factory,
            run_id=parsed_run_id,
            project_id=project_id,
            failure_code="B_MODEL_PERSISTENCE_FAILED",
            failure_message=str(failure),
        )
        raise failure from exc
    finally:
        session.close()


__all__ = ["execute_b_model"]
