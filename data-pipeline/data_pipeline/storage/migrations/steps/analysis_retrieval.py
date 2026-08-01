"""Schema step: add the durable Retrieval stage outcome."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    op.add_column(
        "node_analysis_run",
        sa.Column(
            "retrieval_status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "node_analysis_run",
        sa.Column("retrieval_result_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "node_analysis_run",
        sa.Column(
            "retrieval_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    if _is_sqlite():
        with op.batch_alter_table(
            "node_analysis_run",
            recreate="always",
        ) as batch_op:
            batch_op.create_check_constraint(
                "ck_analysis_run_retrieval_status",
                "retrieval_status IN ('PENDING', 'COMPLETED', 'FAILED')",
            )
            batch_op.create_check_constraint(
                "ck_analysis_run_retrieval_count_non_negative",
                "retrieval_result_count IS NULL "
                "OR retrieval_result_count >= 0",
            )
    else:
        op.create_check_constraint(
            "ck_analysis_run_retrieval_status",
            "node_analysis_run",
            "retrieval_status IN ('PENDING', 'COMPLETED', 'FAILED')",
        )
        op.create_check_constraint(
            "ck_analysis_run_retrieval_count_non_negative",
            "node_analysis_run",
            "retrieval_result_count IS NULL "
            "OR retrieval_result_count >= 0",
        )


def downgrade() -> None:
    if _is_sqlite():
        with op.batch_alter_table(
            "node_analysis_run",
            recreate="always",
        ) as batch_op:
            batch_op.drop_constraint(
                "ck_analysis_run_retrieval_count_non_negative",
                type_="check",
            )
            batch_op.drop_constraint(
                "ck_analysis_run_retrieval_status",
                type_="check",
            )
    else:
        op.drop_constraint(
            "ck_analysis_run_retrieval_count_non_negative",
            "node_analysis_run",
            type_="check",
        )
        op.drop_constraint(
            "ck_analysis_run_retrieval_status",
            "node_analysis_run",
            type_="check",
        )
    op.drop_column("node_analysis_run", "retrieval_completed_at")
    op.drop_column("node_analysis_run", "retrieval_result_count")
    op.drop_column("node_analysis_run", "retrieval_status")
