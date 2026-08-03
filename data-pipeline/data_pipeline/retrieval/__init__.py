"""Embedding and project-scoped pgvector Retrieval."""

from __future__ import annotations

from data_pipeline.config import RetrievalSettings, load_settings
from .embedding import (
    CurrentRevisionEmbeddingError,
    CurrentRevisionEmbeddingInput,
    EmbeddingClient,
    build_embedding_text,
    build_embedding_text_from_parts,
    embedding_text_hash,
    load_current_revision_embedding_input,
    validate_embedding,
)
from .embedding_client import (
    EmbeddingCallResult,
    EmbeddingClientSettings,
    EmbeddingResponseError,
    EmbeddingTransportError,
    EmbeddingUsage,
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
from .search import (
    RetrievedNode,
    search_link_candidates,
    search_merge_candidates,
    search_scoped_candidates,
    search_similar_nodes,
)


def retrieval_settings() -> RetrievalSettings:
    """Return the configured Retrieval policy."""
    return load_settings().retrieval


__all__ = [
    "CrossProjectRetrievalError",
    "CurrentRevisionEmbeddingError",
    "CurrentRevisionEmbeddingInput",
    "EmbeddingClient",
    "EmbeddingCallResult",
    "EmbeddingClientSettings",
    "EmbeddingGenerationError",
    "EmbeddingResponseError",
    "EmbeddingTransportError",
    "EmbeddingUsage",
    "EmbeddingValidationError",
    "GmsEmbeddingClient",
    "RetrievalExecutionError",
    "RetrievalSettings",
    "RetrievedNode",
    "build_embedding_client",
    "build_embedding_text",
    "EMBEDDING_CONTRACT_VERSION",
    "build_embedding_text_from_parts",
    "embedding_text_hash",
    "load_current_revision_embedding_input",
    "load_embedding_client_settings",
    "retrieval_settings",
    "search_link_candidates",
    "search_merge_candidates",
    "search_scoped_candidates",
    "search_similar_nodes",
    "validate_embedding",
]
