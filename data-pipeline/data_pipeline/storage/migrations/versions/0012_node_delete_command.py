"""admit Node logical delete commands into the shared command inbox

Revision ID: 0012_node_delete_command
Revises: 0011_node_content_update_command
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0012_node_delete_command"
down_revision = "0011_node_content_update_command"
branch_labels = None
depends_on = None


# Kept byte-identical to the ``ck_analysis_command_shape`` text in
# ``storage.models`` so a schema diff against the ORM stays quiet.
_SHAPE_WITH_DELETE = (
    "(command_type = 'MEETING_ANALYSIS_REQUESTED' AND "
    "meeting_id IS NOT NULL AND room_name IS NOT NULL AND "
    "length(trim(room_name)) > 0 AND generate_summary IS NOT NULL AND "
    "generate_nodes IS NOT NULL AND target_node_id IS NULL AND "
    "expected_node_version IS NULL AND expected_graph_version IS NULL AND "
    "requested_by_member_id IS NULL) OR "
    "(command_type = 'NODE_CONTENT_UPDATE_REQUESTED' AND "
    "meeting_id IS NULL AND room_name IS NULL AND "
    "generate_summary IS NULL AND generate_nodes IS NULL AND "
    "target_node_id IS NOT NULL AND expected_node_version IS NOT NULL AND "
    "expected_graph_version IS NULL AND "
    "requested_by_member_id IS NOT NULL) OR "
    "(command_type = 'NODE_DELETE_REQUESTED' AND "
    "meeting_id IS NULL AND room_name IS NULL AND "
    "generate_summary IS NULL AND generate_nodes IS NULL AND "
    "target_node_id IS NULL AND expected_node_version IS NULL AND "
    "expected_graph_version IS NOT NULL AND "
    "requested_by_member_id IS NOT NULL)"
)

# The 0011 text, restored verbatim on downgrade.
_SHAPE_WITHOUT_DELETE = (
    "(command_type = 'MEETING_ANALYSIS_REQUESTED' AND "
    "meeting_id IS NOT NULL AND room_name IS NOT NULL AND "
    "length(trim(room_name)) > 0 AND generate_summary IS NOT NULL AND "
    "generate_nodes IS NOT NULL AND target_node_id IS NULL AND "
    "expected_node_version IS NULL AND requested_by_member_id IS NULL) OR "
    "(command_type = 'NODE_CONTENT_UPDATE_REQUESTED' AND "
    "meeting_id IS NULL AND room_name IS NULL AND "
    "generate_summary IS NULL AND generate_nodes IS NULL AND "
    "target_node_id IS NOT NULL AND expected_node_version IS NOT NULL AND "
    "requested_by_member_id IS NOT NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table("meeting_analysis_command") as batch_op:
        batch_op.add_column(
            sa.Column("expected_graph_version", sa.Integer(), nullable=True)
        )
        batch_op.drop_constraint("ck_analysis_command_shape", type_="check")
        batch_op.drop_constraint("ck_analysis_command_type", type_="check")
        batch_op.create_check_constraint(
            "ck_analysis_command_type",
            "command_type IN ('MEETING_ANALYSIS_REQUESTED', "
            "'NODE_CONTENT_UPDATE_REQUESTED', 'NODE_DELETE_REQUESTED')",
        )
        batch_op.create_check_constraint(
            "ck_analysis_command_shape",
            _SHAPE_WITH_DELETE,
        )
        batch_op.create_check_constraint(
            "ck_analysis_command_graph_version_nonnegative",
            "expected_graph_version IS NULL OR expected_graph_version >= 0",
        )


def downgrade() -> None:
    connection = op.get_bind()
    delete_commands = connection.execute(
        sa.text(
            "SELECT count(*) FROM meeting_analysis_command "
            "WHERE command_type = 'NODE_DELETE_REQUESTED'"
        )
    ).scalar_one()
    if delete_commands:
        raise RuntimeError(
            "cannot downgrade while Node delete commands exist"
        )

    with op.batch_alter_table("meeting_analysis_command") as batch_op:
        batch_op.drop_constraint(
            "ck_analysis_command_graph_version_nonnegative", type_="check"
        )
        batch_op.drop_constraint("ck_analysis_command_shape", type_="check")
        batch_op.drop_constraint("ck_analysis_command_type", type_="check")
        batch_op.create_check_constraint(
            "ck_analysis_command_type",
            "command_type IN ('MEETING_ANALYSIS_REQUESTED', "
            "'NODE_CONTENT_UPDATE_REQUESTED')",
        )
        batch_op.create_check_constraint(
            "ck_analysis_command_shape",
            _SHAPE_WITHOUT_DELETE,
        )
        batch_op.drop_column("expected_graph_version")
