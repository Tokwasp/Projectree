"""Schema step: add durable S3 audio-upload idempotency."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    op.create_table(
        "audio_upload_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("object_identity", sa.String(length=1024), nullable=False),
        sa.Column("identity_kind", sa.String(length=16), nullable=False),
        sa.Column("version_id", sa.String(length=1024), nullable=True),
        sa.Column("etag", sa.String(length=256), nullable=True),
        sa.Column("object_size", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("upload_id", sa.String(length=128), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="PROCESSING",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("external_request_id", sa.String(length=128), nullable=True),
        sa.Column("pipeline_status", sa.String(length=32), nullable=True),
        sa.Column("pipeline_outcome", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column(
            "processing_started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
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
            "identity_kind IN ('VERSION_ID', 'ETAG')",
            name="ck_audio_upload_identity_kind",
        ),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_audio_upload_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 1",
            name="ck_audio_upload_attempt_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket",
            "object_key",
            "object_identity",
            name="uq_audio_upload_object_identity",
        ),
    )
    op.create_index(
        "ix_audio_upload_project_meeting",
        "audio_upload_event",
        ["project_id", "external_meeting_id"],
    )
    op.create_index(
        "ix_audio_upload_status",
        "audio_upload_event",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audio_upload_status",
        table_name="audio_upload_event",
    )
    op.drop_index(
        "ix_audio_upload_project_meeting",
        table_name="audio_upload_event",
    )
    op.drop_table("audio_upload_event")
