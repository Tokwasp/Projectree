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
    AudioUploadEvent,
    AnalysisCandidate,
    AnalysisDeliveryState,
    BModelResult,
    CandidateReviewEvent,
    Category,
    Evidence,
    GenerationRun,
    GraphChangeEvent,
    Meeting,
    MeetingSummary,
    MergeOperation,
    MergeOperationDependency,
    Node,
    NodeAnalysisRun,
    NodeCandidate,
    NodeCandidateEvidence,
    NodeEmbedding,
    NodeEvidence,
    NodeMergeHistory,
    NodeRevision,
    NodeRevisionEvidence,
    AnalysisJob,
    OutboxEvent,
    ProjectGraphState,
    Relation,
    Request,
    RetrievalResult,
    TranscriptSegment,
)

__all__ = [
    "Base", "AudioUploadEvent", "CandidateReviewEvent", "BModelResult", "AnalysisCandidate", "AnalysisDeliveryState",
    "GenerationRun", "NodeRevision", "Evidence", "NodeRevisionEvidence",
    "MergeOperation", "MergeOperationDependency",
    "Meeting", "MeetingSummary", "ProjectGraphState", "Request", "Node", "NodeAnalysisRun", "RetrievalResult",
    "NodeCandidate", "NodeCandidateEvidence",
    "NodeEmbedding", "TranscriptSegment",
    "NodeEvidence", "NodeMergeHistory", "Relation", "GraphChangeEvent",
    "AnalysisJob", "OutboxEvent", "Category",
    "make_engine", "make_session_factory", "session_scope",
    "reseed_categories", "active_category_values",
    "EVIDENCE_KEY_VERSION", "build_evidence_key", "upsert_node_evidence",
]
