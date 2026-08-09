"""durable analysis job queue and outbox publisher state

Two additive changes:

1. ``analysis_job`` — the asynchronous boundary for the analysis stage. Initial
   review completion enqueues rows and returns 202 instead of running embedding,
   Retrieval and the B model inside the HTTP request. Rows survive restarts.
2. ``outbox_event`` gains publisher bookkeeping (attempt_count, max_attempts,
   available_at, published_at, last_error) so a relay can retry with backoff.
   Existing rows default to attempt 0 and become immediately claimable.

No existing column is dropped or retyped and no earlier revision is rewritten.

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    op.create_table(
        "analysis_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("node_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="analysis_job_pkey"),
        sa.UniqueConstraint("node_id", name="uq_analysis_job_node"),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["node.id"],
            name="fk_analysis_job_node",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_analysis_job_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_analysis_job_attempt"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_analysis_job_max_attempts"),
    )
    op.create_index(
        "ix_analysis_job_claimable", "analysis_job", ["status", "available_at"]
    )
    op.create_index(
        "ix_analysis_job_project_meeting",
        "analysis_job",
        ["project_id", "external_meeting_id"],
    )

    op.add_column(
        "outbox_event",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "outbox_event",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="8"),
    )
    if _is_sqlite():
        # SQLite cannot add a non-null column with a non-constant default when
        # legacy rows exist. Add/backfill first, then rebuild this small table
        # so future inserts still receive CURRENT_TIMESTAMP.
        op.add_column(
            "outbox_event",
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        op.execute(
            sa.text(
                "UPDATE outbox_event SET available_at = CURRENT_TIMESTAMP "
                "WHERE available_at IS NULL"
            )
        )
        with op.batch_alter_table(
            "outbox_event",
            recreate="always",
        ) as batch_op:
            batch_op.alter_column(
                "available_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
    else:
        op.add_column(
            "outbox_event",
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
    op.add_column(
        "outbox_event",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("outbox_event", sa.Column("last_error", sa.Text(), nullable=True))
    op.create_index(
        "ix_outbox_event_claimable", "outbox_event", ["status", "available_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_event_claimable", table_name="outbox_event")
    op.drop_column("outbox_event", "last_error")
    op.drop_column("outbox_event", "published_at")
    op.drop_column("outbox_event", "available_at")
    op.drop_column("outbox_event", "max_attempts")
    op.drop_column("outbox_event", "attempt_count")
    op.drop_index("ix_analysis_job_project_meeting", table_name="analysis_job")
    op.drop_index("ix_analysis_job_claimable", table_name="analysis_job")
    op.drop_table("analysis_job")
