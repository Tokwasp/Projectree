"""add immutable meeting summary and Java handoff outbox support

Revision ID: 0008_meeting_summary
Revises: 0007_drop_lifecycle_status
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from data_pipeline.storage.types import JSONB_or_JSON

revision = "0008_meeting_summary"
down_revision = "0007_drop_lifecycle_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meeting_summary",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("summary_version", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("structured_summary", JSONB_or_JSON, nullable=False),
        sa.Column("status", sa.String(length=16), server_default="READY", nullable=False),
        sa.Column("generator_name", sa.String(length=64), nullable=False),
        sa.Column("generator_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "summary_version >= 1",
            name="ck_meeting_summary_version_positive",
        ),
        sa.CheckConstraint("status = 'READY'", name="ck_meeting_summary_status"),
        sa.ForeignKeyConstraint(
            ["project_id", "external_meeting_id"],
            ["meeting.project_id", "meeting.external_meeting_id"],
            name="fk_meeting_summary_meeting_project",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "external_meeting_id",
            "summary_version",
            name="uq_meeting_summary_version",
        ),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_meeting_summary_project_id",
        ),
    )
    op.create_index(
        "ix_meeting_summary_project_meeting",
        "meeting_summary",
        ["project_id", "external_meeting_id", "summary_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meeting_summary_project_meeting",
        table_name="meeting_summary",
    )
    op.drop_table("meeting_summary")
