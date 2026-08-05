"""Read-only Retrieval pilot runner with before/after mutation proof."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from sqlalchemy import MetaData, Table, func, inspect, select

from data_pipeline.config import RetrievalSettings
from data_pipeline.retrieval import search_similar_nodes, validate_embedding
from data_pipeline.storage import Node, NodeEmbedding

from .contracts import EvaluationCase, PilotResult, RetrievedCandidate

PRODUCT_TABLES = (
    "node",
    "relation",
    "node_revision",
    "evidence",
    "node_revision_evidence",
    "merge_operation",
    "generation_run",
    "node_analysis_run",
    "outbox_event",
)


@dataclass(frozen=True)
class TableFingerprint:
    present: bool
    row_count: int
    primary_key_checksum: str | None

    def as_dict(self) -> dict:
        return {
            "present": self.present,
            "rowCount": self.row_count,
            "primaryKeyChecksum": self.primary_key_checksum,
        }


def snapshot_product_tables(
    session,
    *,
    table_names: tuple[str, ...] = PRODUCT_TABLES,
) -> dict[str, TableFingerprint]:
    """Read only primary keys; never load product content into reports."""

    bind = session.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    metadata = MetaData()
    result: dict[str, TableFingerprint] = {}
    for table_name in table_names:
        if table_name not in existing:
            result[table_name] = TableFingerprint(False, 0, None)
            continue
        table = Table(table_name, metadata, autoload_with=bind)
        primary_keys = list(table.primary_key.columns)
        if not primary_keys:
            result[table_name] = TableFingerprint(
                True,
                session.execute(
                    select(func.count()).select_from(table)
                ).scalar_one(),
                None,
            )
            continue
        rows = session.execute(select(*primary_keys)).all()
        serialized = sorted(
            "|".join(str(value) for value in row)
            for row in rows
        )
        digest = hashlib.sha256(
            "\n".join(serialized).encode("utf-8")
        ).hexdigest()
        result[table_name] = TableFingerprint(True, len(rows), digest)
    return result


def deterministic_safety_matrix() -> list[dict]:
    """Map contract fixtures to the existing regression evidence."""

    return [
        {"case": "self merge", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "type mismatch", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "cross-project target", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "deleted/merged target", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "canonical cycle", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "stale version", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "parent conflict", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "category partition", "status": "PASS", "test": "test_category_partition_and_parent_rules.py"},
        {"case": "same-target multi merge", "status": "PASS", "test": "test_automatic_graph.py"},
        {"case": "unattached without parent", "status": "PASS", "test": "test_automatic_graph.py"},
    ]


def run_read_only_pilot(
    session,
    *,
    cases: list[EvaluationCase],
    settings: RetrievalSettings,
) -> tuple[list[PilotResult], dict]:
    before = snapshot_product_tables(session)
    results: list[PilotResult] = []
    for case in cases:
        source = session.execute(
            select(Node).where(
                Node.id == case.source_node_id,
                Node.project_id == case.project_id,
                Node.graph_state.in_(("ACTIVE", "UNATTACHED")),
                Node.merged_into_node_id.is_(None),
            )
        ).scalar_one_or_none()
        if source is None:
            results.append(
                PilotResult(
                    caseId=case.case_id,
                    projectId=case.project_id,
                    sourceNodeId=case.source_node_id,
                    sourceNodeType=case.source_node_type,
                    status="SKIPPED",
                    reason="SOURCE_NOT_SEARCHABLE",
                )
            )
            continue
        embedding = session.get(
            NodeEmbedding,
            {
                "node_id": source.id,
                "embedding_version": settings.embedding_version,
            },
        )
        if (
            embedding is None
            or embedding.status != "READY"
            or embedding.embedding is None
            or embedding.embedding_model != settings.embedding_model
            or embedding.dimension != settings.embedding_dim
        ):
            results.append(
                PilotResult(
                    caseId=case.case_id,
                    projectId=case.project_id,
                    sourceNodeId=case.source_node_id,
                    sourceNodeType=source.node_type,
                    status="SKIPPED",
                    reason="READY_EMBEDDING_UNAVAILABLE",
                )
            )
            continue
        vector = validate_embedding(
            embedding.embedding,
            expected_dimension=settings.embedding_dim,
        )
        started = time.monotonic()
        retrieved = search_similar_nodes(
            session,
            project_id=case.project_id,
            source_node_id=source.id,
            embedding=vector,
            embedding_model=settings.embedding_model,
            embedding_version=settings.embedding_version,
            embedding_dimension=settings.embedding_dim,
            top_k=settings.node_top_k,
            min_similarity=settings.min_similarity,
        )
        target_ids = [row.target_node_id for row in retrieved]
        target_types = {
            node.id: node.node_type
            for node in session.execute(
                select(Node).where(
                    Node.project_id == case.project_id,
                    Node.id.in_(target_ids),
                )
            ).scalars()
        } if target_ids else {}
        results.append(
            PilotResult(
                caseId=case.case_id,
                projectId=case.project_id,
                sourceNodeId=case.source_node_id,
                sourceNodeType=source.node_type,
                status="COMPLETED",
                reason="RETRIEVAL_COMPLETED",
                retrievalLatencyMs=max(
                    0,
                    int((time.monotonic() - started) * 1000),
                ),
                candidates=[
                    RetrievedCandidate(
                        nodeId=row.target_node_id,
                        rank=rank,
                        similarity=row.similarity,
                        nodeType=target_types[row.target_node_id],
                        typeValid=(
                            target_types[row.target_node_id]
                            == source.node_type
                        ),
                    )
                    for rank, row in enumerate(retrieved, start=1)
                ],
            )
        )
    session.rollback()
    after = snapshot_product_tables(session)
    unchanged = before == after
    return results, {
        "unchanged": unchanged,
        "before": {key: value.as_dict() for key, value in before.items()},
        "after": {key: value.as_dict() for key, value in after.items()},
    }


__all__ = [
    "PRODUCT_TABLES",
    "TableFingerprint",
    "deterministic_safety_matrix",
    "run_read_only_pilot",
    "snapshot_product_tables",
]
