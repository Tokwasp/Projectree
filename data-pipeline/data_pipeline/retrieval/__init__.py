"""Embedding and project-scoped pgvector Retrieval."""

from __future__ import annotations

from data_pipeline.config import RetrievalSettings, load_settings
from .embedding import (
    EmbeddingClient,
    build_embedding_text,
    embedding_text_hash,
    validate_embedding,
)
from .embedding_client import (
    EmbeddingClientSettings,
    EmbeddingResponseError,
    EmbeddingTransportError,
    GmsEmbeddingClient,
    build_embedding_client,
    load_embedding_client_settings,
)
from .errors import (
    CrossProjectRetrievalError,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    RetrievalExecutionError,
)
from .search import RetrievedNode, search_similar_nodes


def retrieval_settings() -> RetrievalSettings:
    """Return the configured Retrieval policy."""
    return load_settings().retrieval


__all__ = [
    "CrossProjectRetrievalError",
    "EmbeddingClient",
    "EmbeddingClientSettings",
    "EmbeddingGenerationError",
    "EmbeddingResponseError",
    "EmbeddingTransportError",
    "EmbeddingValidationError",
    "GmsEmbeddingClient",
    "RetrievalExecutionError",
    "RetrievalSettings",
    "RetrievedNode",
    "build_embedding_client",
    "build_embedding_text",
    "embedding_text_hash",
    "load_embedding_client_settings",
    "retrieval_settings",
    "search_similar_nodes",
    "validate_embedding",
]
