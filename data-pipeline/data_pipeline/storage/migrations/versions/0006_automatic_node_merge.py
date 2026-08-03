"""add automatic graph generation, revision evidence, and logical merge lineage

Revision ID: 0006_automatic_node_merge
Revises: 0005_manual_user_decisions
Create Date: 2026-08-02

The migration is intentionally additive. Existing Node/NodeEvidence and
NodeMergeHistory rows remain available while honest legacy snapshots are
linked into the new revision/evidence/merge-operation model. Missing legacy
evidence is never fabricated.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping

import sqlalchemy as sa
from alembic import op

from data_pipeline.storage.types import JSONB_or_JSON

revision = "0006_automatic_node_merge"
down_revision = "0005_manual_user_decisions"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _uuid_value() -> uuid.UUID | str:
    value = uuid.uuid4()
    return value if _dialect_name() == "postgresql" else value.hex


def _stable_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _has_constraint(table_name: str, constraint_name: str, kind: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if kind == "check":
        constraints = inspector.get_check_constraints(table_name)
    elif kind == "unique":
        constraints = inspector.get_unique_constraints(table_name)
    elif kind == "foreignkey":
        constraints = inspector.get_foreign_keys(table_name)
    else:  # pragma: no cover - internal migration programming error
        raise ValueError(f"unsupported constraint kind: {kind}")
    return any(item.get("name") == constraint_name for item in constraints)


def _create_generation_run() -> None:
    op.create_table(
        "generation_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=False),
        sa.Column("recording_hash", sa.String(length=64), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("external_request_id", sa.String(length=128), nullable=True),
        sa.Column("source_request_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="RECEIVED",
            nullable=False,
        ),
        sa.Column("warnings", JSONB_or_JSON, nullable=True),
        sa.Column("result_summary", JSONB_or_JSON, nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ("
            "'RECEIVED', 'EXTRACTING', 'DECISION_ANALYZING', "
            "'DEPENDENT_ANALYZING', 'VALIDATING', 'APPLYING', "
            "'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED'"
            ")",
            name="ck_generation_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["source_request_id"],
            ["request.id"],
            name="fk_generation_run_request",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "external_meeting_id",
            "recording_hash",
            "pipeline_version",
            name="uq_generation_run_input",
        ),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_generation_run_project_id",
        ),
    )
    op.create_index(
        "ix_generation_run_project_meeting",
        "generation_run",
        ["project_id", "external_meeting_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_run_status",
        "generation_run",
        ["status"],
        unique=False,
    )


def _extend_node() -> None:
    columns = [
        sa.Column("current_revision_id", sa.Uuid(), nullable=True),
        sa.Column(
            "origin_type",
            sa.String(length=24),
            server_default="LLM_GENERATED",
            nullable=False,
        ),
        sa.Column(
            "last_actor_type",
            sa.String(length=16),
            server_default="SYSTEM",
            nullable=False,
        ),
        sa.Column(
            "consistency_status",
            sa.String(length=24),
            server_default="NORMAL",
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]
    if _dialect_name() == "sqlite":
        # Recreating node would cascade-delete existing analysis rows in
        # SQLite. Production constraints live in PostgreSQL; SQLite keeps the
        # long-standing service-validation policy used by earlier revisions.
        for column in columns:
            op.add_column("node", column)
        op.create_index(
            "ix_node_current_revision_id",
            "node",
            ["current_revision_id"],
            unique=False,
        )
        return
    with op.batch_alter_table("node") as batch_op:
        if _has_constraint("node", "ck_node_graph_state", "check"):
            batch_op.drop_constraint("ck_node_graph_state", type_="check")
        for column in columns:
            batch_op.add_column(column)
        batch_op.create_check_constraint(
            "ck_node_graph_state",
            "graph_state IN ("
            "'ACTIVE', 'UNATTACHED', 'EXCLUDED', 'MERGED', 'ARCHIVED', 'DELETED'"
            ")",
        )
        batch_op.create_check_constraint(
            "ck_node_origin_type",
            "origin_type IN ('LLM_GENERATED', 'USER_CREATED', 'LEGACY')",
        )
        batch_op.create_check_constraint(
            "ck_node_last_actor_type",
            "last_actor_type IN ('SYSTEM', 'USER', 'LEGACY')",
        )
        batch_op.create_check_constraint(
            "ck_node_consistency_status",
            "consistency_status IN ('NORMAL', 'NEEDS_ATTENTION')",
        )
        batch_op.create_check_constraint(
            "ck_node_deleted_shape",
            "(graph_state = 'DELETED' AND deleted_at IS NOT NULL) OR "
            "(graph_state <> 'DELETED' AND deleted_at IS NULL)",
        )
        batch_op.create_index(
            "ix_node_current_revision_id",
            ["current_revision_id"],
            unique=False,
        )


def _create_revision_and_evidence() -> None:
    with op.batch_alter_table("transcript_segment") as batch_op:
        batch_op.create_unique_constraint(
            "uq_segment_project_id",
            ["project_id", "id"],
        )

    revision_foreign_keys = (
        [
            sa.ForeignKeyConstraint(
                ["project_id", "node_id"],
                ["node.project_id", "node.id"],
                name="fk_node_revision_node_project",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["project_id", "generation_run_id"],
                ["generation_run.project_id", "generation_run.id"],
                name="fk_node_revision_generation_project",
            ),
        ]
        if _dialect_name() == "postgresql"
        else [
            sa.ForeignKeyConstraint(
                ["node_id"],
                ["node.id"],
                name="fk_node_revision_node_project",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["generation_run_id"],
                ["generation_run.id"],
                name="fk_node_revision_generation_project",
            ),
        ]
    )
    op.create_table(
        "node_revision",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=16), nullable=False),
        sa.Column("due_date", sa.String(length=32), nullable=True),
        sa.Column("created_by_type", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.String(length=128), nullable=True),
        sa.Column("generation_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "requires_evidence",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "legacy_imported",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_node_revision_version_positive",
        ),
        sa.CheckConstraint(
            "created_by_type IN ('SYSTEM', 'USER', 'LEGACY')",
            name="ck_node_revision_created_by_type",
        ),
        *revision_foreign_keys,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "node_id",
            "version",
            name="uq_node_revision_version",
        ),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_node_revision_project_id",
        ),
    )
    op.create_index(
        "ix_node_revision_node_created",
        "node_revision",
        ["node_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("external_meeting_id", sa.String(length=128), nullable=True),
        sa.Column("transcript_segment_id", sa.Uuid(), nullable=True),
        sa.Column("source_segment_id", sa.String(length=64), nullable=True),
        sa.Column("speaker_label", sa.String(length=64), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("quote_start", sa.Integer(), nullable=True),
        sa.Column("quote_end", sa.Integer(), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("immutable_hash", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=True),
        sa.Column(
            "legacy_imported",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('TRANSCRIPT', 'USER_ASSERTION', 'LEGACY')",
            name="ck_evidence_source_type",
        ),
        sa.CheckConstraint(
            "(source_type = 'TRANSCRIPT' AND transcript_segment_id IS NOT NULL "
            "AND quote_start IS NOT NULL AND quote_end IS NOT NULL "
            "AND quote_start >= 0 AND quote_end > quote_start) OR "
            "(source_type IN ('USER_ASSERTION', 'LEGACY'))",
            name="ck_evidence_source_shape",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "external_meeting_id"],
            ["meeting.project_id", "meeting.external_meeting_id"],
            name="fk_evidence_meeting_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "transcript_segment_id"],
            ["transcript_segment.project_id", "transcript_segment.id"],
            name="fk_evidence_segment_project",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_evidence_project_id",
        ),
        sa.UniqueConstraint(
            "project_id",
            "immutable_hash",
            name="uq_evidence_project_hash",
        ),
    )
    op.create_index(
        "ix_evidence_segment",
        "evidence",
        ["transcript_segment_id"],
        unique=False,
    )

    op.create_table(
        "node_revision_evidence",
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("node_revision_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column(
            "support_type",
            sa.String(length=24),
            server_default="SUPPORTING",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "support_type IN ('PRIMARY', 'SUPPORTING', 'USER_ASSERTION', 'LEGACY')",
            name="ck_node_revision_evidence_support_type",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "evidence_id"],
            ["evidence.project_id", "evidence.id"],
            name="fk_revision_evidence_evidence_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "node_revision_id"],
            ["node_revision.project_id", "node_revision.id"],
            name="fk_revision_evidence_revision_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "node_revision_id",
            "evidence_id",
        ),
    )


def _create_merge_operation() -> None:
    merge_foreign_keys = (
        [
            sa.ForeignKeyConstraint(
                ["project_id", "generation_run_id"],
                ["generation_run.project_id", "generation_run.id"],
                name="fk_merge_operation_generation_project",
            ),
            sa.ForeignKeyConstraint(
                ["project_id", "resolved_target_node_id"],
                ["node.project_id", "node.id"],
                name="fk_merge_operation_resolved_target_project",
            ),
            sa.ForeignKeyConstraint(
                ["project_id", "source_node_id"],
                ["node.project_id", "node.id"],
                name="fk_merge_operation_source_project",
            ),
            sa.ForeignKeyConstraint(
                ["project_id", "target_node_id"],
                ["node.project_id", "node.id"],
                name="fk_merge_operation_target_project",
            ),
        ]
        if _dialect_name() == "postgresql"
        else [
            sa.ForeignKeyConstraint(
                ["generation_run_id"],
                ["generation_run.id"],
                name="fk_merge_operation_generation_project",
            ),
            sa.ForeignKeyConstraint(
                ["resolved_target_node_id"],
                ["node.id"],
                name="fk_merge_operation_resolved_target_project",
            ),
            sa.ForeignKeyConstraint(
                ["source_node_id"],
                ["node.id"],
                name="fk_merge_operation_source_project",
            ),
            sa.ForeignKeyConstraint(
                ["target_node_id"],
                ["node.id"],
                name="fk_merge_operation_target_project",
            ),
        ]
    )
    op.create_table(
        "merge_operation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=False),
        sa.Column("resolved_target_node_id", sa.Uuid(), nullable=False),
        sa.Column("source_original_graph_state", sa.String(length=16), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("generation_run_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("identity_basis", JSONB_or_JSON, nullable=True),
        sa.Column("conflicts_checked", JSONB_or_JSON, nullable=True),
        sa.Column("model_confidence", sa.Float(), nullable=True),
        sa.Column("retrieval_rank", sa.Integer(), nullable=True),
        sa.Column("retrieval_score", sa.Float(), nullable=True),
        sa.Column("second_retrieval_score", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="APPLIED",
            nullable=False,
        ),
        sa.Column(
            "is_legacy",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_by", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "actor_type IN ('SYSTEM', 'USER', 'LEGACY')",
            name="ck_merge_operation_actor_type",
        ),
        sa.CheckConstraint(
            "status IN ('APPLIED', 'REVERTED')",
            name="ck_merge_operation_status",
        ),
        sa.CheckConstraint(
            "source_node_id <> target_node_id",
            name="ck_merge_operation_not_self",
        ),
        sa.CheckConstraint(
            "source_version >= 1 AND target_version >= 1",
            name="ck_merge_operation_versions_positive",
        ),
        *merge_foreign_keys,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_merge_operation_project_id",
        ),
    )
    op.create_index(
        "ix_merge_operation_source_status",
        "merge_operation",
        ["source_node_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_merge_operation_target_status",
        "merge_operation",
        ["target_node_id", "status"],
        unique=False,
    )
    op.create_table(
        "merge_operation_dependency",
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("depends_on_operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation_id <> depends_on_operation_id",
            name="ck_merge_dependency_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "depends_on_operation_id"],
            ["merge_operation.project_id", "merge_operation.id"],
            name="fk_merge_dependency_parent_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "operation_id"],
            ["merge_operation.project_id", "merge_operation.id"],
            name="fk_merge_dependency_operation_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "operation_id",
            "depends_on_operation_id",
        ),
    )

    with op.batch_alter_table("relation") as batch_op:
        batch_op.add_column(sa.Column("generation_run_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("caused_by_merge_operation_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "valid_from",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_relation_generation_run",
            "generation_run",
            ["generation_run_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_relation_merge_operation",
            "merge_operation",
            ["caused_by_merge_operation_id"],
            ["id"],
        )


def _backfill_revisions_and_evidence() -> None:
    connection = op.get_bind()
    nodes = connection.execute(
        sa.text(
            "SELECT id, project_id, source_meeting_id, node_type, category, "
            "title, content, lifecycle_status, due_date, version, created_at "
            "FROM node"
        )
    ).mappings()
    revision_by_node: dict[object, object] = {}
    project_by_node: dict[object, str] = {}
    meeting_by_node: dict[object, str] = {}
    for node in nodes:
        revision_id = _uuid_value()
        revision_by_node[node["id"]] = revision_id
        project_by_node[node["id"]] = node["project_id"]
        meeting_by_node[node["id"]] = node["source_meeting_id"]
        connection.execute(
            sa.text(
                "INSERT INTO node_revision ("
                "id, project_id, node_id, version, title, content, node_type, "
                "category, lifecycle_status, due_date, created_by_type, "
                "requires_evidence, legacy_imported, created_at"
                ") VALUES ("
                ":id, :project_id, :node_id, :version, :title, :content, "
                ":node_type, :category, :lifecycle_status, :due_date, 'LEGACY', "
                ":requires_evidence, :legacy_imported, :created_at"
                ")"
            ),
            {
                "id": revision_id,
                "project_id": node["project_id"],
                "node_id": node["id"],
                "version": node["version"],
                "title": node["title"],
                "content": node["content"],
                "node_type": node["node_type"],
                "category": node["category"],
                "lifecycle_status": node["lifecycle_status"],
                "due_date": node["due_date"],
                "requires_evidence": False,
                "legacy_imported": True,
                "created_at": node["created_at"],
            },
        )
        connection.execute(
            sa.text(
                "UPDATE node SET current_revision_id = :revision_id, "
                "origin_type = 'LEGACY', last_actor_type = 'LEGACY' "
                "WHERE id = :node_id AND project_id = :project_id"
            ),
            {
                "revision_id": revision_id,
                "node_id": node["id"],
                "project_id": node["project_id"],
            },
        )

    evidence_rows = connection.execute(
        sa.text(
            "SELECT id, node_id, evidence_key, segment_id, quote, quote_start, "
            "quote_end, evidence_type, source_meeting_id FROM node_evidence"
        )
    ).mappings()
    evidence_by_hash: dict[tuple[str, str], object] = {}
    for legacy in evidence_rows:
        revision_id = revision_by_node.get(legacy["node_id"])
        project_id = project_by_node.get(legacy["node_id"])
        if revision_id is None or project_id is None:
            continue
        meeting_id = legacy["source_meeting_id"] or meeting_by_node[legacy["node_id"]]
        segment = connection.execute(
            sa.text(
                "SELECT id, speaker_label, start_ms, end_ms, text, "
                "normalized_text, normalization_metadata "
                "FROM transcript_segment WHERE project_id = :project_id "
                "AND external_meeting_id = :meeting_id AND segment_id = :segment_id"
            ),
            {
                "project_id": project_id,
                "meeting_id": meeting_id,
                "segment_id": legacy["segment_id"],
            },
        ).mappings().first()
        quote_start = legacy["quote_start"]
        quote_end = legacy["quote_end"]
        normalized_text = (
            (segment["normalized_text"] or segment["text"]) if segment else None
        )
        exact_span = (
            segment is not None
            and isinstance(quote_start, int)
            and isinstance(quote_end, int)
            and 0 <= quote_start < quote_end <= len(normalized_text)
            and normalized_text[quote_start:quote_end] == legacy["quote"]
        )
        source_type = "TRANSCRIPT" if exact_span else "LEGACY"
        quoted_text = (
            normalized_text[quote_start:quote_end] if exact_span else legacy["quote"]
        )
        payload = {
            "project_id": project_id,
            "meeting_id": meeting_id,
            "segment_id": legacy["segment_id"],
            "quote_start": quote_start if exact_span else None,
            "quote_end": quote_end if exact_span else None,
            "quoted_text": quoted_text,
            "source_type": source_type,
        }
        immutable_hash = _stable_hash(payload)
        cache_key = (project_id, immutable_hash)
        evidence_id = evidence_by_hash.get(cache_key)
        if evidence_id is None:
            existing_id = connection.execute(
                sa.text(
                    "SELECT id FROM evidence WHERE project_id = :project_id "
                    "AND immutable_hash = :immutable_hash"
                ),
                {
                    "project_id": project_id,
                    "immutable_hash": immutable_hash,
                },
            ).scalar_one_or_none()
            evidence_id = existing_id or _uuid_value()
            evidence_by_hash[cache_key] = evidence_id
            if existing_id is None:
                normalization_version = None
                if segment and segment["normalization_metadata"]:
                    metadata = segment["normalization_metadata"]
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except ValueError:
                            metadata = {}
                    if isinstance(metadata, Mapping):
                        normalization_version = str(
                            metadata.get("dictionary_version")
                            or metadata.get("version")
                            or ""
                        ) or None
                connection.execute(
                    sa.text(
                        "INSERT INTO evidence ("
                        "id, project_id, external_meeting_id, "
                        "transcript_segment_id, source_segment_id, speaker_label, "
                        "start_ms, end_ms, quote_start, quote_end, quoted_text, "
                        "source_type, immutable_hash, normalization_version, "
                        "legacy_imported"
                        ") VALUES ("
                        ":id, :project_id, :meeting_id, :transcript_segment_id, "
                        ":source_segment_id, :speaker_label, :start_ms, :end_ms, "
                        ":quote_start, :quote_end, :quoted_text, :source_type, "
                        ":immutable_hash, :normalization_version, :legacy_imported"
                        ")"
                    ),
                    {
                        "id": evidence_id,
                        "project_id": project_id,
                        "meeting_id": meeting_id if segment else None,
                        "transcript_segment_id": segment["id"] if segment and exact_span else None,
                        "source_segment_id": legacy["segment_id"],
                        "speaker_label": segment["speaker_label"] if segment else None,
                        "start_ms": segment["start_ms"] if segment else None,
                        "end_ms": segment["end_ms"] if segment else None,
                        "quote_start": quote_start if exact_span else None,
                        "quote_end": quote_end if exact_span else None,
                        "quoted_text": quoted_text,
                        "source_type": source_type,
                        "immutable_hash": immutable_hash,
                        "normalization_version": normalization_version,
                        "legacy_imported": True,
                    },
                )
        connection.execute(
            sa.text(
                "INSERT INTO node_revision_evidence ("
                "project_id, node_revision_id, evidence_id, support_type"
                ") VALUES ("
                ":project_id, :revision_id, :evidence_id, 'LEGACY'"
                ")"
            ),
            {
                "project_id": project_id,
                "revision_id": revision_id,
                "evidence_id": evidence_id,
            },
        )

    if _dialect_name() == "postgresql":
        with op.batch_alter_table("node") as batch_op:
            batch_op.create_foreign_key(
                "fk_node_current_revision_project",
                "node_revision",
                ["project_id", "current_revision_id"],
                ["project_id", "id"],
            )


def _resolve_legacy_target(
    source_id: object,
    target_id: object,
    merge_target_by_source: Mapping[object, object],
) -> object:
    visited = {source_id}
    current = target_id
    while current in merge_target_by_source:
        if current in visited:
            return target_id
        visited.add(current)
        current = merge_target_by_source[current]
    return current


def _backfill_merge_operations() -> None:
    connection = op.get_bind()
    histories = list(
        connection.execute(
            sa.text(
                "SELECT id, project_id, source_node_id, target_node_id, "
                "approved_by, approved_at, source_version, target_version "
                "FROM node_merge_history ORDER BY approved_at, id"
            )
        ).mappings()
    )
    target_by_source = {
        row["source_node_id"]: row["target_node_id"] for row in histories
    }
    operation_by_source: dict[object, object] = {}
    for row in histories:
        operation_id = _uuid_value()
        operation_by_source[row["source_node_id"]] = operation_id
        resolved_target = _resolve_legacy_target(
            row["source_node_id"],
            row["target_node_id"],
            target_by_source,
        )
        connection.execute(
            sa.text(
                "INSERT INTO merge_operation ("
                "id, project_id, source_node_id, source_version, target_node_id, "
                "target_version, resolved_target_node_id, "
                "source_original_graph_state, actor_type, actor_id, reason_code, "
                "reason_text, status, is_legacy, applied_at"
                ") VALUES ("
                ":id, :project_id, :source_node_id, :source_version, "
                ":target_node_id, :target_version, :resolved_target_node_id, "
                "'UNATTACHED', 'LEGACY', :actor_id, 'LEGACY_IMPORT', "
                "'Imported from node_merge_history without invented model metadata', "
                "'APPLIED', :is_legacy, :applied_at"
                ")"
            ),
            {
                "id": operation_id,
                "project_id": row["project_id"],
                "source_node_id": row["source_node_id"],
                "source_version": row["source_version"],
                "target_node_id": row["target_node_id"],
                "target_version": row["target_version"],
                "resolved_target_node_id": resolved_target,
                "actor_id": row["approved_by"],
                "is_legacy": True,
                "applied_at": row["approved_at"],
            },
        )

    # If A -> B exists before B -> C, the later B -> C operation depends on
    # A -> B. This is enough to enforce reverse-order unmerge for legacy chains.
    for row in histories:
        operation_id = operation_by_source[row["source_node_id"]]
        for earlier in histories:
            if earlier["target_node_id"] != row["source_node_id"]:
                continue
            dependency_id = operation_by_source[earlier["source_node_id"]]
            connection.execute(
                sa.text(
                    "INSERT INTO merge_operation_dependency ("
                    "project_id, operation_id, depends_on_operation_id"
                    ") VALUES (:project_id, :operation_id, :dependency_id)"
                ),
                {
                    "project_id": row["project_id"],
                    "operation_id": operation_id,
                    "dependency_id": dependency_id,
                },
            )


def _install_postgresql_evidence_constraint() -> None:
    if _dialect_name() != "postgresql":
        return
    op.execute(
        """
        CREATE FUNCTION enforce_node_revision_evidence()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.requires_evidence
               AND NOT EXISTS (
                   SELECT 1 FROM node_revision_evidence
                   WHERE node_revision_id = NEW.id
                     AND project_id = NEW.project_id
               )
            THEN
                RAISE EXCEPTION
                    'node revision % requires at least one evidence row', NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_node_revision_requires_evidence
        AFTER INSERT OR UPDATE OF requires_evidence
        ON node_revision
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_node_revision_evidence()
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_revision_evidence_delete()
        RETURNS trigger AS $$
        DECLARE revision_row node_revision%ROWTYPE;
        BEGIN
            SELECT * INTO revision_row
            FROM node_revision
            WHERE id = OLD.node_revision_id
              AND project_id = OLD.project_id;
            IF FOUND
               AND revision_row.requires_evidence
               AND NOT EXISTS (
                   SELECT 1 FROM node_revision_evidence
                   WHERE node_revision_id = OLD.node_revision_id
                     AND project_id = OLD.project_id
               )
            THEN
                RAISE EXCEPTION
                    'node revision % requires at least one evidence row',
                    OLD.node_revision_id;
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_revision_evidence_delete
        AFTER DELETE ON node_revision_evidence
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_revision_evidence_delete()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_immutable_graph_row_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_evidence_immutable
        BEFORE UPDATE OR DELETE ON evidence
        FOR EACH ROW
        EXECUTE FUNCTION prevent_immutable_graph_row_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_node_revision_immutable
        BEFORE UPDATE OR DELETE ON node_revision
        FOR EACH ROW
        EXECUTE FUNCTION prevent_immutable_graph_row_mutation()
        """
    )


def upgrade() -> None:
    _create_generation_run()
    _extend_node()
    _create_revision_and_evidence()
    _create_merge_operation()
    _backfill_revisions_and_evidence()
    _backfill_merge_operations()
    _install_postgresql_evidence_constraint()


def downgrade() -> None:
    if _dialect_name() == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_node_revision_immutable "
            "ON node_revision"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_evidence_immutable ON evidence"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS prevent_immutable_graph_row_mutation()"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_revision_evidence_delete "
            "ON node_revision_evidence"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS enforce_revision_evidence_delete()"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_node_revision_requires_evidence "
            "ON node_revision"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS enforce_node_revision_evidence()"
        )

    if _has_constraint(
        "node",
        "fk_node_current_revision_project",
        "foreignkey",
    ):
        with op.batch_alter_table("node") as batch_op:
            batch_op.drop_constraint(
                "fk_node_current_revision_project",
                type_="foreignkey",
            )

    with op.batch_alter_table("relation") as batch_op:
        batch_op.drop_constraint("fk_relation_merge_operation", type_="foreignkey")
        batch_op.drop_constraint("fk_relation_generation_run", type_="foreignkey")
        batch_op.drop_column("valid_to")
        batch_op.drop_column("valid_from")
        batch_op.drop_column("caused_by_merge_operation_id")
        batch_op.drop_column("generation_run_id")

    op.drop_table("merge_operation_dependency")
    op.drop_index(
        "ix_merge_operation_target_status",
        table_name="merge_operation",
    )
    op.drop_index(
        "ix_merge_operation_source_status",
        table_name="merge_operation",
    )
    op.drop_table("merge_operation")
    op.drop_table("node_revision_evidence")
    op.drop_index("ix_evidence_segment", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_node_revision_node_created", table_name="node_revision")
    op.drop_table("node_revision")

    with op.batch_alter_table("transcript_segment") as batch_op:
        batch_op.drop_constraint("uq_segment_project_id", type_="unique")

    if _dialect_name() == "sqlite":
        op.drop_index("ix_node_current_revision_id", table_name="node")
        for column_name in (
            "deleted_at",
            "consistency_status",
            "last_actor_type",
            "origin_type",
            "current_revision_id",
        ):
            op.drop_column("node", column_name)
    else:
        with op.batch_alter_table("node") as batch_op:
            batch_op.drop_index("ix_node_current_revision_id")
            batch_op.drop_constraint("ck_node_deleted_shape", type_="check")
            batch_op.drop_constraint("ck_node_consistency_status", type_="check")
            batch_op.drop_constraint("ck_node_last_actor_type", type_="check")
            batch_op.drop_constraint("ck_node_origin_type", type_="check")
            batch_op.drop_constraint("ck_node_graph_state", type_="check")
            batch_op.create_check_constraint(
                "ck_node_graph_state",
                "graph_state IN ("
                "'ACTIVE', 'UNATTACHED', 'EXCLUDED', 'MERGED', 'ARCHIVED'"
                ")",
            )
            batch_op.drop_column("deleted_at")
            batch_op.drop_column("consistency_status")
            batch_op.drop_column("last_actor_type")
            batch_op.drop_column("origin_type")
            batch_op.drop_column("current_revision_id")

    op.drop_index("ix_generation_run_status", table_name="generation_run")
    op.drop_index(
        "ix_generation_run_project_meeting",
        table_name="generation_run",
    )
    op.drop_table("generation_run")
