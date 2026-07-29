"""seed the immutable baseline category set

Revision ID: 0002_seed_categories
Revises: 0001_initial
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_seed_categories"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_VALUES = ["PLANNING", "DESIGN", "FRONTEND", "BACKEND", "AI", "INFRA", "ETC"]
_SCHEMA_VERSION = "cat-v1"


def upgrade() -> None:
    category = sa.table(
        "category",
        sa.column("value", sa.String(length=64)),
        sa.column("position", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("schema_version", sa.String(length=32)),
    )
    op.bulk_insert(
        category,
        [
            {
                "value": value,
                "position": position,
                "is_active": True,
                "schema_version": _SCHEMA_VERSION,
            }
            for position, value in enumerate(_VALUES)
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM category"))
