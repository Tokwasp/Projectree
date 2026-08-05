"""Errors raised by the dependency-free Retrieval layer."""

from __future__ import annotations


class EmbeddingGenerationError(RuntimeError):
    pass


class EmbeddingValidationError(RuntimeError):
    pass


class RetrievalExecutionError(RuntimeError):
    pass


class CrossProjectRetrievalError(RetrievalExecutionError):
    pass


__all__ = [
    "CrossProjectRetrievalError",
    "EmbeddingGenerationError",
    "EmbeddingValidationError",
    "RetrievalExecutionError",
]
