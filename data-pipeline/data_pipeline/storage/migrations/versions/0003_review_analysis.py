"""add normalization, review boundary, and analysis execution

Revision ID: 0003_review_analysis
Revises: 0002_seed_categories
Create Date: 2026-07-30

This revision squashes the uncommitted 0003-0007 development migrations.
It remains upgrade-safe from the committed 0002 schema, including legacy
TranscriptSegment and NodeEvidence backfills.
"""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_review_analysis"
down_revision = "0002_seed_categories"
branch_labels = None
depends_on = None

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
EVIDENCE_KEY_VERSION = "node-evidence-v1"
_ACTIVE_RUN_PREDICATE = "status IN ('PENDING', 'RUNNING')"

node_evidence = sa.table(
    "node_evidence",
    sa.column("id", sa.Uuid()),
    sa.column("node_id", sa.Uuid()),
    sa.column("evidence_key", sa.String(length=64)),
    sa.column("segment_id", sa.String(length=64)),
    sa.column("quote", sa.Text()),
    sa.column("quote_start", sa.Integer()),
    sa.column("quote_end", sa.Integer()),
    sa.column("evidence_type", sa.String(length=24)),
    sa.column("source_meeting_id", sa.String(length=128)),
)


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _evidence_key(row) -> str:
    canonical = json.dumps(
        [
            EVIDENCE_KEY_VERSION,
            row.source_meeting_id,
            row.segment_id,
            row.quote_start,
            row.quote_end,
            row.quote,
            row.evidence_type,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _backfill_evidence_keys() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            node_evidence.c.id,
            node_evidence.c.node_id,
            node_evidence.c.segment_id,
            node_evidence.c.quote,
            node_evidence.c.quote_start,
            node_evidence.c.quote_end,
            node_evidence.c.evidence_type,
            node_evidence.c.source_meeting_id,
        ).order_by(node_evidence.c.node_id, node_evidence.c.id)
    ).all()

    keys_by_row: list[tuple[object, str]] = []
    seen: set[tuple[object, str]] = set()
    duplicate_count = 0
    for row in rows:
        key = _evidence_key(row)
        identity = (row.node_id, key)
        if identity in seen:
            duplicate_count += 1
        else:
            seen.add(identity)
        keys_by_row.append((row.id, key))

    if duplicate_count:
        raise RuntimeError(
            "node_evidence contains "
            f"{duplicate_count} duplicate row(s) for the v1 evidence key"
        )

    for evidence_id, key in keys_by_row:
        connection.execute(
            node_evidence.update()
            .where(node_evidence.c.id == evidence_id)
            .values(evidence_key=key)
        )


def _add_normalized_transcript_columns() -> None:
    op.add_column(
        "transcript_segment",
        sa.Column("raw_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "transcript_segment",
        sa.Column("raw_text_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "transcript_segment",
        sa.Column("normalized_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "transcript_segment",
        sa.Column("normalization_metadata", JSON_VALUE, nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE transcript_segment "
            "SET raw_text = text, "
            "raw_text_hash = text_hash, "
            "normalized_text = text"
        )
    )


def _add_review_boundary_columns() -> None:
    op.add_column(
        "node",
        sa.Column("merged_into_node_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "node",
        sa.Column(
            "analysis_status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "node",
        sa.Column("analysis_input_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "node",
        sa.Column("initial_reviewed_by", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "node",
        sa.Column(
            "initial_reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "node",
        sa.Column("confirmed_by", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "node",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "node_candidate",
        sa.Column("initial_review_node_id", sa.Uuid(), nullable=True),
    )

    if not _is_sqlite():
        op.create_foreign_key(
            "fk_node_merged_into",
            "node",
            "node",
            ["merged_into_node_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_candidate_initial_review_node",
            "node_candidate",
            "node",
            ["initial_review_node_id"],
            ["id"],
        )
        op.create_check_constraint(
            "ck_node_analysis_status",
            "node",
            "analysis_status IN "
            "('PENDING', 'ANALYZING', 'ANALYZED', 'STALE', 'FAILED')",
        )

    op.create_index(
        "uq_candidate_initial_review_node",
        "node_candidate",
        ["initial_review_node_id"],
        unique=True,
    )
    op.create_index(
        "ix_node_merged_into_node_id",
        "node",
        ["merged_into_node_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            "UPDATE node_candidate "
            "SET initial_review_node_id = confirmed_node_id "
            "WHERE confirmed_node_id IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE node "
            "SET initial_reviewed_by = ("
            "SELECT reviewed_by FROM node_candidate "
            "WHERE node_candidate.id = node.source_candidate_id"
            "), initial_reviewed_at = ("
            "SELECT reviewed_at FROM node_candidate "
            "WHERE node_candidate.id = node.source_candidate_id"
            ") "
            "WHERE source_candidate_id IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE node "
            "SET confirmed_by = initial_reviewed_by, "
            "confirmed_at = initial_reviewed_at "
            "WHERE graph_state = 'ACTIVE'"
        )
    )


def _add_evidence_identity() -> None:
    op.add_column(
        "node_evidence",
        sa.Column("evidence_key", sa.String(length=64), nullable=True),
    )
    _backfill_evidence_keys()

    if _is_sqlite():
        with op.batch_alter_table(
            "node_evidence",
            recreate="always",
        ) as batch_op:
            batch_op.alter_column(
                "evidence_key",
                existing_type=sa.String(length=64),
                nullable=False,
            )
    else:
        op.alter_column(
            "node_evidence",
            "evidence_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )

    op.create_index(
        "uq_node_evidence_node_key",
        "node_evidence",
        ["node_id", "evidence_key"],
        unique=True,
    )


def _create_analysis_execution_tables() -> None:
    op.create_table(
        "node_analysis_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_version", sa.Integer(), nullable=False),
        sa.Column("analysis_input_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "analysis_input_hash_version",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "retrieval_config_version",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.String(length=64), nullable=True),
        sa.Column("embedding_version", sa.String(length=32), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN "
            "('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SUPERSEDED')",
            name="ck_analysis_run_status",
        ),
        sa.CheckConstraint(
            "source_node_version >= 1",
            name="ck_analysis_run_node_version_positive",
        ),
        sa.CheckConstraint(
            "attempt >= 1",
            name="ck_analysis_run_attempt_positive",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["node.id"],
            name="fk_analysis_run_source_node",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_node_id",
            "source_node_version",
            "analysis_input_hash",
            "attempt",
            name="uq_analysis_run_node_version_hash_attempt",
        ),
        sa.UniqueConstraint(
            "source_node_id",
            "id",
            name="uq_analysis_run_source_node_id",
        ),
    )
    op.create_index(
        "ix_analysis_run_node_hash_status",
        "node_analysis_run",
        ["source_node_id", "analysis_input_hash", "status"],
        unique=False,
    )
    if _is_sqlite():
        op.create_index(
            "uq_analysis_run_active_node_hash",
            "node_analysis_run",
            ["source_node_id", "analysis_input_hash"],
            unique=True,
            sqlite_where=sa.text(_ACTIVE_RUN_PREDICATE),
        )
    else:
        op.create_index(
            "uq_analysis_run_active_node_hash",
            "node_analysis_run",
            ["source_node_id", "analysis_input_hash"],
            unique=True,
            postgresql_where=sa.text(_ACTIVE_RUN_PREDICATE),
        )

    op.create_table(
        "retrieval_result",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_version", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rank >= 1",
            name="ck_retrieval_result_rank_positive",
        ),
        sa.CheckConstraint(
            "target_node_version >= 1",
            name="ck_retrieval_result_target_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["node_analysis_run.id"],
            name="fk_retrieval_result_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["node.id"],
            name="fk_retrieval_result_target_node",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id",
            "rank",
            name="uq_retrieval_result_run_rank",
        ),
        sa.UniqueConstraint(
            "analysis_run_id",
            "target_node_id",
            name="uq_retrieval_result_run_target",
        ),
    )
    op.create_index(
        "ix_retrieval_result_target_node",
        "retrieval_result",
        ["target_node_id"],
        unique=False,
    )

    op.add_column(
        "node",
        sa.Column("current_analysis_run_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_node_current_analysis_run_id",
        "node",
        ["current_analysis_run_id"],
        unique=False,
    )
    if not _is_sqlite():
        op.create_foreign_key(
            "fk_node_current_analysis_run",
            "node",
            "node_analysis_run",
            ["id", "current_analysis_run_id"],
            ["source_node_id", "id"],
        )


def upgrade() -> None:
    _add_normalized_transcript_columns()
    _add_review_boundary_columns()
    _add_evidence_identity()
    _create_analysis_execution_tables()


def downgrade() -> None:
    if not _is_sqlite():
        op.drop_constraint(
            "fk_node_current_analysis_run",
            "node",
            type_="foreignkey",
        )
    op.drop_index("ix_node_current_analysis_run_id", table_name="node")
    op.drop_column("node", "current_analysis_run_id")

    op.drop_index(
        "ix_retrieval_result_target_node",
        table_name="retrieval_result",
    )
    op.drop_table("retrieval_result")
    op.drop_index(
        "uq_analysis_run_active_node_hash",
        table_name="node_analysis_run",
    )
    op.drop_index(
        "ix_analysis_run_node_hash_status",
        table_name="node_analysis_run",
    )
    op.drop_table("node_analysis_run")

    op.drop_index(
        "uq_node_evidence_node_key",
        table_name="node_evidence",
    )
    op.drop_column("node_evidence", "evidence_key")

    op.drop_index(
        "uq_candidate_initial_review_node",
        table_name="node_candidate",
    )
    op.drop_index(
        "ix_node_merged_into_node_id",
        table_name="node",
    )
    if not _is_sqlite():
        op.drop_constraint(
            "ck_node_analysis_status",
            "node",
            type_="check",
        )
        op.drop_constraint(
            "fk_candidate_initial_review_node",
            "node_candidate",
            type_="foreignkey",
        )
        op.drop_constraint(
            "fk_node_merged_into",
            "node",
            type_="foreignkey",
        )

    op.drop_column("node_candidate", "initial_review_node_id")
    op.drop_column("node", "confirmed_at")
    op.drop_column("node", "confirmed_by")
    op.drop_column("node", "initial_reviewed_at")
    op.drop_column("node", "initial_reviewed_by")
    op.drop_column("node", "analysis_input_hash")
    op.drop_column("node", "analysis_status")
    op.drop_column("node", "merged_into_node_id")

    op.drop_column("transcript_segment", "normalization_metadata")
    op.drop_column("transcript_segment", "normalized_text")
    op.drop_column("transcript_segment", "raw_text_hash")
    op.drop_column("transcript_segment", "raw_text")
