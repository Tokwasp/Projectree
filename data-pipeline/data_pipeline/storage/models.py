"""SQLAlchemy 2.0 모델 (v2.2 D1′~D1‴).

원칙:
  - 전 테이블 내부 PK = id UUID. 외부 식별자(external_meeting_id, source_item_id 등)는 분리.
  - node 에는 embedding 컬럼 없음 — node_embedding 별도 테이블(모델 고정 1536/v1).
  - graph_change_event 는 append-only(before/after JSONB), outbox_event 는 범용.
  - advisory lock 없음 — UNIQUE + (ON CONFLICT/IntegrityError) + 처리 상태 + version(optimistic).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .types import JSONB_or_JSON, Vector


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Meeting(Base):
    __tablename__ = "meeting"
    __table_args__ = (
        UniqueConstraint("project_id", "external_meeting_id", name="uq_meeting_project_external"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_meeting_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Request(Base):
    """Generation claim and lifecycle boundary."""

    __tablename__ = "request"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "external_meeting_id", "input_hash",
            name="uq_request_generation_input",
        ),
        CheckConstraint(
            "status IN "
            "('PROCESSING', 'REVIEW_PENDING', 'REVIEW_COMPLETED', 'FAILED', 'COMPLETED')",
            name="ck_request_status",
        ),
        CheckConstraint(
            "failure_stage IS NULL OR failure_stage IN ('EXTRACTION', 'JUDGMENT', 'PERSISTENCE')",
            name="ck_request_failure_stage",
        ),
        Index("ix_request_status", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_meeting_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, default="NODE_GENERATION")
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROCESSING")
    lineage: Mapped[dict | None] = mapped_column(JSONB_or_JSON, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSONB_or_JSON, nullable=True)
    raw_extraction: Mapped[dict | list | str | None] = mapped_column(JSONB_or_JSON, nullable=True)
    raw_judgment: Mapped[dict | list | str | None] = mapped_column(JSONB_or_JSON, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB_or_JSON, nullable=True)
    failure_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class AudioUploadEvent(Base):
    """Durable S3 ObjectCreated idempotency and processing claim."""

    __tablename__ = "audio_upload_event"
    __table_args__ = (
        UniqueConstraint(
            "bucket",
            "object_key",
            "object_identity",
            name="uq_audio_upload_object_identity",
        ),
        CheckConstraint(
            "identity_kind IN ('VERSION_ID', 'ETAG')",
            name="ck_audio_upload_identity_kind",
        ),
        CheckConstraint(
            "status IN ('PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_audio_upload_status",
        ),
        CheckConstraint(
            "attempt_count >= 1",
            name="ck_audio_upload_attempt_positive",
        ),
        Index(
            "ix_audio_upload_project_meeting",
            "project_id",
            "external_meeting_id",
        ),
        Index("ix_audio_upload_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    object_identity: Mapped[str] = mapped_column(String(1024), nullable=False)
    identity_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    object_size: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_meeting_id: Mapped[str] = mapped_column(String(128), nullable=False)
    upload_id: Mapped[str] = mapped_column(String(128), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PROCESSING",
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    external_request_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    pipeline_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pipeline_outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )


class Node(Base):
    __tablename__ = "node"
    __table_args__ = (
        UniqueConstraint("source_candidate_id", name="uq_node_source_candidate"),
        UniqueConstraint("project_id", "id", name="uq_node_project_id"),
        CheckConstraint("version >= 1", name="ck_node_version_positive"),
        CheckConstraint(
            "node_type IN ('DECISION', 'ACTION', 'ISSUE')",
            name="ck_node_type",
        ),
        CheckConstraint(
            "graph_state IN "
            "('ACTIVE', 'UNATTACHED', 'EXCLUDED', 'MERGED', 'ARCHIVED')",
            name="ck_node_graph_state",
        ),
        CheckConstraint(
            "(node_type = 'DECISION' "
            "AND lifecycle_status IN ('ACTIVE', 'SUPERSEDED')) OR "
            "(node_type = 'ACTION' "
            "AND lifecycle_status IN "
            "('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')) OR "
            "(node_type = 'ISSUE' "
            "AND lifecycle_status IN ('OPEN', 'RESOLVED'))",
            name="ck_node_lifecycle_by_type",
        ),
        CheckConstraint(
            "(graph_state = 'MERGED' AND merged_into_node_id IS NOT NULL) OR "
            "(graph_state <> 'MERGED' AND merged_into_node_id IS NULL)",
            name="ck_node_merge_shape",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="ck_node_not_self_parent",
        ),
        CheckConstraint(
            "merged_into_node_id IS NULL OR merged_into_node_id <> id",
            name="ck_node_not_self_merge",
        ),
        CheckConstraint(
            "analysis_status IN "
            "('PENDING', 'ANALYZING', 'ANALYZED', 'STALE', 'FAILED')",
            name="ck_node_analysis_status",
        ),
        ForeignKeyConstraint(
            ["project_id", "parent_id"],
            ["node.project_id", "node.id"],
            name="fk_node_parent_project",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["project_id", "merged_into_node_id"],
            ["node.project_id", "node.id"],
            name="fk_node_merged_into_project",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["id", "current_analysis_run_id"],
            [
                "node_analysis_run.source_node_id",
                "node_analysis_run.id",
            ],
            name="fk_node_current_analysis_run",
            use_alter=True,
        ),
        Index("ix_node_merged_into_node_id", "merged_into_node_id"),
        Index("ix_node_current_analysis_run_id", "current_analysis_run_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    source_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "node_candidate.id",
            name="fk_node_source_candidate",
            use_alter=True,
        ),
        nullable=True,
    )
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_meeting_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), ForeignKey("category.value", name="fk_node_category"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_node_parent"), nullable=True
    )
    graph_state: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    merged_into_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_node_merged_into"),
        nullable=True,
    )
    analysis_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PENDING",
    )
    analysis_input_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    current_analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        nullable=True,
    )
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    initial_reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    initial_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    evidence: Mapped[list["NodeEvidence"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class NodeEmbedding(Base):
    """R4′: 버전별 임베딩 분리. PK(node_id, embedding_version) — 모델 교체 시 신규 버전 전량
    재색인 후 검색기 스왑(신구 병행 조회). MVP 는 text-embedding-3-small/1536/v1 고정."""

    __tablename__ = "node_embedding"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'READY', 'STALE', 'FAILED')",
            name="ck_node_embedding_status",
        ),
        CheckConstraint(
            "dimension = 1536",
            name="ck_node_embedding_dimension",
        ),
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_embedding_node", ondelete="CASCADE"), primary_key=True
    )
    embedding_version: Mapped[str] = mapped_column(String(16), primary_key=True, default="v1")
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False, default="text-embedding-3-small")
    dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=1536)
    embedded_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TranscriptSegment(Base):
    """D1″: raw STT and normalized evidence text with stable sequence."""

    __tablename__ = "transcript_segment"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "external_meeting_id", "segment_id",
            name="uq_segment_source",
        ),
        UniqueConstraint(
            "project_id", "external_meeting_id", "sequence_no",
            name="uq_segment_sequence",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_meeting_id: Mapped[str] = mapped_column(String(128), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speaker_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalization_metadata: Mapped[dict | None] = mapped_column(
        JSONB_or_JSON,
        nullable=True,
    )


class NodeEvidence(Base):
    """D1″: quote_start/quote_end 는 서버가 세그먼트 원문에서 역산한 char 오프셋(규칙 4)."""

    __tablename__ = "node_evidence"
    __table_args__ = (
        Index(
            "uq_node_evidence_node_key",
            "node_id",
            "evidence_key",
            unique=True,
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_evidence_node", ondelete="CASCADE"), nullable=False
    )
    evidence_key: Mapped[str] = mapped_column(String(64), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_meeting_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    node: Mapped[Node] = relationship(back_populates="evidence")


class NodeAnalysisRun(Base):
    """One durable attempt to analyze one immutable Node input version."""

    __tablename__ = "node_analysis_run"
    __table_args__ = (
        UniqueConstraint(
            "source_node_id",
            "source_node_version",
            "analysis_input_hash",
            "attempt",
            name="uq_analysis_run_node_version_hash_attempt",
        ),
        UniqueConstraint(
            "source_node_id",
            "id",
            name="uq_analysis_run_source_node_id",
        ),
        CheckConstraint(
            "status IN "
            "('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SUPERSEDED')",
            name="ck_analysis_run_status",
        ),
        CheckConstraint(
            "source_node_version >= 1",
            name="ck_analysis_run_node_version_positive",
        ),
        CheckConstraint("attempt >= 1", name="ck_analysis_run_attempt_positive"),
        CheckConstraint(
            "retrieval_status IN ('PENDING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_run_retrieval_status",
        ),
        CheckConstraint(
            "b_model_status IN "
            "('PENDING', 'RUNNING', 'SUCCEEDED', 'SKIPPED', 'FAILED')",
            name="ck_analysis_run_b_model_status",
        ),
        CheckConstraint(
            "retrieval_result_count IS NULL OR retrieval_result_count >= 0",
            name="ck_analysis_run_retrieval_count_non_negative",
        ),
        Index(
            "ix_analysis_run_node_hash_status",
            "source_node_id",
            "analysis_input_hash",
            "status",
        ),
        Index(
            "uq_analysis_run_active_node_hash",
            "source_node_id",
            "analysis_input_hash",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING', 'RUNNING')"
            ),
            sqlite_where=text(
                "status IN ('PENDING', 'RUNNING')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "node.id",
            name="fk_analysis_run_source_node",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_node_version: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_input_hash_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    retrieval_config_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    embedding_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    retrieval_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PENDING",
    )
    retrieval_result_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    retrieval_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    b_model_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PENDING",
    )
    b_model_skip_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    b_model_failure_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    b_model_failure_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    b_model_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    b_model_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PENDING",
    )
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )


class RetrievalResult(Base):
    """Ranked Retrieval output persisted by a future worker."""

    __tablename__ = "retrieval_result"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "rank",
            name="uq_retrieval_result_run_rank",
        ),
        UniqueConstraint(
            "analysis_run_id",
            "target_node_id",
            name="uq_retrieval_result_run_target",
        ),
        CheckConstraint("rank >= 1", name="ck_retrieval_result_rank_positive"),
        CheckConstraint(
            "target_node_version >= 1",
            name="ck_retrieval_result_target_version_positive",
        ),
        Index("ix_retrieval_result_target_node", "target_node_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "node_analysis_run.id",
            name="fk_retrieval_result_analysis_run",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_retrieval_result_target_node"),
        nullable=False,
    )
    target_node_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )


class BModelResult(Base):
    """Validated B-model recommendation; raw model payload is not retained."""

    __tablename__ = "b_model_result"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            name="uq_b_model_result_analysis_run",
        ),
        CheckConstraint(
            "recommendation IN ('CREATE_NEW', 'LINK', 'MERGE')",
            name="ck_b_model_result_recommendation",
        ),
        CheckConstraint(
            "validation_status = 'VALIDATED'",
            name="ck_b_model_result_validation_status",
        ),
        CheckConstraint(
            "source_node_version >= 1",
            name="ck_b_model_result_source_version_positive",
        ),
        CheckConstraint(
            "target_node_version IS NULL OR target_node_version >= 1",
            name="ck_b_model_result_target_version_positive",
        ),
        CheckConstraint(
            "(recommendation = 'CREATE_NEW' "
            "AND target_node_id IS NULL AND relation_type IS NULL) OR "
            "(recommendation = 'LINK' "
            "AND target_node_id IS NOT NULL "
            "AND relation_type IN ('ATTACHED_TO', 'RELATED_TO')) OR "
            "(recommendation = 'MERGE' "
            "AND target_node_id IS NOT NULL AND relation_type IS NULL)",
            name="ck_b_model_result_shape",
        ),
        Index("ix_b_model_result_source_node", "source_node_id"),
        Index("ix_b_model_result_target_node", "target_node_id"),
        ForeignKeyConstraint(
            ["project_id", "source_node_id"],
            ["node.project_id", "node.id"],
            name="fk_b_model_result_source_project",
        ),
        ForeignKeyConstraint(
            ["project_id", "target_node_id"],
            ["node.project_id", "node.id"],
            name="fk_b_model_result_target_project",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "node_analysis_run.id",
            name="fk_b_model_result_analysis_run",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_b_model_result_source_node"),
        nullable=False,
    )
    source_node_version: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    target_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_b_model_result_target_node"),
        nullable=True,
    )
    target_node_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    relation_type: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    suggested_title: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_content: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB_or_JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="VALIDATED",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )


class AnalysisCandidate(Base):
    """Final user decision candidate produced from one validated B result."""

    __tablename__ = "analysis_candidate"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            name="uq_analysis_candidate_run",
        ),
        UniqueConstraint(
            "b_model_result_id",
            name="uq_analysis_candidate_b_model_result",
        ),
        CheckConstraint(
            "recommendation IN ('CREATE_NEW', 'LINK', 'MERGE')",
            name="ck_analysis_candidate_recommendation",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_analysis_candidate_status",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_analysis_candidate_version_positive",
        ),
        CheckConstraint(
            "source_node_version >= 1",
            name="ck_analysis_candidate_source_version_positive",
        ),
        CheckConstraint(
            "target_node_version IS NULL OR target_node_version >= 1",
            name="ck_analysis_candidate_target_version_positive",
        ),
        CheckConstraint(
            "(recommendation = 'CREATE_NEW' "
            "AND target_node_id IS NULL AND relation_type IS NULL) OR "
            "(recommendation = 'LINK' "
            "AND target_node_id IS NOT NULL "
            "AND relation_type IN ('ATTACHED_TO', 'RELATED_TO')) OR "
            "(recommendation = 'MERGE' "
            "AND target_node_id IS NOT NULL AND relation_type IS NULL)",
            name="ck_analysis_candidate_shape",
        ),
        Index(
            "ix_analysis_candidate_project_status",
            "project_id",
            "status",
        ),
        Index("ix_analysis_candidate_source_node", "source_node_id"),
        Index("ix_analysis_candidate_target_node", "target_node_id"),
        ForeignKeyConstraint(
            ["project_id", "source_node_id"],
            ["node.project_id", "node.id"],
            name="fk_analysis_candidate_source_project",
        ),
        ForeignKeyConstraint(
            ["project_id", "target_node_id"],
            ["node.project_id", "node.id"],
            name="fk_analysis_candidate_target_project",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "node_analysis_run.id",
            name="fk_analysis_candidate_analysis_run",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    b_model_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "b_model_result.id",
            name="fk_analysis_candidate_b_model_result",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_analysis_candidate_source_node"),
        nullable=False,
    )
    source_node_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_analysis_candidate_target_node"),
        nullable=True,
    )
    target_node_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    relation_type: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    suggested_title: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_content: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PENDING",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    decided_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )


class NodeCandidate(Base):
    """LLM generation 결과를 사용자 승인 전까지 보존하는 PROPOSED 후보."""

    __tablename__ = "node_candidate"
    __table_args__ = (
        UniqueConstraint("request_id", "source_item_id", name="uq_candidate_request_item"),
        UniqueConstraint("confirmed_node_id", name="uq_candidate_confirmed_node"),
        Index(
            # 0003 created this as a unique index (rather than a named UNIQUE
            # constraint).  Keep ORM metadata identical to the applied schema
            # so ``alembic check`` never proposes a destructive index swap.
            "uq_candidate_initial_review_node",
            "initial_review_node_id",
            unique=True,
        ),
        CheckConstraint("version >= 1", name="ck_candidate_version_positive"),
        CheckConstraint(
            "NOT (suggested_parent_candidate_id IS NOT NULL "
            "AND suggested_parent_node_id IS NOT NULL)",
            name="ck_candidate_suggested_parent_exclusive",
        ),
        CheckConstraint(
            "NOT (reviewed_parent_candidate_id IS NOT NULL "
            "AND reviewed_parent_node_id IS NOT NULL)",
            name="ck_candidate_reviewed_parent_exclusive",
        ),
        CheckConstraint(
            "(reviewed_parent_mode = 'INHERIT' "
            "AND reviewed_parent_candidate_id IS NULL "
            "AND reviewed_parent_node_id IS NULL) OR "
            "(reviewed_parent_mode = 'NONE' "
            "AND reviewed_parent_candidate_id IS NULL "
            "AND reviewed_parent_node_id IS NULL) OR "
            "(reviewed_parent_mode = 'CANDIDATE' "
            "AND reviewed_parent_candidate_id IS NOT NULL "
            "AND reviewed_parent_node_id IS NULL) OR "
            "(reviewed_parent_mode = 'NODE' "
            "AND reviewed_parent_candidate_id IS NULL "
            "AND reviewed_parent_node_id IS NOT NULL)",
            name="ck_candidate_reviewed_parent_mode",
        ),
        CheckConstraint(
            "review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_candidate_review_status",
        ),
        CheckConstraint(
            "suggested_node_type IN ('DECISION', 'ACTION', 'ISSUE', 'UNKNOWN')",
            name="ck_candidate_suggested_node_type",
        ),
        Index("ix_candidate_review_status", "review_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("request.id", name="fk_candidate_request", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_meeting_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_item: Mapped[dict] = mapped_column(JSONB_or_JSON, nullable=False)
    raw_judgment: Mapped[dict | None] = mapped_column(JSONB_or_JSON, nullable=True)

    suggested_node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    suggested_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggested_title: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_content: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ACTION lifecycle state proposed by the LLM from the speaker's tense.
    # NULL for DECISION/ISSUE and for ACTIONs the model could not place.
    suggested_lifecycle_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    suggested_parent_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("node_candidate.id", name="fk_candidate_suggested_parent_candidate"),
        nullable=True,
    )
    suggested_parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_candidate_suggested_parent_node"), nullable=True
    )

    reviewed_node_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reviewed_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reviewer override of the ACTION lifecycle state; wins over the suggestion.
    reviewed_lifecycle_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    reviewed_parent_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="INHERIT"
    )
    reviewed_parent_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("node_candidate.id", name="fk_candidate_reviewed_parent_candidate"),
        nullable=True,
    )
    reviewed_parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_candidate_reviewed_parent_node"), nullable=True
    )

    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    confirmed_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_candidate_confirmed_node"), nullable=True
    )
    initial_review_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "node.id",
            name="fk_candidate_initial_review_node",
            use_alter=True,
        ),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    evidence: Mapped[list["NodeCandidateEvidence"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class CandidateReviewEvent(Base):
    """Append-only user review audit without prompts or transcript payloads."""

    __tablename__ = "candidate_review_event"
    __table_args__ = (
        CheckConstraint(
            "action IN ('EDIT', 'APPROVE', 'REJECT')",
            name="ck_candidate_review_event_action",
        ),
        Index("ix_candidate_review_event_candidate", "candidate_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "node_candidate.id",
            name="fk_candidate_review_event_candidate",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "request.id",
            name="fk_candidate_review_event_request",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    before_json: Mapped[dict] = mapped_column(JSONB_or_JSON, nullable=False)
    after_json: Mapped[dict] = mapped_column(JSONB_or_JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class NodeCandidateEvidence(Base):
    __tablename__ = "node_candidate_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("node_candidate.id", name="fk_candidate_evidence_candidate", ondelete="CASCADE"),
        nullable=False,
    )
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_meeting_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    candidate: Mapped[NodeCandidate] = relationship(back_populates="evidence")


class Relation(Base):
    """ATTACHED_TO/SAME/REVERSES/FOLLOWS/RESOLVED_BY × status.
    중복 후보도 SAME+PROPOSED 로 표현 (별도 duplicate_candidate 타입 금지)."""

    __tablename__ = "relation"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "from_node_id", "to_node_id", "relation_type",
            name="uq_relation",
        ),
        CheckConstraint(
            "relation_type IN "
            "('ATTACHED_TO', 'RELATED_TO', 'SAME', 'REVERSES', "
            "'FOLLOWS', 'RESOLVED_BY')",
            name="ck_relation_type",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'CONFIRMED', 'REJECTED')",
            name="ck_relation_status",
        ),
        CheckConstraint(
            "from_node_id <> to_node_id",
            name="ck_relation_not_self",
        ),
        ForeignKeyConstraint(
            ["project_id", "from_node_id"],
            ["node.project_id", "node.id"],
            name="fk_relation_from_project",
        ),
        ForeignKeyConstraint(
            ["project_id", "to_node_id"],
            ["node.project_id", "node.id"],
            name="fk_relation_to_project",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_relation_from"), nullable=False
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_relation_to"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROPOSED")
    # M4: 재제안 억제 키 구성 요소. 내용·규칙이 바뀌면 재제안 가능(영구 차단 방지).
    from_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merge_rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="AI")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class NodeMergeHistory(Base):
    """Append-only merge lineage required to resolve evidence provenance."""

    __tablename__ = "node_merge_history"
    __table_args__ = (
        UniqueConstraint(
            "source_node_id",
            name="uq_node_merge_history_source",
        ),
        Index("ix_node_merge_history_target", "target_node_id"),
        ForeignKeyConstraint(
            ["project_id", "source_node_id"],
            ["node.project_id", "node.id"],
            name="fk_merge_history_source_project",
        ),
        ForeignKeyConstraint(
            ["project_id", "target_node_id"],
            ["node.project_id", "node.id"],
            name="fk_merge_history_target_project",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_merge_history_source"),
        nullable=False,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_merge_history_target"),
        nullable=False,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "node_analysis_run.id",
            name="fk_merge_history_analysis_run",
        ),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "analysis_candidate.id",
            name="fk_merge_history_candidate",
        ),
        nullable=False,
        unique=True,
    )
    approved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_version: Mapped[int] = mapped_column(Integer, nullable=False)
    merged_title: Mapped[str] = mapped_column(Text, nullable=False)
    merged_content: Mapped[str] = mapped_column(Text, nullable=False)


class GraphChangeEvent(Base):
    """append-only 변경 이력. before/after JSONB."""

    __tablename__ = "graph_change_event"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    change_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="AI")
    before: Mapped[dict | None] = mapped_column(JSONB_or_JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB_or_JSON, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB_or_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class OutboxEvent(Base):
    """범용 outbox (전용 outbox·command 테이블 만들지 않는다). 스프링 연동은 M4."""

    __tablename__ = "outbox_event"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PUBLISHING', 'PUBLISHED', 'DEAD')",
            name="ck_outbox_event_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_outbox_event_attempt_count",
        ),
        CheckConstraint(
            "max_attempts >= 1",
            name="ck_outbox_event_max_attempts",
        ),
        CheckConstraint(
            "(status = 'PUBLISHING' AND claim_token IS NOT NULL) OR "
            "(status <> 'PUBLISHING' AND claim_token IS NULL)",
            name="ck_outbox_event_claim_owner",
        ),
        Index("ix_outbox_event_claimable", "status", "available_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v2.2")
    payload: Mapped[dict] = mapped_column(JSONB_or_JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    # --- publisher operational state (0008) ---
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnalysisJob(Base):
    """Durable work item for the asynchronous analysis stage.

    Initial-review completion enqueues one row per created UNATTACHED Node and
    returns 202 immediately; the Analysis Worker claims rows out of band. The
    row survives process restarts, which a FastAPI BackgroundTask would not.
    """

    __tablename__ = "analysis_job"
    __table_args__ = (
        # One live job per Node: re-enqueueing an already-queued Node reuses the
        # row instead of racing a second analysis for the same source.
        UniqueConstraint("node_id", name="uq_analysis_job_node"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_analysis_job_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_analysis_job_attempt"),
        CheckConstraint("max_attempts >= 1", name="ck_analysis_job_max_attempts"),
        Index("ix_analysis_job_claimable", "status", "available_at"),
        Index("ix_analysis_job_project_meeting", "project_id", "external_meeting_id"),
        ForeignKeyConstraint(
            ["project_id", "node_id"],
            ["node.project_id", "node.id"],
            name="fk_analysis_job_node_project",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_meeting_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("node.id", name="fk_analysis_job_node", ondelete="CASCADE"),
        nullable=False,
    )
    node_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class Category(Base):
    """설정 기반 카테고리 reference 테이블. config/categories.json 을 마이그레이션이 시딩.
    값 교체 = config 수정 + 재시딩 마이그레이션 1개 (reseed_categories)."""

    __tablename__ = "category"
    value: Mapped[str] = mapped_column(String(64), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="cat-v1")
