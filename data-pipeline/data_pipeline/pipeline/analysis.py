"""Durable analysis execution lifecycle without Retrieval or model calls."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from data_pipeline.config import load_settings
from data_pipeline.contracts import (
    AnalysisRunStatus,
    AnalysisRunView,
    AnalysisStatus,
    GraphState,
    ReanalyzeUnattachedNodeResult,
    analysis_run_status_transition_allowed,
    analysis_status_transition_allowed,
)
from data_pipeline.storage.models import Node, NodeAnalysisRun

from .errors import (
    AnalysisRunNotFoundError,
    AnalysisRunStateError,
    NodeNotFoundError,
    NodeStateError,
    NodeValidationError,
    NodeVersionConflict,
)

ANALYSIS_INPUT_HASH_VERSION = "analysis-input-v2"
_REUSABLE_RUN_STATUSES = frozenset(
    {
        AnalysisRunStatus.PENDING.value,
        AnalysisRunStatus.RUNNING.value,
        AnalysisRunStatus.COMPLETED.value,
    }
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

        if latest is not None and latest.status in _REUSABLE_RUN_STATUSES:
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
    """Persist a successful worker terminal state without model calls."""

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
