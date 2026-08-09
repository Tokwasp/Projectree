"""add command/recording join, independent tasks, and graph snapshot artifacts

Revision ID: 0010_meeting_analysis_join_v3
Revises: 0009_graph_event_contract_v1
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from data_pipeline.storage.types import JSONB_or_JSON


revision = "0010_meeting_analysis_join_v3"
down_revision = "0009_graph_event_contract_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recording_ready_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("room_name", sa.String(length=128), nullable=False),
        sa.Column("egress_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("member_id", sa.String(length=128), nullable=True),
        sa.Column("recording_bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("ended_at_raw", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(room_name)) > 0", name="ck_recording_ready_room"),
        sa.CheckConstraint("kind = 'MIXED'", name="ck_recording_ready_kind"),
        sa.CheckConstraint(
            "status IN ('WAITING_FOR_COMMAND', 'READY', 'CLAIMED', "
            "'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_recording_ready_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("egress_id", name="uq_recording_ready_egress"),
        sa.UniqueConstraint(
            "recording_bucket",
            "object_key",
            name="uq_recording_ready_object",
        ),
    )
    op.create_index(
        "ix_recording_ready_join",
        "recording_ready_event",
        ["project_id", "room_name", "status"],
    )

    op.create_table(
        "meeting_analysis_command",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("meeting_id", sa.String(length=128), nullable=False),
        sa.Column("room_name", sa.String(length=128), nullable=False),
        sa.Column("generate_summary", sa.Boolean(), nullable=False),
        sa.Column("generate_nodes", sa.Boolean(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(room_name)) > 0", name="ck_analysis_command_room"),
        sa.CheckConstraint("length(payload_hash) = 64", name="ck_analysis_command_hash"),
        sa.CheckConstraint(
            "status IN ('WAITING_FOR_RECORDING', 'READY', 'CLAIMED', "
            "'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_command_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", name="uq_meeting_analysis_command_id"),
        sa.UniqueConstraint(
            "project_id",
            "meeting_id",
            name="uq_meeting_analysis_command_project_meeting",
        ),
        sa.UniqueConstraint(
            "project_id",
            "command_id",
            name="uq_meeting_analysis_command_project_id",
        ),
    )
    op.create_index(
        "ix_meeting_analysis_command_join",
        "meeting_analysis_command",
        ["project_id", "room_name", "status"],
    )

    op.create_table(
        "meeting_analysis_task",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "task_type IN ('SUMMARY', 'NODES')",
            name="ck_meeting_analysis_task_type",
        ),
        sa.CheckConstraint(
            "status IN ('WAITING_INPUT', 'READY', 'PROCESSING', "
            "'SUCCEEDED', 'FAILED', 'SKIPPED')",
            name="ck_meeting_analysis_task_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_meeting_analysis_task_attempt"),
        sa.CheckConstraint("max_attempts = 3", name="ck_meeting_analysis_task_max_attempts"),
        sa.CheckConstraint(
            "(status = 'PROCESSING' AND claim_token IS NOT NULL) OR "
            "(status <> 'PROCESSING' AND claim_token IS NULL)",
            name="ck_meeting_analysis_task_claim",
        ),
        sa.ForeignKeyConstraint(
            ["command_id"],
            ["meeting_analysis_command.command_id"],
            name="fk_meeting_analysis_task_command",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "command_id",
            "task_type",
            name="uq_meeting_analysis_task_type",
        ),
    )
    op.create_index(
        "ix_meeting_analysis_task_claimable",
        "meeting_analysis_task",
        ["status", "available_at"],
    )

    op.create_table(
        "graph_snapshot_artifact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("meeting_id", sa.String(length=128), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("graph_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("payload_json", JSONB_or_JSON, nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("graph_version >= 1", name="ck_graph_snapshot_version"),
        sa.CheckConstraint("snapshot_schema_version = 1", name="ck_graph_snapshot_schema"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_graph_snapshot_size"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_graph_snapshot_sha256"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'UPLOADED', 'FAILED')",
            name="ck_graph_snapshot_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "command_id"],
            [
                "meeting_analysis_command.project_id",
                "meeting_analysis_command.command_id",
            ],
            name="fk_graph_snapshot_command_project",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "graph_version",
            name="uq_graph_snapshot_project_version",
        ),
        sa.UniqueConstraint(
            "command_id",
            "graph_version",
            name="uq_graph_snapshot_command_version",
        ),
    )


def downgrade() -> None:
    op.drop_table("graph_snapshot_artifact")
    op.drop_index(
        "ix_meeting_analysis_task_claimable",
        table_name="meeting_analysis_task",
    )
    op.drop_table("meeting_analysis_task")
    op.drop_index(
        "ix_meeting_analysis_command_join",
        table_name="meeting_analysis_command",
    )
    op.drop_table("meeting_analysis_command")
    op.drop_index("ix_recording_ready_join", table_name="recording_ready_event")
    op.drop_table("recording_ready_event")
