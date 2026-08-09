"""drop the Node lifecycle_status domain and widen the embedding contract version

Revision ID: 0007_drop_lifecycle_status
Revises: 0006_automatic_node_merge
Create Date: 2026-08-03

Two unrelated-looking changes ship together because both are schema-level
prerequisites for the same policy update.

1. The team decided Node progress state is not a product feature. Rather than
   keeping an unused nullable column and dead branches, the columns and the
   per-type CHECK constraint are dropped outright.

2. ``node_embedding.embedding_version`` was ``varchar(16)``, which cannot hold
   the agreed contract name ``node-embedding-v2-no-category`` (29 characters).
   SQLite does not enforce declared widths, so a too-long value passes the
   SQLite suite and then fails every PostgreSQL insert. The column is part of
   the primary key, so it is widened rather than replaced.

Dropping columns is not reversible without data loss. ``downgrade`` restores
the columns and the constraint so the lineage stays runnable, but it cannot
restore the values that were dropped; it backfills type-appropriate defaults.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_drop_lifecycle_status"
down_revision = "0006_automatic_node_merge"
branch_labels = None
depends_on = None

_EMBEDDING_VERSION_WIDTH = 64
_PREVIOUS_EMBEDDING_VERSION_WIDTH = 16

#: Restored by downgrade only; the product no longer reads these values.
_LEGACY_DEFAULT_BY_TYPE = {
    "DECISION": "ACTIVE",
    "ACTION": "TODO",
    "ISSUE": "OPEN",
}

_LIFECYCLE_CHECK = (
    "(node_type = 'DECISION' "
    "AND lifecycle_status IN ('ACTIVE', 'SUPERSEDED')) OR "
    "(node_type = 'ACTION' "
    "AND lifecycle_status IN "
    "('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')) OR "
    "(node_type = 'ISSUE' "
    "AND lifecycle_status IN ('OPEN', 'RESOLVED'))"
)


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _set_sqlite_foreign_keys(*, enabled: bool) -> None:
    """Toggle SQLite FK enforcement outside Alembic's transaction.

    SQLite batch mode implements DROP COLUMN by copying a table and dropping
    the original. With foreign keys enabled, that DROP can cascade into tables
    that reference ``node`` even though its replacement preserves every row.
    PostgreSQL alters the tables in place and never uses this workaround.
    """

    if not _is_sqlite():
        return
    value = "ON" if enabled else "OFF"
    with op.get_context().autocommit_block():
        op.get_bind().exec_driver_sql(f"PRAGMA foreign_keys={value}")


def _upgrade_schema() -> None:
    # SQLite cannot drop a CHECK constraint in place; batch mode recreates the
    # table without it. On PostgreSQL the constraint is dropped directly.
    with op.batch_alter_table("node") as batch:
        if not _is_sqlite():
            batch.drop_constraint("ck_node_lifecycle_by_type", type_="check")
        batch.drop_column("lifecycle_status")

    with op.batch_alter_table("node_revision") as batch:
        batch.drop_column("lifecycle_status")

    with op.batch_alter_table("node_candidate") as batch:
        batch.drop_column("reviewed_lifecycle_status")
        batch.drop_column("suggested_lifecycle_status")

    with op.batch_alter_table("node_embedding") as batch:
        batch.alter_column(
            "embedding_version",
            existing_type=sa.String(length=_PREVIOUS_EMBEDDING_VERSION_WIDTH),
            type_=sa.String(length=_EMBEDDING_VERSION_WIDTH),
            existing_nullable=False,
        )


def upgrade() -> None:
    sqlite = _is_sqlite()
    if sqlite:
        _set_sqlite_foreign_keys(enabled=False)
    try:
        _upgrade_schema()
    finally:
        if sqlite:
            _set_sqlite_foreign_keys(enabled=True)


def _downgrade_schema() -> None:
    with op.batch_alter_table("node_embedding") as batch:
        batch.alter_column(
            "embedding_version",
            existing_type=sa.String(length=_EMBEDDING_VERSION_WIDTH),
            type_=sa.String(length=_PREVIOUS_EMBEDDING_VERSION_WIDTH),
            existing_nullable=False,
        )

    with op.batch_alter_table("node_candidate") as batch:
        batch.add_column(
            sa.Column("suggested_lifecycle_status", sa.String(length=16), nullable=True)
        )
        batch.add_column(
            sa.Column("reviewed_lifecycle_status", sa.String(length=16), nullable=True)
        )

    # The dropped values are gone. Re-add as nullable, backfill a
    # type-appropriate default, then restore NOT NULL so the lineage stays
    # runnable without inventing per-row history.
    for table in ("node", "node_revision"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("lifecycle_status", sa.String(length=16), nullable=True)
            )
        for node_type, default in _LEGACY_DEFAULT_BY_TYPE.items():
            op.execute(
                sa.text(
                    f"UPDATE {table} SET lifecycle_status = :default "  # noqa: S608
                    "WHERE node_type = :node_type"
                ).bindparams(default=default, node_type=node_type)
            )
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "lifecycle_status",
                existing_type=sa.String(length=16),
                nullable=False,
            )

    if not _is_sqlite():
        op.create_check_constraint(
            "ck_node_lifecycle_by_type", "node", sa.text(_LIFECYCLE_CHECK)
        )


def downgrade() -> None:
    sqlite = _is_sqlite()
    if sqlite:
        _set_sqlite_foreign_keys(enabled=False)
    try:
        _downgrade_schema()
    finally:
        if sqlite:
            _set_sqlite_foreign_keys(enabled=True)
