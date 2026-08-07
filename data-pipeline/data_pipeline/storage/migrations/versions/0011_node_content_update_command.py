"""generalize command inbox for canonical Node content updates

Revision ID: 0011_node_content_update_command
Revises: 0010_meeting_analysis_join_v3
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011_node_content_update_command"
down_revision = "0010_meeting_analysis_join_v3"
branch_labels = None
depends_on = None


_COMMAND_SHAPE = (
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
            sa.Column(
                "command_type",
                sa.String(length=48),
                server_default="MEETING_ANALYSIS_REQUESTED",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("target_node_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("expected_node_version", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("requested_by_member_id", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("failure_code", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(sa.Column("failure_message", sa.Text(), nullable=True))
        batch_op.alter_column("meeting_id", existing_type=sa.String(128), nullable=True)
        batch_op.alter_column("room_name", existing_type=sa.String(128), nullable=True)
        batch_op.alter_column("generate_summary", existing_type=sa.Boolean(), nullable=True)
        batch_op.alter_column("generate_nodes", existing_type=sa.Boolean(), nullable=True)
        batch_op.drop_constraint("ck_analysis_command_room", type_="check")
        batch_op.create_check_constraint(
            "ck_analysis_command_type",
            "command_type IN ('MEETING_ANALYSIS_REQUESTED', "
            "'NODE_CONTENT_UPDATE_REQUESTED')",
        )
        batch_op.create_check_constraint(
            "ck_analysis_command_shape",
            _COMMAND_SHAPE,
        )
        batch_op.create_check_constraint(
            "ck_analysis_command_node_version_positive",
            "expected_node_version IS NULL OR expected_node_version >= 1",
        )

    with op.batch_alter_table("graph_snapshot_artifact") as batch_op:
        batch_op.alter_column(
            "meeting_id",
            existing_type=sa.String(128),
            nullable=True,
        )


def downgrade() -> None:
    connection = op.get_bind()
    node_commands = connection.execute(
        sa.text(
            "SELECT count(*) FROM meeting_analysis_command "
            "WHERE command_type = 'NODE_CONTENT_UPDATE_REQUESTED'"
        )
    ).scalar_one()
    null_meeting_artifacts = connection.execute(
        sa.text(
            "SELECT count(*) FROM graph_snapshot_artifact WHERE meeting_id IS NULL"
        )
    ).scalar_one()
    if node_commands or null_meeting_artifacts:
        raise RuntimeError(
            "cannot downgrade while Node update commands or their snapshots exist"
        )

    with op.batch_alter_table("graph_snapshot_artifact") as batch_op:
        batch_op.alter_column(
            "meeting_id",
            existing_type=sa.String(128),
            nullable=False,
        )

    with op.batch_alter_table("meeting_analysis_command") as batch_op:
        batch_op.drop_constraint(
            "ck_analysis_command_node_version_positive", type_="check"
        )
        batch_op.drop_constraint("ck_analysis_command_shape", type_="check")
        batch_op.drop_constraint("ck_analysis_command_type", type_="check")
        batch_op.create_check_constraint(
            "ck_analysis_command_room",
            "length(trim(room_name)) > 0",
        )
        batch_op.alter_column("generate_nodes", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("generate_summary", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("room_name", existing_type=sa.String(128), nullable=False)
        batch_op.alter_column("meeting_id", existing_type=sa.String(128), nullable=False)
        batch_op.drop_column("failure_message")
        batch_op.drop_column("failure_code")
        batch_op.drop_column("requested_by_member_id")
        batch_op.drop_column("expected_node_version")
        batch_op.drop_column("target_node_id")
        batch_op.drop_column("command_type")
