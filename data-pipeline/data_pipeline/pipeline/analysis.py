"""Durable analysis execution through Embedding and Retrieval."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from data_pipeline.config import load_settings
from data_pipeline.contracts import (
    AnalysisRetrievalResult,
    AnalysisRunStatus,
    AnalysisRunView,
    AnalysisStatus,
    BModelStatus,
    GraphState,
    ReanalyzeUnattachedNodeResult,
    RetrievalResultView,
    RetrievalStageStatus,
    analysis_run_status_transition_allowed,
    analysis_status_transition_allowed,
)
from data_pipeline.retrieval import (
    EmbeddingClient,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    build_embedding_text,
    embedding_text_hash,
    search_similar_nodes,
    validate_embedding,
)
from data_pipeline.storage.models import (
    AnalysisCandidate,
    BModelResult,
    Node,
    NodeAnalysisRun,
    NodeEmbedding,
    RetrievalResult,
)

from .errors import (
    AnalysisRunIncompleteError,
    AnalysisRunNotFoundError,
    AnalysisRunStateError,
    NodeNotFoundError,
    NodeStateError,
    NodeValidationError,
    NodeVersionConflict,
    RetrievalExecutionError,
)

ANALYSIS_INPUT_HASH_VERSION = "analysis-input-v2"
_REUSABLE_RUN_STATUSES = frozenset(
    {
        AnalysisRunStatus.PENDING.value,
        AnalysisRunStatus.RUNNING.value,
        AnalysisRunStatus.COMPLETED.value,
    }
)
_READY_EMBEDDING_STATUS = "READY"
_STORAGE_EMBEDDING_DIMENSION = (
    NodeEmbedding.__table__.c.embedding.type.dim
)


def build_analysis_input_hash(
    node: Node,
    *,
    retrieval_config_version: str,
    embedding_model: str,
    embedding_version: str,
) -> str:
    """Hash only Retrieval inputs, in the contract-defined deterministic order."""

    evidence = sorted(
        (row.segment_id, row.quote)
        for row in node.evidence
    )
    canonical = json.dumps(
        [
            ANALYSIS_INPUT_HASH_VERSION,
            node.node_type,
            node.category,
            node.title,
            node.content,
            evidence,
            retrieval_config_version,
            embedding_model,
            embedding_version,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_view(run: NodeAnalysisRun) -> AnalysisRunView:
    return AnalysisRunView(
        analysis_run_id=str(run.id),
        source_node_id=str(run.source_node_id),
        source_node_version=run.source_node_version,
        analysis_input_hash=run.analysis_input_hash,
        analysis_input_hash_version=run.analysis_input_hash_version,
        retrieval_config_version=run.retrieval_config_version,
        embedding_model=run.embedding_model,
        embedding_version=run.embedding_version,
        retrieval_status=RetrievalStageStatus(run.retrieval_status),
        retrieval_result_count=run.retrieval_result_count,
        retrieval_completed_at=run.retrieval_completed_at,
        b_model_status=BModelStatus(run.b_model_status),
        b_model_skip_reason=run.b_model_skip_reason,
        b_model_failure_code=run.b_model_failure_code,
        b_model_failure_message=run.b_model_failure_message,
        b_model_started_at=run.b_model_started_at,
        b_model_completed_at=run.b_model_completed_at,
        attempt=run.attempt,
        status=AnalysisRunStatus(run.status),
        requested_by=run.requested_by,
        failure_code=run.failure_code,
        failure_message=run.failure_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def _set_node_status(node: Node, status: AnalysisStatus) -> None:
    current = node.analysis_status
    if current == status.value:
        return
    if not analysis_status_transition_allowed(current, status.value):
        raise AnalysisRunStateError(
            f"invalid Node analysis transition: {current} -> {status.value}"
        )
    node.analysis_status = status.value
    node.updated_at = datetime.now(timezone.utc)


def _prepare_node_for_pending(node: Node) -> None:
    if node.analysis_status in {
        AnalysisStatus.ANALYZING.value,
        AnalysisStatus.ANALYZED.value,
    }:
        _set_node_status(node, AnalysisStatus.STALE)
    _set_node_status(node, AnalysisStatus.PENDING)


def _set_run_status(
    run: NodeAnalysisRun,
    status: AnalysisRunStatus,
) -> None:
    if run.status == status.value:
        return
    if not analysis_run_status_transition_allowed(run.status, status.value):
        raise AnalysisRunStateError(
            f"invalid analysis run transition: {run.status} -> {status.value}"
        )
    run.status = status.value
    run.updated_at = datetime.now(timezone.utc)


def _supersede_current_run(
    session,
    *,
    node: Node,
    except_run_id: uuid.UUID | None = None,
) -> None:
    current_id = node.current_analysis_run_id
    if current_id is None or current_id == except_run_id:
        return
    current = session.get(
        NodeAnalysisRun,
        current_id,
        with_for_update=True,
    )
    if current is None:
        return
    if current.status in {
        AnalysisRunStatus.PENDING.value,
        AnalysisRunStatus.RUNNING.value,
        AnalysisRunStatus.COMPLETED.value,
    }:
        _set_run_status(current, AnalysisRunStatus.SUPERSEDED)
        current.completed_at = datetime.now(timezone.utc)


def _node_status_for_run(run_status: str) -> AnalysisStatus:
    return {
        AnalysisRunStatus.PENDING.value: AnalysisStatus.PENDING,
        AnalysisRunStatus.RUNNING.value: AnalysisStatus.ANALYZING,
        AnalysisRunStatus.COMPLETED.value: AnalysisStatus.ANALYZED,
        AnalysisRunStatus.FAILED.value: AnalysisStatus.FAILED,
        AnalysisRunStatus.SUPERSEDED.value: AnalysisStatus.STALE,
    }[run_status]


def reanalyze_unattached_node(
    session_factory,
    node_id: str | uuid.UUID,
    *,
    project_id: str,
    actor_id: str,
    expected_version: int,
    retrieval_config_version: str | None = None,
) -> ReanalyzeUnattachedNodeResult:
    """Create or reuse an analysis run; no Retrieval/model work occurs here."""

    try:
        parsed_id = (
            node_id
            if isinstance(node_id, uuid.UUID)
            else uuid.UUID(str(node_id))
        )
    except (TypeError, ValueError) as exc:
        raise NodeValidationError("node_id must be a UUID") from exc
    if not actor_id or not actor_id.strip():
        raise NodeValidationError("actor_id must not be empty")
    retrieval_settings = load_settings().retrieval
    config_version = (
        retrieval_config_version
        or retrieval_settings.config_version
    )
    if not config_version.strip():
        raise NodeValidationError(
            "retrieval_config_version must not be empty"
        )

    session = session_factory()
    try:
        node = (
            session.execute(
                select(Node)
                .options(selectinload(Node.evidence))
                .where(
                    Node.id == parsed_id,
                    Node.project_id == project_id,
                )
                .with_for_update()
            )
            .scalars()
            .unique()
            .one_or_none()
        )
        if node is None:
            raise NodeNotFoundError(f"node not found: {node_id}")
        if (
            node.graph_state != GraphState.UNATTACHED.value
            or node.merged_into_node_id is not None
        ):
            raise NodeStateError(
                "only non-merged UNATTACHED nodes can be analyzed"
            )
        if node.version != expected_version:
            raise NodeVersionConflict(
                str(node.id),
                expected_version,
                node.version,
            )

        input_hash = build_analysis_input_hash(
            node,
            retrieval_config_version=config_version,
            embedding_model=retrieval_settings.embedding_model,
            embedding_version=retrieval_settings.embedding_version,
        )
        active = session.execute(
            select(NodeAnalysisRun)
            .where(
                NodeAnalysisRun.source_node_id == node.id,
                NodeAnalysisRun.analysis_input_hash == input_hash,
                NodeAnalysisRun.status.in_(
                    {
                        AnalysisRunStatus.PENDING.value,
                        AnalysisRunStatus.RUNNING.value,
                    }
                ),
            )
            .order_by(NodeAnalysisRun.attempt.desc())
            .with_for_update()
        ).scalars().first()
        if active is not None and active.source_node_version == node.version:
            _supersede_current_run(
                session,
                node=node,
                except_run_id=active.id,
            )
            node.current_analysis_run_id = active.id
            node.analysis_input_hash = input_hash
            desired_status = _node_status_for_run(active.status)
            if node.analysis_status != desired_status.value:
                if desired_status is AnalysisStatus.PENDING:
                    _prepare_node_for_pending(node)
                else:
                    _set_node_status(node, desired_status)
            session.commit()
            return ReanalyzeUnattachedNodeResult(
                run=_run_view(active),
                node_analysis_status=desired_status,
                created=False,
            )
        if active is not None:
            _set_run_status(active, AnalysisRunStatus.SUPERSEDED)
            active.completed_at = datetime.now(timezone.utc)

        latest = session.execute(
            select(NodeAnalysisRun)
            .where(
                NodeAnalysisRun.source_node_id == node.id,
                NodeAnalysisRun.source_node_version == node.version,
                NodeAnalysisRun.analysis_input_hash == input_hash,
            )
            .order_by(NodeAnalysisRun.attempt.desc())
            .with_for_update()
        ).scalars().first()

        if (
            latest is not None
            and latest.status in _REUSABLE_RUN_STATUSES
            and not _pending_candidate_target_is_stale(session, latest)
        ):
            _supersede_current_run(
                session,
                node=node,
                except_run_id=latest.id,
            )
            node.current_analysis_run_id = latest.id
            node.analysis_input_hash = input_hash
            desired_status = _node_status_for_run(latest.status)
            if node.analysis_status != desired_status.value:
                if desired_status is AnalysisStatus.PENDING:
                    _prepare_node_for_pending(node)
                else:
                    _set_node_status(node, desired_status)
            session.commit()
            return ReanalyzeUnattachedNodeResult(
                run=_run_view(latest),
                node_analysis_status=desired_status,
                created=False,
            )

        _supersede_current_run(session, node=node)
        attempt = 1 if latest is None else latest.attempt + 1
        run = NodeAnalysisRun(
            source_node_id=node.id,
            source_node_version=node.version,
            analysis_input_hash=input_hash,
            analysis_input_hash_version=ANALYSIS_INPUT_HASH_VERSION,
            retrieval_config_version=config_version,
            embedding_model=retrieval_settings.embedding_model,
            embedding_version=retrieval_settings.embedding_version,
            attempt=attempt,
            status=AnalysisRunStatus.PENDING.value,
            requested_by=actor_id.strip(),
        )
        session.add(run)
        session.flush()
        node.current_analysis_run_id = run.id
        node.analysis_input_hash = input_hash
        _prepare_node_for_pending(node)
        session.commit()
        return ReanalyzeUnattachedNodeResult(
            run=_run_view(run),
            node_analysis_status=AnalysisStatus.PENDING,
            created=True,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _pending_candidate_target_is_stale(session, run) -> bool:
    """True when the run's PENDING candidate points at a drifted target.

    Found in the live E2E: approving a MERGE bumps the target's version, which
    makes every sibling candidate aimed at that target un-approvable ("Candidate
    target is no longer valid"). The analysis input hash covers only the source
    node, so a plain reanalyze reused the COMPLETED run — and with it the stale
    candidate — leaving the node permanently stuck. A stale target must instead
    force a fresh attempt so Retrieval and the B model see the current graph.
    """

    candidate = session.execute(
        select(AnalysisCandidate).where(
            AnalysisCandidate.analysis_run_id == run.id,
            AnalysisCandidate.status == "PENDING",
            AnalysisCandidate.target_node_id.is_not(None),
        )
    ).scalar_one_or_none()
    if candidate is None:
        return False
    target = session.get(Node, candidate.target_node_id)
    if (
        target is None
        or target.merged_into_node_id is not None
        or target.graph_state not in ("ACTIVE", "UNATTACHED")
    ):
        return True
    return target.version != candidate.target_node_version


def _locked_run_and_node(
    session,
    run_id: str | uuid.UUID,
    *,
    project_id: str,
):
    try:
        parsed_id = (
            run_id
            if isinstance(run_id, uuid.UUID)
            else uuid.UUID(str(run_id))
        )
    except (TypeError, ValueError) as exc:
        raise NodeValidationError("analysis_run_id must be a UUID") from exc
    run_source = session.execute(
        select(NodeAnalysisRun.source_node_id)
        .join(Node, Node.id == NodeAnalysisRun.source_node_id)
        .where(
            NodeAnalysisRun.id == parsed_id,
            Node.project_id == project_id,
        )
    ).scalar_one_or_none()
    if run_source is None:
        raise AnalysisRunNotFoundError(
            f"analysis run not found: {run_id}"
        )
    node = session.execute(
        select(Node)
        .where(
            Node.id == run_source,
            Node.project_id == project_id,
        )
        .with_for_update()
    ).scalar_one()
    run = session.execute(
        select(NodeAnalysisRun)
        .where(
            NodeAnalysisRun.id == parsed_id,
            NodeAnalysisRun.source_node_id == node.id,
        )
        .with_for_update()
    ).scalar_one()
    return run, node


def _run_is_current(run: NodeAnalysisRun, node: Node) -> bool:
    return (
        node.current_analysis_run_id == run.id
        and node.version == run.source_node_version
        and node.analysis_input_hash == run.analysis_input_hash
        and node.graph_state == GraphState.UNATTACHED.value
        and node.merged_into_node_id is None
    )


def _supersede_obsolete_run(
    run: NodeAnalysisRun,
    node: Node,
) -> bool:
    if _run_is_current(run, node):
        return False
    if run.status in {
        AnalysisRunStatus.PENDING.value,
        AnalysisRunStatus.RUNNING.value,
        AnalysisRunStatus.COMPLETED.value,
    }:
        _set_run_status(run, AnalysisRunStatus.SUPERSEDED)
        run.completed_at = datetime.now(timezone.utc)
    return True


def mark_analysis_run_running(
    session_factory,
    run_id: str | uuid.UUID,
    *,
    project_id: str,
) -> AnalysisRunView:
    """Worker claim boundary; it performs no Retrieval itself."""

    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            run_id,
            project_id=project_id,
        )
        if _supersede_obsolete_run(run, node):
            session.commit()
            return _run_view(run)
        if run.status == AnalysisRunStatus.RUNNING.value:
            session.rollback()
            return _run_view(run)
        _set_run_status(run, AnalysisRunStatus.RUNNING)
        run.started_at = run.started_at or datetime.now(timezone.utc)
        _set_node_status(node, AnalysisStatus.ANALYZING)
        session.commit()
        return _run_view(run)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_analysis_run_completed(
    session_factory,
    run_id: str | uuid.UUID,
    *,
    project_id: str,
) -> AnalysisRunView:
    """Complete only after every contract-required durable output exists."""

    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            run_id,
            project_id=project_id,
        )
        if _supersede_obsolete_run(run, node):
            session.commit()
            return _run_view(run)
        if run.status == AnalysisRunStatus.COMPLETED.value:
            session.rollback()
            return _run_view(run)
        missing_results = _missing_completion_results(
            session,
            run=run,
            node=node,
        )
        if missing_results:
            raise AnalysisRunIncompleteError(missing_results)
        _set_run_status(run, AnalysisRunStatus.COMPLETED)
        run.completed_at = datetime.now(timezone.utc)
        _set_node_status(node, AnalysisStatus.ANALYZED)
        session.commit()
        return _run_view(run)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_analysis_run_failed(
    session_factory,
    run_id: str | uuid.UUID,
    *,
    project_id: str,
    failure_code: str,
    failure_message: str,
) -> AnalysisRunView:
    """Persist a failed attempt; reanalyze creates the next attempt."""

    if not failure_code or not failure_code.strip():
        raise NodeValidationError("failure_code must not be empty")
    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            run_id,
            project_id=project_id,
        )
        if _supersede_obsolete_run(run, node):
            session.commit()
            return _run_view(run)
        if run.status == AnalysisRunStatus.FAILED.value:
            session.rollback()
            return _run_view(run)
        _set_run_status(run, AnalysisRunStatus.FAILED)
        if run.retrieval_status != RetrievalStageStatus.COMPLETED.value:
            run.retrieval_status = RetrievalStageStatus.FAILED.value
        run.failure_code = failure_code.strip()
        run.failure_message = failure_message
        run.completed_at = datetime.now(timezone.utc)
        _set_node_status(node, AnalysisStatus.FAILED)
        session.commit()
        return _run_view(run)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _embedding_for_run(session, *, run: NodeAnalysisRun, node: Node):
    if run.embedding_version is None:
        return None
    return session.get(
        NodeEmbedding,
        {
            "node_id": node.id,
            "embedding_version": run.embedding_version,
        },
    )


def _embedding_matches_run(
    embedding: NodeEmbedding | None,
    *,
    run: NodeAnalysisRun,
    text_hash: str,
    expected_dimension: int,
) -> bool:
    return (
        embedding is not None
        and embedding.status == _READY_EMBEDDING_STATUS
        and embedding.embedding is not None
        and embedding.embedding_model == run.embedding_model
        and embedding.embedding_version == run.embedding_version
        and embedding.dimension == expected_dimension
        and embedding.embedded_text_hash == text_hash
    )


def _missing_completion_results(
    session,
    *,
    run: NodeAnalysisRun,
    node: Node,
) -> list[str]:
    settings = load_settings().retrieval
    text_hash = embedding_text_hash(build_embedding_text(node))
    embedding = _embedding_for_run(session, run=run, node=node)
    missing = []
    if not _embedding_matches_run(
        embedding,
        run=run,
        text_hash=text_hash,
        expected_dimension=settings.embedding_dim,
    ):
        missing.append("EMBEDDING")
    retrieval_count = session.execute(
        select(func.count(RetrievalResult.id)).where(
            RetrievalResult.analysis_run_id == run.id
        )
    ).scalar_one()
    retrieval_complete = not (
        run.retrieval_status != RetrievalStageStatus.COMPLETED.value
        or run.retrieval_result_count is None
        or run.retrieval_completed_at is None
        or run.retrieval_result_count != retrieval_count
    )
    if not retrieval_complete:
        missing.append("RETRIEVAL")
    b_result_count = session.execute(
        select(func.count(BModelResult.id)).where(
            BModelResult.analysis_run_id == run.id,
            BModelResult.project_id == node.project_id,
            BModelResult.validation_status == "VALIDATED",
        )
    ).scalar_one()
    candidate_count = session.execute(
        select(func.count(AnalysisCandidate.id)).where(
            AnalysisCandidate.analysis_run_id == run.id,
            AnalysisCandidate.project_id == node.project_id,
        )
    ).scalar_one()
    if not retrieval_complete:
        missing.append("B_MODEL_OR_FINAL_CANDIDATE")
    elif retrieval_count == 0:
        if (
            run.b_model_status != BModelStatus.SKIPPED.value
            or run.b_model_skip_reason != "NO_RETRIEVAL_CANDIDATES"
            or b_result_count != 0
            or candidate_count != 0
        ):
            missing.append("B_MODEL_SKIPPED_RESULT")
    elif (
        run.b_model_status != BModelStatus.SUCCEEDED.value
        or run.b_model_completed_at is None
        or b_result_count != 1
        or candidate_count != 1
    ):
        missing.append("B_MODEL_OR_FINAL_CANDIDATE")
    return missing


def _validate_embedding_configuration() -> None:
    settings = load_settings().retrieval
    if settings.embedding_dim != _STORAGE_EMBEDDING_DIMENSION:
        raise EmbeddingValidationError(
            "configured embedding dimension does not match storage: "
            f"configured={settings.embedding_dim}, "
            f"storage={_STORAGE_EMBEDDING_DIMENSION}"
        )
    if settings.node_top_k < 1:
        raise RetrievalExecutionError(
            "RETRIEVAL_NODE_TOP_K must be at least 1"
        )
    if (
        settings.min_similarity is not None
        and not -1.0 <= settings.min_similarity <= 1.0
    ):
        raise RetrievalExecutionError(
            "RETRIEVAL_MIN_SIMILARITY must be between -1.0 and 1.0"
        )


def _persisted_retrieval_views(
    session,
    run_id: uuid.UUID,
) -> list[RetrievalResultView]:
    rows = session.execute(
        select(RetrievalResult)
        .where(RetrievalResult.analysis_run_id == run_id)
        .order_by(RetrievalResult.rank)
    ).scalars().all()
    return [
        RetrievalResultView(
            target_node_id=str(row.target_node_id),
            target_node_version=row.target_node_version,
            rank=row.rank,
            similarity=row.similarity,
        )
        for row in rows
    ]


def _retrieval_result(
    session,
    *,
    run: NodeAnalysisRun,
    embedding_created: bool,
) -> AnalysisRetrievalResult:
    return AnalysisRetrievalResult(
        run=_run_view(run),
        node_analysis_status=AnalysisStatus.ANALYZING,
        embedding_created=embedding_created,
        retrieval_results=_persisted_retrieval_views(session, run.id),
    )


def _mark_stage_failed(
    session_factory,
    *,
    run_id: str | uuid.UUID,
    project_id: str,
    failure_code: str,
    exc: Exception,
) -> None:
    try:
        mark_analysis_run_failed(
            session_factory,
            run_id,
            project_id=project_id,
            failure_code=failure_code,
            failure_message=str(exc),
        )
    except (AnalysisRunNotFoundError, AnalysisRunStateError):
        # A concurrent invalidation may have superseded the Run. Preserve that
        # newer state instead of masking the original stage failure.
        return


def _with_parent_hint(
    session,
    *,
    node: Node,
    candidates,
    query_vector: list[float],
    embedding_version: str,
):
    """Force-include the approved same-meeting parent in the candidate set.

    A parent Node created minutes ago by initial review usually has no READY
    embedding yet, so pure vector search can never rank it. Appending it here
    keeps the generation-stage knowledge alive without auto-attaching anything.
    Deduplicated against the vector Top-K; ordering of real matches is kept.
    """

    from data_pipeline.retrieval.search import RetrievedNode, _cosine_similarity

    from .parent_hint import resolve_same_meeting_parent_hint

    hint = resolve_same_meeting_parent_hint(session, node)
    if hint is None:
        return candidates
    if any(row.target_node_id == hint.node_id for row in candidates):
        return candidates

    similarity = 0.0
    embedding_row = session.get(
        NodeEmbedding,
        {"node_id": hint.node_id, "embedding_version": embedding_version},
    )
    if (
        embedding_row is not None
        and embedding_row.status == _READY_EMBEDDING_STATUS
        and embedding_row.embedding is not None
        and len(embedding_row.embedding) == len(query_vector)
    ):
        try:
            similarity = _cosine_similarity(
                [float(v) for v in embedding_row.embedding], query_vector
            )
        except Exception:
            similarity = 0.0

    return [
        *candidates,
        RetrievedNode(
            target_node_id=hint.node_id,
            target_node_version=hint.node_version,
            project_id=node.project_id,
            similarity=similarity,
        ),
    ]


def execute_analysis_retrieval(
    session_factory,
    run_id: str | uuid.UUID,
    *,
    project_id: str,
    embedding_client: EmbeddingClient,
) -> AnalysisRetrievalResult:
    """Generate/reuse an embedding and atomically persist vector Retrieval."""

    _validate_embedding_configuration()
    settings = load_settings().retrieval
    claimed = mark_analysis_run_running(
        session_factory,
        run_id,
        project_id=project_id,
    )
    if claimed.status is not AnalysisRunStatus.RUNNING:
        raise AnalysisRunStateError(
            f"analysis run is not executable: {claimed.status.value}"
        )

    parsed_run_id = uuid.UUID(claimed.analysis_run_id)
    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            parsed_run_id,
            project_id=project_id,
        )
        if run.retrieval_status == RetrievalStageStatus.COMPLETED.value:
            result = _retrieval_result(
                session,
                run=run,
                embedding_created=False,
            )
            session.rollback()
            return result
        text_to_embed = build_embedding_text(node)
        text_hash = embedding_text_hash(text_to_embed)
        stored_embedding = _embedding_for_run(
            session,
            run=run,
            node=node,
        )
        reuse_embedding = _embedding_matches_run(
            stored_embedding,
            run=run,
            text_hash=text_hash,
            expected_dimension=settings.embedding_dim,
        )
        if reuse_embedding:
            try:
                vector = validate_embedding(
                    stored_embedding.embedding,
                    expected_dimension=settings.embedding_dim,
                )
            except EmbeddingValidationError:
                reuse_embedding = False
        session.rollback()
    finally:
        session.close()

    if not reuse_embedding:
        try:
            vector = validate_embedding(
                embedding_client.embed(
                    text=text_to_embed,
                    model=claimed.embedding_model or "",
                    dimensions=settings.embedding_dim,
                ),
                expected_dimension=settings.embedding_dim,
            )
        except EmbeddingValidationError as exc:
            _mark_stage_failed(
                session_factory,
                run_id=parsed_run_id,
                project_id=project_id,
                failure_code="EMBEDDING_INVALID",
                exc=exc,
            )
            raise
        except Exception as exc:
            wrapped = EmbeddingGenerationError(
                f"embedding generation failed: {exc}"
            )
            _mark_stage_failed(
                session_factory,
                run_id=parsed_run_id,
                project_id=project_id,
                failure_code="EMBEDDING_FAILED",
                exc=wrapped,
            )
            raise wrapped from exc

    session = session_factory()
    try:
        run, node = _locked_run_and_node(
            session,
            parsed_run_id,
            project_id=project_id,
        )
        if run.retrieval_status == RetrievalStageStatus.COMPLETED.value:
            result = _retrieval_result(
                session,
                run=run,
                embedding_created=False,
            )
            session.rollback()
            return result
        if (
            run.status != AnalysisRunStatus.RUNNING.value
            or not _run_is_current(run, node)
        ):
            raise AnalysisRunStateError(
                "analysis run changed while embedding was generated"
            )
        current_text = build_embedding_text(node)
        current_text_hash = embedding_text_hash(current_text)
        if current_text_hash != text_hash:
            raise AnalysisRunStateError(
                "analysis input changed while embedding was generated"
            )

        embedding_row = _embedding_for_run(
            session,
            run=run,
            node=node,
        )
        if embedding_row is None:
            embedding_row = NodeEmbedding(
                node_id=node.id,
                embedding_version=run.embedding_version,
            )
            session.add(embedding_row)
        embedding_row.embedding_model = run.embedding_model
        embedding_row.dimension = settings.embedding_dim
        embedding_row.embedded_text_hash = current_text_hash
        embedding_row.embedding = vector
        embedding_row.status = _READY_EMBEDDING_STATUS
        embedding_row.embedded_at = datetime.now(timezone.utc)
        session.flush()

        candidates = search_similar_nodes(
            session,
            project_id=project_id,
            source_node_id=node.id,
            embedding=vector,
            embedding_model=run.embedding_model or "",
            embedding_version=run.embedding_version or "",
            embedding_dimension=settings.embedding_dim,
            top_k=settings.node_top_k,
            min_similarity=settings.min_similarity,
        )
        candidates = _with_parent_hint(
            session,
            node=node,
            candidates=candidates,
            query_vector=vector,
            embedding_version=run.embedding_version or "",
        )
        session.execute(
            delete(RetrievalResult).where(
                RetrievalResult.analysis_run_id == run.id
            )
        )
        for rank, candidate in enumerate(candidates, start=1):
            session.add(
                RetrievalResult(
                    analysis_run_id=run.id,
                    target_node_id=candidate.target_node_id,
                    target_node_version=candidate.target_node_version,
                    rank=rank,
                    similarity=candidate.similarity,
                )
            )
        now = datetime.now(timezone.utc)
        run.retrieval_status = RetrievalStageStatus.COMPLETED.value
        run.retrieval_result_count = len(candidates)
        run.retrieval_completed_at = now
        run.updated_at = now
        session.flush()
        session.commit()
        return _retrieval_result(
            session,
            run=run,
            embedding_created=not reuse_embedding,
        )
    except Exception as exc:
        session.rollback()
        _mark_stage_failed(
            session_factory,
            run_id=parsed_run_id,
            project_id=project_id,
            failure_code="RETRIEVAL_FAILED",
            exc=exc,
        )
        raise
    finally:
        session.close()
