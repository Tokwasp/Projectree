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
    require_category: str | None = None,
    require_node_type: str | tuple[str, ...] | None = None,
    graph_states: tuple[str, ...] = _SEARCHABLE_GRAPH_STATES,
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
    policy_clause = ""
    # Filter on the Node projection rather than JOINing node_revision.
    # NodeRevision is the source of truth, but Node.category/node_type are kept
    # in lockstep by create_node_revision (proved by
    # test_node_category_projection_tracks_the_current_revision). An INNER JOIN
    # on current_revision_id would silently drop legacy Nodes that predate the
    # revision table, hiding valid MERGE targets.
    if require_category is not None:
        policy_clause += "AND n.category = :require_category "
        params["require_category"] = require_category
    if require_node_type is not None:
        types = (
            (require_node_type,)
            if isinstance(require_node_type, str)
            else tuple(require_node_type)
        )
        keys = []
        for index, value in enumerate(types):
            key = f"require_node_type_{index}"
            params[key] = value
            keys.append(f":{key}")
        policy_clause += "AND n.node_type IN (" + ", ".join(keys) + ") "
    state_names = tuple(graph_states)
    state_params = []
    for index, state in enumerate(state_names):
        key = f"graph_state_{index}"
        params[key] = state
        state_params.append(f":{key}")
    state_clause = "AND n.deleted_at IS NULL AND n.graph_state IN (" + ", ".join(state_params) + ") "
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
        f"{state_clause}"
        "AND n.merged_into_node_id IS NULL "
        f"{policy_clause}"
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
    require_category: str | None = None,
    require_node_type: str | tuple[str, ...] | None = None,
    graph_states: tuple[str, ...] = _SEARCHABLE_GRAPH_STATES,
) -> list[RetrievedNode]:
    statement = (
        select(Node, NodeEmbedding)
        .join(NodeEmbedding, NodeEmbedding.node_id == Node.id)
        .where(
            Node.project_id == project_id,
            Node.id != source_node_id,
            Node.graph_state.in_(tuple(graph_states)),
            Node.deleted_at.is_(None),
            Node.merged_into_node_id.is_(None),
            NodeEmbedding.embedding_model == embedding_model,
            NodeEmbedding.embedding_version == embedding_version,
            NodeEmbedding.dimension == embedding_dimension,
            NodeEmbedding.status == _READY_EMBEDDING_STATUS,
            NodeEmbedding.embedding.is_not(None),
        )
    )
    if require_category is not None:
        statement = statement.where(Node.category == require_category)
    if require_node_type is not None:
        types = (
            (require_node_type,)
            if isinstance(require_node_type, str)
            else tuple(require_node_type)
        )
        statement = statement.where(Node.node_type.in_(types))
    rows = session.execute(statement).all()
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


def _search(session, **arguments) -> list[RetrievedNode]:
    project_id = arguments["project_id"]
    _validate_search_options(
        top_k=arguments["top_k"],
        min_similarity=arguments["min_similarity"],
    )
    if session.get_bind().dialect.name == "postgresql":
        results = _search_postgresql(session=session, **arguments)
    else:
        results = _search_sqlite(session=session, **arguments)
    if any(row.project_id != project_id for row in results):
        raise CrossProjectRetrievalError(
            "Retrieval returned a Node from another project"
        )
    return results


def search_merge_candidates(
    session,
    *,
    project_id: str,
    source_node_id: uuid.UUID,
    embedding: list[float],
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
    category: str,
    node_type: str,
    top_k: int,
    min_similarity: float | None,
) -> list[RetrievedNode]:
    """Automatic-MERGE candidates: same project, category, type; ACTIVE canonical.

    Category and node_type are HARD filters here. A merge folds two Nodes into
    one identity, so a cross-category or cross-type target is never acceptable.
    UNATTACHED targets are excluded: only an ACTIVE canonical Node may absorb.
    """

    return _search(
        session,
        project_id=project_id,
        source_node_id=source_node_id,
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        embedding_dimension=embedding_dimension,
        top_k=top_k,
        min_similarity=min_similarity,
        require_category=category,
        require_node_type=node_type,
        graph_states=("ACTIVE",),
    )


def search_link_candidates(
    session,
    *,
    project_id: str,
    source_node_id: uuid.UUID,
    embedding: list[float],
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
    category: str,
    parent_node_type: str,
    top_k: int,
    min_similarity: float | None,
) -> list[RetrievedNode]:
    """LINK/parent candidates: same project, same category, ACTIVE canonical.

    Category is a Graph partition, not a display tag: a BACKEND Action and a
    FRONTEND Action for the same feature are separate Nodes and neither may
    parent the other. The caller still has to check that ``parent_node_type``
    is legal for the child via ``is_allowed_parent_type``; this only scopes the
    candidate set.
    """

    return _search(
        session,
        project_id=project_id,
        source_node_id=source_node_id,
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        embedding_dimension=embedding_dimension,
        top_k=top_k,
        min_similarity=min_similarity,
        require_category=category,
        require_node_type=parent_node_type,
        graph_states=("ACTIVE",),
    )


def search_scoped_candidates(
    session,
    *,
    project_id: str,
    source_node_id: uuid.UUID,
    embedding: list[float],
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
    category: str,
    node_types: tuple[str, ...],
    top_k: int,
    min_similarity: float | None,
) -> list[RetrievedNode]:
    """One candidate set that both MERGE and LINK may legally draw from.

    The manual re-analysis path asks the B model for a single recommendation
    that may turn out to be MERGE or LINK, so it cannot use either of the
    purpose-built searches alone. Everything both policies share is still
    enforced here — same project, same category, ACTIVE canonical — and
    ``node_types`` is the union of the source's own type (MERGE) and its legal
    parent types (LINK).
    """

    return _search(
        session,
        project_id=project_id,
        source_node_id=source_node_id,
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        embedding_dimension=embedding_dimension,
        top_k=top_k,
        min_similarity=min_similarity,
        require_category=category,
        require_node_type=tuple(node_types),
        graph_states=("ACTIVE",),
    )


__all__ = [
    "RetrievedNode",
    "search_link_candidates",
    "search_merge_candidates",
    "search_scoped_candidates",
    "search_similar_nodes",
]
