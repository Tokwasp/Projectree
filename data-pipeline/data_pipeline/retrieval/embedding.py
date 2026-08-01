"""Deterministic embedding input and an injectable client boundary."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from typing import Protocol

from data_pipeline.storage import Node
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


def build_embedding_text(node: Node) -> str:
    """Serialize all contract-defined Retrieval inputs deterministically."""

    evidence = sorted(
        (row.segment_id, row.quote)
        for row in node.evidence
    )
    return json.dumps(
        [
            node.node_type,
            node.category,
            node.title,
            node.content,
            evidence,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
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
    "EmbeddingClient",
    "build_embedding_text",
    "embedding_text_hash",
    "validate_embedding",
]
