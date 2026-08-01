"""add durable ownership to outbox publisher claims

The existing ``PUBLISHING`` status is a lease marker, but status alone cannot
distinguish the worker whose expired lease was reclaimed from the new owner.
This revision adds an opaque claim token used by compare-and-set completion.

An in-flight legacy ``PUBLISHING`` row has no safe owner to backfill.  Rather
than inventing ownership or silently replaying it, the migration fails with an
operator-facing message.  PENDING/PUBLISHED/DEAD rows upgrade without changes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def validate_upgrade() -> None:
    count = op.get_bind().execute(
        sa.text(
            "SELECT COUNT(*) FROM outbox_event "
            "WHERE status = 'PUBLISHING'"
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            "outbox_event contains "
            f"{count} legacy PUBLISHING row(s) without a claim owner; "
            "confirm whether each delivery happened, then explicitly move "
            "the row to PENDING, PUBLISHED, or DEAD before upgrading"
        )


def upgrade() -> None:
    validate_upgrade()
    op.add_column(
        "outbox_event",
        sa.Column("claim_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "outbox_event",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # PostgreSQL is canonical.  SQLite migrations deliberately omit these
    # additive checks because ALTER CHECK requires a destructive table rebuild.
    if not _is_sqlite():
        op.create_check_constraint(
            "ck_outbox_event_status",
            "outbox_event",
            "status IN ('PENDING', 'PUBLISHING', 'PUBLISHED', 'DEAD')",
        )
        op.create_check_constraint(
            "ck_outbox_event_attempt_count",
            "outbox_event",
            "attempt_count >= 0",
        )
        op.create_check_constraint(
            "ck_outbox_event_max_attempts",
            "outbox_event",
            "max_attempts >= 1",
        )
        op.create_check_constraint(
            "ck_outbox_event_claim_owner",
            "outbox_event",
            "(status = 'PUBLISHING' AND claim_token IS NOT NULL) OR "
            "(status <> 'PUBLISHING' AND claim_token IS NULL)",
        )


def downgrade() -> None:
    if not _is_sqlite():
        op.drop_constraint(
            "ck_outbox_event_claim_owner",
            "outbox_event",
            type_="check",
        )
        op.drop_constraint(
            "ck_outbox_event_max_attempts",
            "outbox_event",
            type_="check",
        )
        op.drop_constraint(
            "ck_outbox_event_attempt_count",
            "outbox_event",
            type_="check",
        )
        op.drop_constraint(
            "ck_outbox_event_status",
            "outbox_event",
            type_="check",
        )
    op.drop_column("outbox_event", "claimed_at")
    op.drop_column("outbox_event", "claim_token")
