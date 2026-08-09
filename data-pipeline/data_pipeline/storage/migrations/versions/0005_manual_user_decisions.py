"""allow merge history for manual decisions without analysis artifacts

Revision ID: 0005_manual_user_decisions
Revises: 0004_runtime_pipeline
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_manual_user_decisions"
down_revision = "0004_runtime_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A user may make a final MERGE before a Run/Candidate exists, or after the
    # model was skipped/failed. The merge lineage is still mandatory, while
    # model provenance is optional and remains linked when supplied.
    with op.batch_alter_table("node_merge_history") as batch_op:
        batch_op.alter_column(
            "analysis_run_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
        batch_op.alter_column(
            "candidate_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )


def downgrade() -> None:
    connection = op.get_bind()
    missing_provenance = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM node_merge_history "
            "WHERE analysis_run_id IS NULL OR candidate_id IS NULL"
        )
    ).scalar_one()
    if missing_provenance:
        raise RuntimeError(
            "cannot downgrade manual user decisions while merge history "
            "contains rows without analysis provenance"
        )
    with op.batch_alter_table("node_merge_history") as batch_op:
        batch_op.alter_column(
            "candidate_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        batch_op.alter_column(
            "analysis_run_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
