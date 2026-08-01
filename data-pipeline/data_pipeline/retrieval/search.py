"""Project-scoped cosine-similarity Retrieval."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text

from .errors import (
    CrossProjectRetrievalError,
    RetrievalExecutionError,
)
from data_pipeline.storage import Node, NodeEmbedding

_SEARCHABLE_GRAPH_STATES = ("ACTIVE", "UNATTACHED")
_READY_EMBEDDING_STATUS = "READY"


@dataclass(frozen=True)
class RetrievedNode:
    target_node_id: uuid.UUID
    target_node_version: int
    project_id: str
    similarity: float


def _validate_search_options(
    *,
    top_k: int,
    min_similarity: float | None,
) -> None:
    if top_k < 1:
        raise RetrievalExecutionError("top_k must be at least 1")
    if (
        min_similarity is not None
        and not -1.0 <= min_similarity <= 1.0
    ):
        raise RetrievalExecutionError(
            "min_similarity must be between -1.0 and 1.0"
        )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise RetrievalExecutionError(
            "stored embedding dimension does not match query embedding"
        )
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise RetrievalExecutionError(
            "cosine similarity requires non-zero embeddings"
        )
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in vector) + "]"


def _search_postgresql(
    session,
    *,
    project_id: str,
    source_node_id: uuid.UUID,
    embedding: list[float],
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
    top_k: int,
    min_similarity: float | None,
) -> list[RetrievedNode]:
    threshold_clause = ""
    params: dict[str, object] = {
        "project_id": project_id,
        "source_node_id": source_node_id,
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "embedding_dimension": embedding_dimension,
        "query_vector": _vector_literal(embedding),
        "top_k": top_k,
    }
    if min_similarity is not None:
        threshold_clause = (
            "AND 1 - (ne.embedding <=> CAST(:query_vector AS vector)) "
            ">= :min_similarity "
        )
        params["min_similarity"] = min_similarity
    statement = text(
        "SELECT n.id AS target_node_id, "
        "n.version AS target_node_version, "
        "n.project_id AS project_id, "
        "1 - (ne.embedding <=> CAST(:query_vector AS vector)) "
        "AS similarity "
        "FROM node AS n "
        "JOIN node_embedding AS ne ON ne.node_id = n.id "
        "WHERE n.project_id = :project_id "
        "AND n.id <> :source_node_id "
        "AND n.graph_state IN ('ACTIVE', 'UNATTACHED') "
        "AND n.merged_into_node_id IS NULL "
        "AND ne.embedding_model = :embedding_model "
        "AND ne.embedding_version = :embedding_version "
        "AND ne.dimension = :embedding_dimension "
        "AND ne.status = 'READY' "
        "AND ne.embedding IS NOT NULL "
        f"{threshold_clause}"
        "ORDER BY ne.embedding <=> CAST(:query_vector AS vector), n.id "
        "LIMIT :top_k"
    )
    rows = session.execute(statement, params).mappings().all()
    return [
        RetrievedNode(
            target_node_id=row["target_node_id"],
            target_node_version=row["target_node_version"],
            project_id=row["project_id"],
            similarity=float(row["similarity"]),
        )
        for row in rows
    ]


def _search_sqlite(
    session,
    *,
    project_id: str,
    source_node_id: uuid.UUID,
    embedding: list[float],
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
    top_k: int,
    min_similarity: float | None,
) -> list[RetrievedNode]:
    rows = session.execute(
        select(Node, NodeEmbedding)
        .join(NodeEmbedding, NodeEmbedding.node_id == Node.id)
        .where(
            Node.project_id == project_id,
            Node.id != source_node_id,
            Node.graph_state.in_(_SEARCHABLE_GRAPH_STATES),
            Node.merged_into_node_id.is_(None),
            NodeEmbedding.embedding_model == embedding_model,
            NodeEmbedding.embedding_version == embedding_version,
            NodeEmbedding.dimension == embedding_dimension,
            NodeEmbedding.status == _READY_EMBEDDING_STATUS,
            NodeEmbedding.embedding.is_not(None),
        )
    ).all()
    candidates = []
    for node, stored in rows:
        similarity = _cosine_similarity(embedding, stored.embedding)
        if min_similarity is None or similarity >= min_similarity:
            candidates.append(
                RetrievedNode(
                    target_node_id=node.id,
                    target_node_version=node.version,
                    project_id=node.project_id,
                    similarity=similarity,
                )
            )
    candidates.sort(
        key=lambda row: (-row.similarity, str(row.target_node_id))
    )
    return candidates[:top_k]


def search_similar_nodes(
    session,
    *,
    project_id: str,
    source_node_id: uuid.UUID,
    embedding: list[float],
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
    top_k: int,
    min_similarity: float | None,
) -> list[RetrievedNode]:
    """Return only same-project searchable Nodes in deterministic order."""

    _validate_search_options(
        top_k=top_k,
        min_similarity=min_similarity,
    )
    arguments = {
        "session": session,
        "project_id": project_id,
        "source_node_id": source_node_id,
        "embedding": embedding,
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "embedding_dimension": embedding_dimension,
        "top_k": top_k,
        "min_similarity": min_similarity,
    }
    if session.get_bind().dialect.name == "postgresql":
        results = _search_postgresql(**arguments)
    else:
        results = _search_sqlite(**arguments)
    if any(row.project_id != project_id for row in results):
        raise CrossProjectRetrievalError(
            "Retrieval returned a Node from another project"
        )
    return results


__all__ = ["RetrievedNode", "search_similar_nodes"]
