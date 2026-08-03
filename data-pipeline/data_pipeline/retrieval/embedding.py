"""Deterministic embedding input and an injectable client boundary."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select

from data_pipeline.storage import (
    Evidence,
    Node,
    NodeRevision,
    NodeRevisionEvidence,
)
from .errors import EmbeddingValidationError


class EmbeddingClient(Protocol):
    """Implemented by an external adapter; tests provide an offline fake."""

    def embed(
        self,
        *,
        text: str,
        model: str,
        dimensions: int,
    ) -> Sequence[float]:
        ...


class CurrentRevisionEmbeddingError(ValueError):
    """The Node cannot produce a trustworthy current-Revision embedding."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CurrentRevisionEmbeddingInput:
    revision_id: uuid.UUID
    revision_version: int
    text: str
    text_hash: str


#: Embedding input contract version. v2 drops Category from the meaning so a
#: Category-only edit never invalidates a vector or costs a provider call.
#: node_embedding.embedding_version is part of that table's primary key and was
#: widened to varchar(64) in 0007 to hold this name; SQLite ignores declared
#: widths, so test_embedding_v2_contract guards the length against the column.
EMBEDDING_CONTRACT_VERSION = "node-embedding-v2-no-category"

EvidencePair = tuple[str | None, str]
TimedEvidencePair = tuple[int | None, str | None, str]


def _canonical_evidence(
    evidence_pairs: Iterable[EvidencePair | TimedEvidencePair],
) -> list[tuple[str, str]]:
    """Order Evidence deterministically without serializing its timestamp."""

    sortable: list[tuple[int, str, str]] = []
    for pair in evidence_pairs:
        if len(pair) == 2:
            source_segment_id, quoted_text = pair
            start_ms = None
        else:
            start_ms, source_segment_id, quoted_text = pair
        sortable.append(
            (
                start_ms if start_ms is not None else 2**63 - 1,
                source_segment_id or "",
                quoted_text,
            )
        )
    sortable.sort()
    return [(source_segment_id, quoted_text) for _, source_segment_id, quoted_text in sortable]


def build_embedding_text_from_parts(
    *,
    node_type: str,
    title: str,
    content: str,
    evidence_pairs: Iterable[EvidencePair | TimedEvidencePair],
    category: str | None = None,
) -> str:
    """Serialize the stable Retrieval meaning contract (v2).

    ``category`` is accepted only as a deprecated compatibility argument so
    existing call sites keep working; it is deliberately NOT serialized and NOT
    hashed. Category remains authoritative for search scoping, the MERGE gate,
    B-model input and display — it simply is not part of the meaning vector.
    """

    del category  # v2: never part of the serialized meaning
    evidence = _canonical_evidence(evidence_pairs)
    return json.dumps(
        [node_type, title, content, evidence],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_embedding_text(node: Node) -> str:
    """Compatibility wrapper for Nodes that only have legacy evidence."""

    return build_embedding_text_from_parts(
        node_type=node.node_type,
        title=node.title,
        content=node.content,
        evidence_pairs=(
            (row.segment_id or "", row.quote)
            for row in node.evidence
        ),
    )


def load_current_revision_embedding_input(
    session,
    *,
    node: Node,
) -> CurrentRevisionEmbeddingInput:
    """Build input strictly from the Node's immutable current Revision."""

    if node.current_revision_id is None:
        raise CurrentRevisionEmbeddingError("NO_CURRENT_REVISION")
    revision = session.get(NodeRevision, node.current_revision_id)
    if (
        revision is None
        or revision.node_id != node.id
        or revision.project_id != node.project_id
    ):
        raise CurrentRevisionEmbeddingError("INVALID_CURRENT_REVISION")

    links = session.execute(
        select(NodeRevisionEvidence).where(
            NodeRevisionEvidence.node_revision_id == revision.id
        )
    ).scalars().all()
    evidence_pairs: list[TimedEvidencePair] = []
    for link in links:
        if link.project_id != node.project_id:
            raise CurrentRevisionEmbeddingError("INVALID_CURRENT_REVISION")
        evidence = session.get(Evidence, link.evidence_id)
        if evidence is None or evidence.project_id != node.project_id:
            raise CurrentRevisionEmbeddingError("INVALID_CURRENT_REVISION")
        evidence_pairs.append(
            (
                evidence.start_ms,
                evidence.source_segment_id or "",
                evidence.quoted_text,
            )
        )
    if revision.requires_evidence and not evidence_pairs:
        raise CurrentRevisionEmbeddingError("INVALID_CURRENT_REVISION")

    text = build_embedding_text_from_parts(
        node_type=revision.node_type,
        title=revision.title,
        content=revision.content,
        evidence_pairs=evidence_pairs,
    )
    return CurrentRevisionEmbeddingInput(
        revision_id=revision.id,
        revision_version=revision.version,
        text=text,
        text_hash=embedding_text_hash(text),
    )


def embedding_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_embedding(
    embedding: Sequence[float],
    *,
    expected_dimension: int,
) -> list[float]:
    try:
        vector = [float(value) for value in embedding]
    except (TypeError, ValueError) as exc:
        raise EmbeddingValidationError(
            "embedding must contain only numeric values"
        ) from exc
    if len(vector) != expected_dimension:
        raise EmbeddingValidationError(
            "embedding dimension mismatch: "
            f"expected={expected_dimension}, actual={len(vector)}"
        )
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingValidationError(
            "embedding must contain only finite values"
        )
    if not any(value != 0.0 for value in vector):
        raise EmbeddingValidationError(
            "embedding must not be a zero vector"
        )
    return vector


__all__ = [
    "EMBEDDING_CONTRACT_VERSION",
    "CurrentRevisionEmbeddingError",
    "CurrentRevisionEmbeddingInput",
    "EmbeddingClient",
    "build_embedding_text",
    "build_embedding_text_from_parts",
    "embedding_text_hash",
    "load_current_revision_embedding_input",
    "validate_embedding",
]
