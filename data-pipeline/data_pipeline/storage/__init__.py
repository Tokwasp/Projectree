"""storage — SQLAlchemy 모델 + alembic 마이그레이션 + 엔진/세션."""

from __future__ import annotations

from .categories import active_category_values, reseed_categories
from .db import make_engine, make_session_factory, session_scope
from .evidence import (
    EVIDENCE_KEY_VERSION,
    build_evidence_key,
    upsert_node_evidence,
)
from .models import (
    Base,
    CandidateReviewEvent,
    Category,
    GraphChangeEvent,
    Meeting,
    Node,
    NodeAnalysisRun,
    NodeCandidate,
    NodeCandidateEvidence,
    NodeEmbedding,
    NodeEvidence,
    OutboxEvent,
    Relation,
    Request,
    RetrievalResult,
    TranscriptSegment,
)

__all__ = [
    "Base", "CandidateReviewEvent",
    "Meeting", "Request", "Node", "NodeAnalysisRun", "RetrievalResult",
    "NodeCandidate", "NodeCandidateEvidence",
    "NodeEmbedding", "TranscriptSegment",
    "NodeEvidence", "Relation", "GraphChangeEvent", "OutboxEvent", "Category",
    "make_engine", "make_session_factory", "session_scope",
    "reseed_categories", "active_category_values",
    "EVIDENCE_KEY_VERSION", "build_evidence_key", "upsert_node_evidence",
]
