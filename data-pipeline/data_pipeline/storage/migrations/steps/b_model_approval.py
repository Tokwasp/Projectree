"""Schema step: add B-model results, final candidates, and merge lineage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    op.add_column(
        "node_analysis_run",
        sa.Column(
            "b_model_status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "node_analysis_run",
        sa.Column("b_model_skip_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "node_analysis_run",
        sa.Column("b_model_failure_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "node_analysis_run",
        sa.Column("b_model_failure_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "node_analysis_run",
        sa.Column(
            "b_model_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "node_analysis_run",
        sa.Column(
            "b_model_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    if not _is_sqlite():
        op.create_check_constraint(
            "ck_analysis_run_b_model_status",
            "node_analysis_run",
            "b_model_status IN "
            "('PENDING', 'RUNNING', 'SUCCEEDED', 'SKIPPED', 'FAILED')",
        )

    op.create_table(
        "b_model_result",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_version", sa.Integer(), nullable=False),
        sa.Column("recommendation", sa.String(length=16), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=True),
        sa.Column("target_node_version", sa.Integer(), nullable=True),
        sa.Column("relation_type", sa.String(length=16), nullable=True),
        sa.Column("suggested_title", sa.Text(), nullable=False),
        sa.Column("suggested_content", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", JSON_VALUE, nullable=False),
        sa.Column(
            "validation_status",
            sa.String(length=16),
            server_default="VALIDATED",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "recommendation IN ('CREATE_NEW', 'LINK', 'MERGE')",
            name="ck_b_model_result_recommendation",
        ),
        sa.CheckConstraint(
            "validation_status = 'VALIDATED'",
            name="ck_b_model_result_validation_status",
        ),
        sa.CheckConstraint(
            "source_node_version >= 1",
            name="ck_b_model_result_source_version_positive",
        ),
        sa.CheckConstraint(
            "target_node_version IS NULL OR target_node_version >= 1",
            name="ck_b_model_result_target_version_positive",
        ),
        sa.CheckConstraint(
            "(recommendation = 'CREATE_NEW' "
            "AND target_node_id IS NULL AND relation_type IS NULL) OR "
            "(recommendation = 'LINK' "
            "AND target_node_id IS NOT NULL "
            "AND relation_type IN ('ATTACHED_TO', 'RELATED_TO')) OR "
            "(recommendation = 'MERGE' "
            "AND target_node_id IS NOT NULL AND relation_type IS NULL)",
            name="ck_b_model_result_shape",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["node_analysis_run.id"],
            name="fk_b_model_result_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["node.id"],
            name="fk_b_model_result_source_node",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["node.id"],
            name="fk_b_model_result_target_node",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id",
            name="uq_b_model_result_analysis_run",
        ),
    )
    op.create_index(
        "ix_b_model_result_source_node",
        "b_model_result",
        ["source_node_id"],
    )
    op.create_index(
        "ix_b_model_result_target_node",
        "b_model_result",
        ["target_node_id"],
    )

    op.create_table(
        "analysis_candidate",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("b_model_result_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_version", sa.Integer(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=True),
        sa.Column("target_node_version", sa.Integer(), nullable=True),
        sa.Column("recommendation", sa.String(length=16), nullable=False),
        sa.Column("relation_type", sa.String(length=16), nullable=True),
        sa.Column("suggested_title", sa.Text(), nullable=False),
        sa.Column("suggested_content", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            "recommendation IN ('CREATE_NEW', 'LINK', 'MERGE')",
            name="ck_analysis_candidate_recommendation",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_analysis_candidate_status",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_analysis_candidate_version_positive",
        ),
        sa.CheckConstraint(
            "source_node_version >= 1",
            name="ck_analysis_candidate_source_version_positive",
        ),
        sa.CheckConstraint(
            "target_node_version IS NULL OR target_node_version >= 1",
            name="ck_analysis_candidate_target_version_positive",
        ),
        sa.CheckConstraint(
            "(recommendation = 'CREATE_NEW' "
            "AND target_node_id IS NULL AND relation_type IS NULL) OR "
            "(recommendation = 'LINK' "
            "AND target_node_id IS NOT NULL "
            "AND relation_type IN ('ATTACHED_TO', 'RELATED_TO')) OR "
            "(recommendation = 'MERGE' "
            "AND target_node_id IS NOT NULL AND relation_type IS NULL)",
            name="ck_analysis_candidate_shape",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["node_analysis_run.id"],
            name="fk_analysis_candidate_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["b_model_result_id"],
            ["b_model_result.id"],
            name="fk_analysis_candidate_b_model_result",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["node.id"],
            name="fk_analysis_candidate_source_node",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["node.id"],
            name="fk_analysis_candidate_target_node",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id",
            name="uq_analysis_candidate_run",
        ),
        sa.UniqueConstraint(
            "b_model_result_id",
            name="uq_analysis_candidate_b_model_result",
        ),
    )
    op.create_index(
        "ix_analysis_candidate_project_status",
        "analysis_candidate",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_analysis_candidate_source_node",
        "analysis_candidate",
        ["source_node_id"],
    )
    op.create_index(
        "ix_analysis_candidate_target_node",
        "analysis_candidate",
        ["target_node_id"],
    )

    op.create_table(
        "node_merge_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=False),
        sa.Column("merged_title", sa.Text(), nullable=False),
        sa.Column("merged_content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["node.id"],
            name="fk_merge_history_source",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["node.id"],
            name="fk_merge_history_target",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["node_analysis_run.id"],
            name="fk_merge_history_analysis_run",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["analysis_candidate.id"],
            name="fk_merge_history_candidate",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_node_id",
            name="uq_node_merge_history_source",
        ),
        sa.UniqueConstraint("candidate_id"),
    )
    op.create_index(
        "ix_node_merge_history_target",
        "node_merge_history",
        ["target_node_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_node_merge_history_target",
        table_name="node_merge_history",
    )
    op.drop_table("node_merge_history")
    op.drop_index(
        "ix_analysis_candidate_target_node",
        table_name="analysis_candidate",
    )
    op.drop_index(
        "ix_analysis_candidate_source_node",
        table_name="analysis_candidate",
    )
    op.drop_index(
        "ix_analysis_candidate_project_status",
        table_name="analysis_candidate",
    )
    op.drop_table("analysis_candidate")
    op.drop_index(
        "ix_b_model_result_target_node",
        table_name="b_model_result",
    )
    op.drop_index(
        "ix_b_model_result_source_node",
        table_name="b_model_result",
    )
    op.drop_table("b_model_result")
    if not _is_sqlite():
        op.drop_constraint(
            "ck_analysis_run_b_model_status",
            "node_analysis_run",
            type_="check",
        )
    op.drop_column("node_analysis_run", "b_model_completed_at")
    op.drop_column("node_analysis_run", "b_model_started_at")
    op.drop_column("node_analysis_run", "b_model_failure_message")
    op.drop_column("node_analysis_run", "b_model_failure_code")
    op.drop_column("node_analysis_run", "b_model_skip_reason")
    op.drop_column("node_analysis_run", "b_model_status")
