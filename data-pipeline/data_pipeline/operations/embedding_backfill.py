"""Safe, project-scoped Node embedding backfill operation."""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from data_pipeline.config import RetrievalSettings, load_settings
from data_pipeline.storage import Node, NodeEmbedding

from data_pipeline.retrieval.embedding import (
    CurrentRevisionEmbeddingError,
    EmbeddingClient,
    load_current_revision_embedding_input,
    validate_embedding,
)
from data_pipeline.retrieval.errors import EmbeddingValidationError

_ALLOWED_STATES = frozenset({"ACTIVE", "UNATTACHED"})
_READY = "READY"
_INVALID_READY_REASONS = frozenset(
    {
        "VECTOR_MISSING",
        "MODEL_MISMATCH",
        "DIMENSION_MISMATCH",
        "TEXT_HASH_MISMATCH",
        "VECTOR_INVALID",
    }
)


class BackfillReason(StrEnum):
    READY_REUSABLE = "READY_REUSABLE"
    MISSING = "MISSING"
    STATUS_STALE = "STATUS_STALE"
    STATUS_FAILED = "STATUS_FAILED"
    STATUS_PENDING = "STATUS_PENDING"
    VECTOR_MISSING = "VECTOR_MISSING"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    TEXT_HASH_MISMATCH = "TEXT_HASH_MISMATCH"
    VECTOR_INVALID = "VECTOR_INVALID"
    NO_CURRENT_REVISION = "NO_CURRENT_REVISION"
    INVALID_CURRENT_REVISION = "INVALID_CURRENT_REVISION"
    NODE_CHANGED_DURING_EMBED = "NODE_CHANGED_DURING_EMBED"
    CONCURRENT_READY_REUSED = "CONCURRENT_READY_REUSED"
    DEFERRED_MAX_CALLS = "DEFERRED_MAX_CALLS"
    EMBEDDING_PROVIDER_FAILED = "EMBEDDING_PROVIDER_FAILED"
    EMBEDDING_INVALID = "EMBEDDING_INVALID"
    DB_WRITE_FAILED = "DB_WRITE_FAILED"


@dataclass(frozen=True)
class BackfillOptions:
    project_id: str
    states: tuple[str, ...] = ("ACTIVE", "UNATTACHED")
    node_id: uuid.UUID | None = None
    limit: int | None = None
    batch_size: int = 100
    after_node_id: uuid.UUID | None = None
    max_calls: int | None = None
    sleep_seconds: float = 0.0
    apply: bool = False

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id must not be empty")
        normalized_states = tuple(
            dict.fromkeys(state.strip().upper() for state in self.states)
        )
        if not normalized_states or not set(normalized_states) <= _ALLOWED_STATES:
            raise ValueError("states must contain only ACTIVE and UNATTACHED")
        object.__setattr__(self, "states", normalized_states)
        if self.limit is not None and self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.max_calls is not None and self.max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if self.sleep_seconds < 0:
            raise ValueError("sleep_seconds must not be negative")


@dataclass(frozen=True)
class BackfillNodeResult:
    node_id: uuid.UUID
    status: str
    reason: BackfillReason
    previous_status: str | None
    hash_prefix: str | None
    latency_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodeId": str(self.node_id),
            "status": self.status,
            "reason": self.reason.value,
            "previousStatus": self.previous_status,
            "hashPrefix": self.hash_prefix,
            "latencyMs": self.latency_ms,
        }


@dataclass
class BackfillReport:
    run_id: str
    started_at: datetime
    completed_at: datetime
    mode: str
    options: BackfillOptions
    settings: RetrievalSettings
    last_scanned_node_id: uuid.UUID | None
    results: list[BackfillNodeResult]
    provider_attempted: int
    provider_succeeded: int
    provider_failed: int
    provider_latencies_ms: list[int] = field(default_factory=list)
    provider_usage: list[dict[str, Any]] = field(default_factory=list)
    marked_stale: int = 0

    @property
    def failed(self) -> bool:
        return any(result.status == "FAILED" for result in self.results)

    def counts(self) -> dict[str, int]:
        statuses = Counter(result.status for result in self.results)
        return {
            "scanned": len(self.results),
            "eligible": sum(
                result.reason
                not in {
                    BackfillReason.NO_CURRENT_REVISION,
                    BackfillReason.INVALID_CURRENT_REVISION,
                }
                for result in self.results
            ),
            "reusable": statuses["REUSABLE"],
            "wouldGenerate": statuses["WOULD_GENERATE"],
            "generated": statuses["GENERATED"],
            "markedStale": self.marked_stale,
            "changedDuringEmbed": statuses["CHANGED_DURING_EMBED"],
            "concurrentReadyReused": statuses["CONCURRENT_READY_REUSED"],
            "skipped": statuses["SKIPPED"],
            "deferred": statuses["DEFERRED"],
            "failed": statuses["FAILED"],
        }

    def as_dict(self) -> dict[str, Any]:
        elapsed_ms = max(
            0,
            int((self.completed_at - self.started_at).total_seconds() * 1000),
        )
        average_provider_ms = (
            int(sum(self.provider_latencies_ms) / len(self.provider_latencies_ms))
            if self.provider_latencies_ms
            else 0
        )
        counts = self.counts()
        estimated_calls = counts["wouldGenerate"]
        return {
            "runId": self.run_id,
            "startedAt": self.started_at.isoformat(),
            "completedAt": self.completed_at.isoformat(),
            "mode": self.mode,
            "projectId": self.options.project_id,
            "states": list(self.options.states),
            "embeddingModel": self.settings.embedding_model,
            "embeddingVersion": self.settings.embedding_version,
            "embeddingDimension": self.settings.embedding_dim,
            "batchSize": self.options.batch_size,
            "limit": self.options.limit,
            "maxCalls": self.options.max_calls,
            "afterNodeId": (
                str(self.options.after_node_id)
                if self.options.after_node_id is not None
                else None
            ),
            "lastScannedNodeId": (
                str(self.last_scanned_node_id)
                if self.last_scanned_node_id is not None
                else None
            ),
            "counts": counts,
            "providerCalls": {
                "attempted": self.provider_attempted,
                "succeeded": self.provider_succeeded,
                "failed": self.provider_failed,
                "estimated": estimated_calls,
                "estimatedExceedsMax": (
                    self.options.max_calls is not None
                    and estimated_calls > self.options.max_calls
                ),
            },
            "providerUsage": self.provider_usage,
            "latency": {
                "totalMs": elapsed_ms,
                "averageProviderMs": average_provider_ms,
            },
            "results": [result.as_dict() for result in self.results],
        }


@dataclass(frozen=True)
class _Snapshot:
    node_id: uuid.UUID
    project_id: str
    node_version: int
    current_revision_id: uuid.UUID
    text: str
    text_hash: str
    previous_status: str | None
    reason: BackfillReason


def _classify_embedding(
    embedding: NodeEmbedding | None,
    *,
    text_hash: str,
    settings: RetrievalSettings,
) -> BackfillReason:
    if embedding is None:
        return BackfillReason.MISSING
    if embedding.status == "STALE":
        return BackfillReason.STATUS_STALE
    if embedding.status == "FAILED":
        return BackfillReason.STATUS_FAILED
    if embedding.status == "PENDING":
        return BackfillReason.STATUS_PENDING
    if embedding.embedding_model != settings.embedding_model:
        return BackfillReason.MODEL_MISMATCH
    if embedding.dimension != settings.embedding_dim:
        return BackfillReason.DIMENSION_MISMATCH
    if embedding.embedded_text_hash != text_hash:
        return BackfillReason.TEXT_HASH_MISMATCH
    if embedding.embedding is None:
        return BackfillReason.VECTOR_MISSING
    try:
        validate_embedding(
            embedding.embedding,
            expected_dimension=settings.embedding_dim,
        )
    except EmbeddingValidationError:
        return BackfillReason.VECTOR_INVALID
    return BackfillReason.READY_REUSABLE


def _load_snapshot(
    session,
    *,
    node_id: uuid.UUID,
    project_id: str,
    settings: RetrievalSettings,
    for_update: bool = False,
) -> _Snapshot | BackfillReason:
    statement = select(Node).where(
        Node.id == node_id,
        Node.project_id == project_id,
        Node.graph_state.in_(_ALLOWED_STATES),
        Node.deleted_at.is_(None),
        Node.merged_into_node_id.is_(None),
    )
    if for_update:
        statement = statement.with_for_update()
    node = session.execute(statement).scalar_one_or_none()
    if node is None:
        return BackfillReason.NODE_CHANGED_DURING_EMBED
    try:
        current = load_current_revision_embedding_input(session, node=node)
    except CurrentRevisionEmbeddingError as exc:
        return BackfillReason(exc.reason)
    embedding = session.get(
        NodeEmbedding,
        {
            "node_id": node.id,
            "embedding_version": settings.embedding_version,
        },
        with_for_update=for_update,
    )
    return _Snapshot(
        node_id=node.id,
        project_id=node.project_id,
        node_version=node.version,
        current_revision_id=current.revision_id,
        text=current.text,
        text_hash=current.text_hash,
        previous_status=embedding.status if embedding is not None else None,
        reason=_classify_embedding(
            embedding,
            text_hash=current.text_hash,
            settings=settings,
        ),
    )


def _snapshot_matches(left: _Snapshot, right: _Snapshot) -> bool:
    return (
        left.node_id == right.node_id
        and left.project_id == right.project_id
        and left.node_version == right.node_version
        and left.current_revision_id == right.current_revision_id
        and left.text_hash == right.text_hash
    )


def _mark_invalid_ready_stale(
    session_factory,
    *,
    snapshot: _Snapshot,
    settings: RetrievalSettings,
) -> tuple[str, _Snapshot | None]:
    session = session_factory()
    try:
        current = _load_snapshot(
            session,
            node_id=snapshot.node_id,
            project_id=snapshot.project_id,
            settings=settings,
            for_update=True,
        )
        if not isinstance(current, _Snapshot) or not _snapshot_matches(
            snapshot,
            current,
        ):
            session.rollback()
            return "CHANGED", None
        if current.reason is BackfillReason.READY_REUSABLE:
            session.rollback()
            return "REUSED", current
        embedding = session.get(
            NodeEmbedding,
            {
                "node_id": snapshot.node_id,
                "embedding_version": settings.embedding_version,
            },
        )
        if (
            embedding is not None
            and embedding.status == _READY
            and current.reason.value in _INVALID_READY_REASONS
        ):
            embedding.status = "STALE"
            session.commit()
            return "MARKED", current
        session.rollback()
        return "UNCHANGED", current
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _store_embedding(
    session_factory,
    *,
    snapshot: _Snapshot,
    vector: Sequence[float],
    settings: RetrievalSettings,
) -> str:
    session = session_factory()
    try:
        current = _load_snapshot(
            session,
            node_id=snapshot.node_id,
            project_id=snapshot.project_id,
            settings=settings,
            for_update=True,
        )
        if not isinstance(current, _Snapshot) or not _snapshot_matches(
            snapshot,
            current,
        ):
            session.rollback()
            return "CHANGED"
        if current.reason is BackfillReason.READY_REUSABLE:
            session.rollback()
            return "REUSED"

        row = session.get(
            NodeEmbedding,
            {
                "node_id": snapshot.node_id,
                "embedding_version": settings.embedding_version,
            },
        )
        if row is None:
            row = NodeEmbedding(
                node_id=snapshot.node_id,
                embedding_version=settings.embedding_version,
            )
            session.add(row)
        row.embedding_model = settings.embedding_model
        row.embedding_version = settings.embedding_version
        row.dimension = settings.embedding_dim
        row.embedded_text_hash = snapshot.text_hash
        row.embedding = list(vector)
        row.status = _READY
        row.embedded_at = datetime.now(timezone.utc)
        session.flush()
        session.commit()
        return "STORED"
    except IntegrityError:
        session.rollback()
        verification = _load_snapshot(
            session,
            node_id=snapshot.node_id,
            project_id=snapshot.project_id,
            settings=settings,
        )
        if (
            isinstance(verification, _Snapshot)
            and verification.reason is BackfillReason.READY_REUSABLE
        ):
            return "REUSED"
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _result(
    snapshot: _Snapshot,
    *,
    status: str,
    reason: BackfillReason,
    started: float,
) -> BackfillNodeResult:
    return BackfillNodeResult(
        node_id=snapshot.node_id,
        status=status,
        reason=reason,
        previous_status=snapshot.previous_status,
        hash_prefix=snapshot.text_hash[:12],
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
    )


def run_embedding_backfill(
    session_factory,
    *,
    options: BackfillOptions,
    embedding_client_factory: Callable[[], EmbeddingClient] | None = None,
    settings: RetrievalSettings | None = None,
    sleep: Callable[[float], None] = time.sleep,
    run_id: str | None = None,
) -> BackfillReport:
    """Scan deterministically and process each Node in a short transaction."""

    active_settings = settings or load_settings().retrieval
    storage_dimension = NodeEmbedding.__table__.c.embedding.type.dim
    if active_settings.embedding_dim != storage_dimension:
        raise ValueError(
            "configured embedding dimension does not match node_embedding storage"
        )

    started_at = datetime.now(timezone.utc)
    results: list[BackfillNodeResult] = []
    cursor = options.after_node_id
    last_scanned: uuid.UUID | None = None
    provider: EmbeddingClient | None = None
    provider_attempted = 0
    provider_succeeded = 0
    provider_failed = 0
    provider_latencies: list[int] = []
    provider_usage: list[dict[str, Any]] = []
    marked_stale = 0

    while options.limit is None or len(results) < options.limit:
        fetch_size = options.batch_size
        if options.limit is not None:
            fetch_size = min(fetch_size, options.limit - len(results))
        session = session_factory()
        try:
            statement = (
                select(Node.id)
                .where(
                    Node.project_id == options.project_id,
                    Node.graph_state.in_(options.states),
                    Node.deleted_at.is_(None),
                    Node.merged_into_node_id.is_(None),
                )
                .order_by(Node.id.asc())
                .limit(fetch_size)
            )
            if options.node_id is not None:
                statement = statement.where(Node.id == options.node_id)
            if cursor is not None:
                statement = statement.where(Node.id > cursor)
            node_ids = list(session.execute(statement).scalars())
            session.rollback()
        finally:
            session.close()
        if not node_ids:
            break

        for node_id in node_ids:
            node_started = time.monotonic()
            cursor = node_id
            last_scanned = node_id
            session = session_factory()
            try:
                try:
                    loaded = _load_snapshot(
                        session,
                        node_id=node_id,
                        project_id=options.project_id,
                        settings=active_settings,
                    )
                    session.rollback()
                except Exception:
                    session.rollback()
                    results.append(
                        BackfillNodeResult(
                            node_id=node_id,
                            status="FAILED",
                            reason=BackfillReason.DB_WRITE_FAILED,
                            previous_status=None,
                            hash_prefix=None,
                            latency_ms=max(
                                0,
                                int(
                                    (time.monotonic() - node_started)
                                    * 1000
                                ),
                            ),
                        )
                    )
                    continue
            finally:
                session.close()

            if not isinstance(loaded, _Snapshot):
                results.append(
                    BackfillNodeResult(
                        node_id=node_id,
                        status="SKIPPED",
                        reason=loaded,
                        previous_status=None,
                        hash_prefix=None,
                        latency_ms=max(
                            0,
                            int((time.monotonic() - node_started) * 1000),
                        ),
                    )
                )
                continue
            snapshot = loaded
            if snapshot.reason is BackfillReason.READY_REUSABLE:
                results.append(
                    _result(
                        snapshot,
                        status="REUSABLE",
                        reason=BackfillReason.READY_REUSABLE,
                        started=node_started,
                    )
                )
                continue
            if not options.apply:
                results.append(
                    _result(
                        snapshot,
                        status="WOULD_GENERATE",
                        reason=snapshot.reason,
                        started=node_started,
                    )
                )
                continue

            if (
                snapshot.previous_status == _READY
                and snapshot.reason.value in _INVALID_READY_REASONS
            ):
                try:
                    stale_outcome, _ = _mark_invalid_ready_stale(
                        session_factory,
                        snapshot=snapshot,
                        settings=active_settings,
                    )
                except Exception:
                    results.append(
                        _result(
                            snapshot,
                            status="FAILED",
                            reason=BackfillReason.DB_WRITE_FAILED,
                            started=node_started,
                        )
                    )
                    continue
                if stale_outcome == "CHANGED":
                    results.append(
                        _result(
                            snapshot,
                            status="CHANGED_DURING_EMBED",
                            reason=BackfillReason.NODE_CHANGED_DURING_EMBED,
                            started=node_started,
                        )
                    )
                    continue
                if stale_outcome == "REUSED":
                    results.append(
                        _result(
                            snapshot,
                            status="CONCURRENT_READY_REUSED",
                            reason=BackfillReason.CONCURRENT_READY_REUSED,
                            started=node_started,
                        )
                    )
                    continue
                if stale_outcome == "MARKED":
                    marked_stale += 1

            if (
                options.max_calls is not None
                and provider_attempted >= options.max_calls
            ):
                results.append(
                    _result(
                        snapshot,
                        status="DEFERRED",
                        reason=BackfillReason.DEFERRED_MAX_CALLS,
                        started=node_started,
                    )
                )
                continue
            if provider_attempted > 0 and options.sleep_seconds:
                sleep(options.sleep_seconds)
            if provider is None:
                if embedding_client_factory is None:
                    raise ValueError(
                        "embedding_client_factory is required in apply mode"
                    )
                try:
                    provider = embedding_client_factory()
                except Exception:
                    provider_failed += 1
                    results.append(
                        _result(
                            snapshot,
                            status="FAILED",
                            reason=BackfillReason.EMBEDDING_PROVIDER_FAILED,
                            started=node_started,
                        )
                    )
                    continue

            provider_attempted += 1
            provider_started = time.monotonic()
            try:
                detailed_method = getattr(provider, "embed_detailed", None)
                if callable(detailed_method):
                    detailed = detailed_method(
                        text=snapshot.text,
                        model=active_settings.embedding_model,
                        dimensions=active_settings.embedding_dim,
                    )
                    raw_vector = detailed.vector
                    provider_usage.append(
                        {
                            "inputTokens": detailed.usage.input_tokens,
                            "outputTokens": detailed.usage.output_tokens,
                            "totalTokens": detailed.usage.total_tokens,
                            "credit": detailed.usage.credit,
                            "usageSource": detailed.usage.source,
                            "latencyMs": detailed.latency_ms,
                            "retryCount": detailed.retry_count,
                            "rateLimit": detailed.rate_limit,
                        }
                    )
                else:
                    raw_vector = provider.embed(
                        text=snapshot.text,
                        model=active_settings.embedding_model,
                        dimensions=active_settings.embedding_dim,
                    )
                vector = validate_embedding(
                    raw_vector,
                    expected_dimension=active_settings.embedding_dim,
                )
            except EmbeddingValidationError:
                provider_failed += 1
                provider_latencies.append(
                    max(0, int((time.monotonic() - provider_started) * 1000))
                )
                results.append(
                    _result(
                        snapshot,
                        status="FAILED",
                        reason=BackfillReason.EMBEDDING_INVALID,
                        started=node_started,
                    )
                )
                continue
            except Exception:
                provider_failed += 1
                provider_latencies.append(
                    max(0, int((time.monotonic() - provider_started) * 1000))
                )
                results.append(
                    _result(
                        snapshot,
                        status="FAILED",
                        reason=BackfillReason.EMBEDDING_PROVIDER_FAILED,
                        started=node_started,
                    )
                )
                continue
            provider_succeeded += 1
            provider_latencies.append(
                max(0, int((time.monotonic() - provider_started) * 1000))
            )

            try:
                store_outcome = _store_embedding(
                    session_factory,
                    snapshot=snapshot,
                    vector=vector,
                    settings=active_settings,
                )
            except Exception:
                results.append(
                    _result(
                        snapshot,
                        status="FAILED",
                        reason=BackfillReason.DB_WRITE_FAILED,
                        started=node_started,
                    )
                )
                continue
            if store_outcome == "CHANGED":
                results.append(
                    _result(
                        snapshot,
                        status="CHANGED_DURING_EMBED",
                        reason=BackfillReason.NODE_CHANGED_DURING_EMBED,
                        started=node_started,
                    )
                )
            elif store_outcome == "REUSED":
                results.append(
                    _result(
                        snapshot,
                        status="CONCURRENT_READY_REUSED",
                        reason=BackfillReason.CONCURRENT_READY_REUSED,
                        started=node_started,
                    )
                )
            else:
                results.append(
                    _result(
                        snapshot,
                        status="GENERATED",
                        reason=snapshot.reason,
                        started=node_started,
                    )
                )

        if len(node_ids) < fetch_size or options.node_id is not None:
            break

    completed_at = datetime.now(timezone.utc)
    return BackfillReport(
        run_id=run_id or started_at.strftime("%Y%m%d-%H%M%S"),
        started_at=started_at,
        completed_at=completed_at,
        mode="APPLY" if options.apply else "DRY_RUN",
        options=options,
        settings=active_settings,
        last_scanned_node_id=last_scanned,
        results=results,
        provider_attempted=provider_attempted,
        provider_succeeded=provider_succeeded,
        provider_failed=provider_failed,
        provider_latencies_ms=provider_latencies,
        provider_usage=provider_usage,
        marked_stale=marked_stale,
    )


def write_backfill_report(
    report: BackfillReport,
    *,
    report_directory: Path,
) -> tuple[Path, Path]:
    """Write secret-safe machine and operator reports."""

    report_directory.mkdir(parents=True, exist_ok=True)
    json_path = report_directory / "report.json"
    summary_path = report_directory / "summary.md"
    payload = report.as_dict()
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = report.counts()
    summary_path.write_text(
        "\n".join(
            [
                "# Node Embedding Backfill",
                "",
                f"- Run: `{report.run_id}`",
                f"- Mode: `{report.mode}`",
                f"- Project: `{report.options.project_id}`",
                f"- Last scanned Node: `{report.last_scanned_node_id or ''}`",
                f"- Scanned: {counts['scanned']}",
                f"- Reusable: {counts['reusable']}",
                f"- Would generate: {counts['wouldGenerate']}",
                f"- Generated: {counts['generated']}",
                f"- Marked stale: {counts['markedStale']}",
                f"- Deferred: {counts['deferred']}",
                f"- Failed: {counts['failed']}",
                f"- Provider calls: {report.provider_attempted}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return json_path, summary_path


__all__ = [
    "BackfillNodeResult",
    "BackfillOptions",
    "BackfillReason",
    "BackfillReport",
    "run_embedding_backfill",
    "write_backfill_report",
]
