"""carry the ACTION lifecycle state through the Candidate stage

Before this migration every Node created from a Candidate received
``default_lifecycle_status(node_type)``, so every ACTION became TODO even when
the meeting clearly said the work was already done. These two nullable columns
let the LLM suggestion and the reviewer override survive to Node creation.

Additive only: both columns are nullable with no server default, so existing
rows keep meaning "no lifecycle opinion recorded", which the service layer
resolves with the pre-existing default. No backfill is required and no existing
column or constraint is modified.

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    op.add_column(
        "node_candidate",
        sa.Column("suggested_lifecycle_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "node_candidate",
        sa.Column("reviewed_lifecycle_status", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("node_candidate", "reviewed_lifecycle_status")
    op.drop_column("node_candidate", "suggested_lifecycle_status")
