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
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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


class Node(Base):
    __tablename__ = "node"
    __table_args__ = (
        UniqueConstraint("source_candidate_id", name="uq_node_source_candidate"),
        CheckConstraint("version >= 1", name="ck_node_version_positive"),
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
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    evidence: Mapped[list["NodeEvidence"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class NodeEmbedding(Base):
    """R4′: 버전별 임베딩 분리. PK(node_id, embedding_version) — 모델 교체 시 신규 버전 전량
    재색인 후 검색기 스왑(신구 병행 조회). MVP 는 text-embedding-3-small/1536/v1 고정."""

    __tablename__ = "node_embedding"
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
    """D1″: 하드 게이트(evidence 대조)의 전제. sequence_no 로 회의 내 순서를 고정한다."""

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


class NodeEvidence(Base):
    """D1″: quote_start/quote_end 는 서버가 세그먼트 원문에서 역산한 char 오프셋(규칙 4)."""

    __tablename__ = "node_evidence"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("node.id", name="fk_evidence_node", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_meeting_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    node: Mapped[Node] = relationship(back_populates="evidence")


class NodeCandidate(Base):
    """LLM generation 결과를 사용자 승인 전까지 보존하는 PROPOSED 후보."""

    __tablename__ = "node_candidate"
    __table_args__ = (
        UniqueConstraint("request_id", "source_item_id", name="uq_candidate_request_item"),
        UniqueConstraint("confirmed_node_id", name="uq_candidate_confirmed_node"),
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
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v2.2")
    payload: Mapped[dict] = mapped_column(JSONB_or_JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Category(Base):
    """설정 기반 카테고리 reference 테이블. config/categories.json 을 마이그레이션이 시딩.
    값 교체 = config 수정 + 재시딩 마이그레이션 1개 (reseed_categories)."""

    __tablename__ = "category"
    value: Mapped[str] = mapped_column(String(64), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="cat-v1")
