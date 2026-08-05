"""add graph version, soft-delete actor, and analysis completion barrier

Revision ID: 0009_graph_event_contract_v1
Revises: 0008_meeting_summary
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0009_graph_event_contract_v1"
down_revision = "0008_meeting_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("node", sa.Column("deleted_by", sa.String(length=128), nullable=True))
    op.create_table(
        "project_graph_state",
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "graph_version >= 0",
            name="ck_project_graph_version_nonnegative",
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "analysis_delivery_state",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("required_graph_version", sa.Integer(), nullable=True),
        sa.Column("required_summary_version", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
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
            "status IN ('PROCESSING', 'SUCCEEDED', 'FAILED')",
            name="ck_analysis_delivery_status",
        ),
        sa.CheckConstraint(
            "required_graph_version IS NULL OR required_graph_version >= 1",
            name="ck_analysis_delivery_graph_version_positive",
        ),
        sa.CheckConstraint(
            "required_summary_version IS NULL OR required_summary_version >= 1",
            name="ck_analysis_delivery_summary_version_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "external_meeting_id",
            name="uq_analysis_delivery_project_meeting",
        ),
    )


def downgrade() -> None:
    op.drop_table("analysis_delivery_state")
    op.drop_table("project_graph_state")
    op.drop_column("node", "deleted_by")
