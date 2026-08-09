"""explicit Step 4A.1 baseline schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-29

This baseline is intentionally self-contained.  It does not import ORM models
or live metadata, so later model changes cannot rewrite migration history.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


class _PGVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dimension})"


JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
VECTOR_VALUE = sa.JSON().with_variant(_PGVector(1536), "postgresql")


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "category",
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), server_default="cat-v1", nullable=False),
        sa.PrimaryKeyConstraint("value"),
    )

    op.create_table(
        "meeting",
        _uuid_pk(),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="RECEIVED", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "external_meeting_id", name="uq_meeting_project_external"
        ),
    )

    op.create_table(
        "request",
        _uuid_pk(),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("external_request_id", sa.String(length=128), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=32), server_default="NODE_GENERATION", nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash_version", sa.String(length=32), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="PROCESSING", nullable=False),
        sa.Column("lineage", JSON_VALUE, nullable=True),
        sa.Column("usage", JSON_VALUE, nullable=True),
        sa.Column("raw_extraction", JSON_VALUE, nullable=True),
        sa.Column("raw_judgment", JSON_VALUE, nullable=True),
        sa.Column("warnings", JSON_VALUE, nullable=True),
        sa.Column("failure_stage", sa.String(length=16), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN "
            "('PROCESSING', 'REVIEW_PENDING', 'REVIEW_COMPLETED', 'FAILED', 'COMPLETED')",
            name="ck_request_status",
        ),
        sa.CheckConstraint(
            "failure_stage IS NULL OR "
            "failure_stage IN ('EXTRACTION', 'JUDGMENT', 'PERSISTENCE')",
            name="ck_request_failure_stage",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "external_meeting_id", "input_hash",
            name="uq_request_generation_input",
        ),
    )
    op.create_index("ix_request_status", "request", ["status"], unique=False)

    op.create_table(
        "node",
        _uuid_pk(),
        sa.Column("source_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("source_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("source_item_id", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("graph_state", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("lifecycle_status", sa.String(length=16), nullable=False),
        sa.Column("due_date", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_node_version_positive"),
        sa.ForeignKeyConstraint(["category"], ["category.value"], name="fk_node_category"),
        sa.ForeignKeyConstraint(["parent_id"], ["node.id"], name="fk_node_parent"),
        *(
            [
                sa.ForeignKeyConstraint(
                    ["source_candidate_id"],
                    ["node_candidate.id"],
                    name="fk_node_source_candidate",
                )
            ]
            if op.get_bind().dialect.name == "sqlite"
            else []
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_candidate_id", name="uq_node_source_candidate"),
    )

    op.create_table(
        "node_embedding",
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_version", sa.String(length=16), server_default="v1", nullable=False),
        sa.Column(
            "embedding_model",
            sa.String(length=64),
            server_default="text-embedding-3-small",
            nullable=False,
        ),
        sa.Column("dimension", sa.Integer(), server_default=sa.text("1536"), nullable=False),
        sa.Column("embedded_text_hash", sa.String(length=64), nullable=True),
        sa.Column("embedding", VECTOR_VALUE, nullable=True),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["node_id"], ["node.id"], name="fk_embedding_node", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("node_id", "embedding_version"),
    )

    op.create_table(
        "transcript_segment",
        _uuid_pk(),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("speaker_label", sa.String(length=64), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "external_meeting_id", "segment_id", name="uq_segment_source"
        ),
        sa.UniqueConstraint(
            "project_id", "external_meeting_id", "sequence_no", name="uq_segment_sequence"
        ),
    )

    op.create_table(
        "node_evidence",
        _uuid_pk(),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=True),
        sa.Column("quote_end", sa.Integer(), nullable=True),
        sa.Column("evidence_type", sa.String(length=24), nullable=True),
        sa.Column("source_meeting_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["node_id"], ["node.id"], name="fk_evidence_node", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "node_candidate",
        _uuid_pk(),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("source_item_id", sa.String(length=64), nullable=False),
        sa.Column("raw_item", JSON_VALUE, nullable=False),
        sa.Column("raw_judgment", JSON_VALUE, nullable=True),
        sa.Column("suggested_node_type", sa.String(length=16), nullable=False),
        sa.Column("suggested_category", sa.String(length=64), nullable=True),
        sa.Column("suggested_title", sa.Text(), nullable=False),
        sa.Column("suggested_content", sa.Text(), nullable=False),
        sa.Column("suggested_disposition", sa.String(length=32), nullable=False),
        sa.Column("suggested_reason", sa.Text(), nullable=True),
        sa.Column("suggested_parent_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("suggested_parent_node_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_node_type", sa.String(length=16), nullable=True),
        sa.Column("reviewed_category", sa.String(length=64), nullable=True),
        sa.Column("reviewed_title", sa.Text(), nullable=True),
        sa.Column("reviewed_content", sa.Text(), nullable=True),
        sa.Column("reviewed_disposition", sa.String(length=32), nullable=True),
        sa.Column("reviewed_reason", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_parent_mode",
            sa.String(length=16),
            server_default="INHERIT",
            nullable=False,
        ),
        sa.Column("reviewed_parent_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_parent_node_id", sa.Uuid(), nullable=True),
        sa.Column("review_status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("confirmed_node_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_candidate_version_positive"),
        sa.CheckConstraint(
            "NOT (suggested_parent_candidate_id IS NOT NULL "
            "AND suggested_parent_node_id IS NOT NULL)",
            name="ck_candidate_suggested_parent_exclusive",
        ),
        sa.CheckConstraint(
            "NOT (reviewed_parent_candidate_id IS NOT NULL "
            "AND reviewed_parent_node_id IS NOT NULL)",
            name="ck_candidate_reviewed_parent_exclusive",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_candidate_review_status",
        ),
        sa.CheckConstraint(
            "suggested_node_type IN ('DECISION', 'ACTION', 'ISSUE', 'UNKNOWN')",
            name="ck_candidate_suggested_node_type",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_node_id"], ["node.id"], name="fk_candidate_confirmed_node"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["request.id"], name="fk_candidate_request", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_parent_candidate_id"], ["node_candidate.id"],
            name="fk_candidate_reviewed_parent_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_parent_node_id"], ["node.id"], name="fk_candidate_reviewed_parent_node"
        ),
        sa.ForeignKeyConstraint(
            ["suggested_parent_candidate_id"], ["node_candidate.id"],
            name="fk_candidate_suggested_parent_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_parent_node_id"], ["node.id"], name="fk_candidate_suggested_parent_node"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "source_item_id", name="uq_candidate_request_item"),
        sa.UniqueConstraint("confirmed_node_id", name="uq_candidate_confirmed_node"),
    )
    op.create_index(
        "ix_candidate_review_status", "node_candidate", ["review_status"], unique=False
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_node_source_candidate",
            "node",
            "node_candidate",
            ["source_candidate_id"],
            ["id"],
        )

    op.create_table(
        "node_candidate_evidence",
        _uuid_pk(),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=True),
        sa.Column("quote_end", sa.Integer(), nullable=True),
        sa.Column("evidence_type", sa.String(length=24), nullable=True),
        sa.Column("source_meeting_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["node_candidate.id"],
            name="fk_candidate_evidence_candidate", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "candidate_review_event",
        _uuid_pk(),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("before_json", JSON_VALUE, nullable=False),
        sa.Column("after_json", JSON_VALUE, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('EDIT', 'APPROVE', 'REJECT')",
            name="ck_candidate_review_event_action",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["node_candidate.id"],
            name="fk_candidate_review_event_candidate",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["request.id"],
            name="fk_candidate_review_event_request",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_review_event_candidate",
        "candidate_review_event",
        ["candidate_id"],
        unique=False,
    )

    op.create_table(
        "relation",
        _uuid_pk(),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("from_node_id", sa.Uuid(), nullable=False),
        sa.Column("to_node_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PROPOSED", nullable=False),
        sa.Column("from_content_hash", sa.String(length=64), nullable=True),
        sa.Column("to_content_hash", sa.String(length=64), nullable=True),
        sa.Column("merge_rule_version", sa.String(length=32), nullable=True),
        sa.Column("actor_type", sa.String(length=16), server_default="AI", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["from_node_id"], ["node.id"], name="fk_relation_from"),
        sa.ForeignKeyConstraint(["to_node_id"], ["node.id"], name="fk_relation_to"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "from_node_id", "to_node_id", "relation_type", name="uq_relation"
        ),
    )

    op.create_table(
        "graph_change_event",
        _uuid_pk(),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("node_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.String(length=64), nullable=True),
        sa.Column("change_type", sa.String(length=24), nullable=False),
        sa.Column("actor_type", sa.String(length=16), server_default="AI", nullable=False),
        sa.Column("before", JSON_VALUE, nullable=True),
        sa.Column("after", JSON_VALUE, nullable=True),
        sa.Column("detail", JSON_VALUE, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "outbox_event",
        _uuid_pk(),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=16), server_default="v2.2", nullable=False),
        sa.Column("payload", JSON_VALUE, nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("outbox_event")
    op.drop_table("graph_change_event")
    op.drop_table("relation")
    op.drop_index(
        "ix_candidate_review_event_candidate",
        table_name="candidate_review_event",
    )
    op.drop_table("candidate_review_event")
    op.drop_table("node_candidate_evidence")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "fk_node_source_candidate",
            "node",
            type_="foreignkey",
        )
    op.drop_index("ix_candidate_review_status", table_name="node_candidate")
    op.drop_table("node_candidate")
    op.drop_table("node_evidence")
    op.drop_table("transcript_segment")
    op.drop_table("node_embedding")
    op.drop_table("node")
    op.drop_index("ix_request_status", table_name="request")
    op.drop_table("request")
    op.drop_table("meeting")
    op.drop_table("category")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP EXTENSION IF EXISTS vector")
