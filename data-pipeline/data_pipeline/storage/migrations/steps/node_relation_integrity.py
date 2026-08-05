"""Schema step: harden Node, Relation, and Embedding invariants.

The service layer already validates these values.  PostgreSQL now rejects the
same invalid states when a bug, maintenance script, or direct SQL bypasses the
service.  Existing data is audited first; no row is repaired or deleted by this
migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


_VALIDATION_QUERIES = {
    "invalid Node type": (
        "SELECT COUNT(*) FROM node "
        "WHERE node_type NOT IN ('DECISION', 'ACTION', 'ISSUE')"
    ),
    "invalid Node graph state": (
        "SELECT COUNT(*) FROM node WHERE graph_state NOT IN "
        "('ACTIVE', 'UNATTACHED', 'EXCLUDED', 'MERGED', 'ARCHIVED')"
    ),
    "Node lifecycle/type mismatch": (
        "SELECT COUNT(*) FROM node WHERE NOT ("
        "(node_type = 'DECISION' "
        "AND lifecycle_status IN ('ACTIVE', 'SUPERSEDED')) OR "
        "(node_type = 'ACTION' AND lifecycle_status IN "
        "('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')) OR "
        "(node_type = 'ISSUE' "
        "AND lifecycle_status IN ('OPEN', 'RESOLVED')))"
    ),
    "invalid Node merge shape": (
        "SELECT COUNT(*) FROM node WHERE NOT ("
        "(graph_state = 'MERGED' AND merged_into_node_id IS NOT NULL) OR "
        "(graph_state <> 'MERGED' AND merged_into_node_id IS NULL))"
    ),
    "self-referencing Node parent": (
        "SELECT COUNT(*) FROM node WHERE parent_id = id"
    ),
    "self-referencing Node merge": (
        "SELECT COUNT(*) FROM node WHERE merged_into_node_id = id"
    ),
    "cross-project Node parent": (
        "SELECT COUNT(*) FROM node child JOIN node parent "
        "ON parent.id = child.parent_id "
        "WHERE child.project_id <> parent.project_id"
    ),
    "cross-project Node merge": (
        "SELECT COUNT(*) FROM node source JOIN node target "
        "ON target.id = source.merged_into_node_id "
        "WHERE source.project_id <> target.project_id"
    ),
    "invalid Relation type": (
        "SELECT COUNT(*) FROM relation WHERE relation_type NOT IN "
        "('ATTACHED_TO', 'RELATED_TO', 'SAME', 'REVERSES', "
        "'FOLLOWS', 'RESOLVED_BY')"
    ),
    "invalid Relation status": (
        "SELECT COUNT(*) FROM relation "
        "WHERE status NOT IN ('PROPOSED', 'CONFIRMED', 'REJECTED')"
    ),
    "self Relation": (
        "SELECT COUNT(*) FROM relation WHERE from_node_id = to_node_id"
    ),
    "cross-project Relation": (
        "SELECT COUNT(*) FROM relation r "
        "JOIN node source ON source.id = r.from_node_id "
        "JOIN node target ON target.id = r.to_node_id "
        "WHERE r.project_id <> source.project_id "
        "OR r.project_id <> target.project_id"
    ),
    "cross-project B-model result": (
        "SELECT COUNT(*) FROM b_model_result result "
        "JOIN node source ON source.id = result.source_node_id "
        "LEFT JOIN node target ON target.id = result.target_node_id "
        "WHERE result.project_id <> source.project_id "
        "OR (target.id IS NOT NULL "
        "AND result.project_id <> target.project_id)"
    ),
    "cross-project analysis candidate": (
        "SELECT COUNT(*) FROM analysis_candidate candidate "
        "JOIN node source ON source.id = candidate.source_node_id "
        "LEFT JOIN node target ON target.id = candidate.target_node_id "
        "WHERE candidate.project_id <> source.project_id "
        "OR (target.id IS NOT NULL "
        "AND candidate.project_id <> target.project_id)"
    ),
    "cross-project merge history": (
        "SELECT COUNT(*) FROM node_merge_history history "
        "JOIN node source ON source.id = history.source_node_id "
        "JOIN node target ON target.id = history.target_node_id "
        "WHERE history.project_id <> source.project_id "
        "OR history.project_id <> target.project_id"
    ),
    "cross-project analysis job": (
        "SELECT COUNT(*) FROM analysis_job job "
        "JOIN node ON node.id = job.node_id "
        "WHERE job.project_id <> node.project_id"
    ),
    "invalid Embedding status": (
        "SELECT COUNT(*) FROM node_embedding "
        "WHERE status NOT IN ('PENDING', 'READY', 'STALE', 'FAILED')"
    ),
    "invalid Embedding dimension": (
        "SELECT COUNT(*) FROM node_embedding WHERE dimension <> 1536"
    ),
}


def _audit_existing_data() -> None:
    connection = op.get_bind()
    violations = []
    for label, query in _VALIDATION_QUERIES.items():
        count = connection.execute(sa.text(query)).scalar_one()
        if count:
            violations.append(f"{label}: {count}")
    if violations:
        raise RuntimeError(
            "database integrity hardening found existing violations; "
            "no rows were changed: "
            + "; ".join(violations)
        )


def upgrade() -> None:
    _audit_existing_data()
    if _is_sqlite():
        # PostgreSQL is the canonical product database. Adding composite FKs
        # and CHECKs to SQLite requires rebuilding these central tables, which
        # would make the compatibility-test migration destructive.
        return

    op.create_unique_constraint(
        "uq_node_project_id",
        "node",
        ["project_id", "id"],
    )
    op.create_check_constraint(
        "ck_node_type",
        "node",
        "node_type IN ('DECISION', 'ACTION', 'ISSUE')",
    )
    op.create_check_constraint(
        "ck_node_graph_state",
        "node",
        "graph_state IN "
        "('ACTIVE', 'UNATTACHED', 'EXCLUDED', 'MERGED', 'ARCHIVED')",
    )
    op.create_check_constraint(
        "ck_node_lifecycle_by_type",
        "node",
        "(node_type = 'DECISION' "
        "AND lifecycle_status IN ('ACTIVE', 'SUPERSEDED')) OR "
        "(node_type = 'ACTION' AND lifecycle_status IN "
        "('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')) OR "
        "(node_type = 'ISSUE' "
        "AND lifecycle_status IN ('OPEN', 'RESOLVED'))",
    )
    op.create_check_constraint(
        "ck_node_merge_shape",
        "node",
        "(graph_state = 'MERGED' AND merged_into_node_id IS NOT NULL) OR "
        "(graph_state <> 'MERGED' AND merged_into_node_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_node_not_self_parent",
        "node",
        "parent_id IS NULL OR parent_id <> id",
    )
    op.create_check_constraint(
        "ck_node_not_self_merge",
        "node",
        "merged_into_node_id IS NULL OR merged_into_node_id <> id",
    )
    op.create_foreign_key(
        "fk_node_parent_project",
        "node",
        "node",
        ["project_id", "parent_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_node_merged_into_project",
        "node",
        "node",
        ["project_id", "merged_into_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_b_model_result_source_project",
        "b_model_result",
        "node",
        ["project_id", "source_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_b_model_result_target_project",
        "b_model_result",
        "node",
        ["project_id", "target_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_analysis_candidate_source_project",
        "analysis_candidate",
        "node",
        ["project_id", "source_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_analysis_candidate_target_project",
        "analysis_candidate",
        "node",
        ["project_id", "target_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_merge_history_source_project",
        "node_merge_history",
        "node",
        ["project_id", "source_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_merge_history_target_project",
        "node_merge_history",
        "node",
        ["project_id", "target_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_analysis_job_node_project",
        "analysis_job",
        "node",
        ["project_id", "node_id"],
        ["project_id", "id"],
    )

    op.create_check_constraint(
        "ck_relation_type",
        "relation",
        "relation_type IN "
        "('ATTACHED_TO', 'RELATED_TO', 'SAME', 'REVERSES', "
        "'FOLLOWS', 'RESOLVED_BY')",
    )
    op.create_check_constraint(
        "ck_relation_status",
        "relation",
        "status IN ('PROPOSED', 'CONFIRMED', 'REJECTED')",
    )
    op.create_check_constraint(
        "ck_relation_not_self",
        "relation",
        "from_node_id <> to_node_id",
    )
    op.create_foreign_key(
        "fk_relation_from_project",
        "relation",
        "node",
        ["project_id", "from_node_id"],
        ["project_id", "id"],
    )
    op.create_foreign_key(
        "fk_relation_to_project",
        "relation",
        "node",
        ["project_id", "to_node_id"],
        ["project_id", "id"],
    )

    op.create_check_constraint(
        "ck_node_embedding_status",
        "node_embedding",
        "status IN ('PENDING', 'READY', 'STALE', 'FAILED')",
    )
    op.create_check_constraint(
        "ck_node_embedding_dimension",
        "node_embedding",
        "dimension = 1536",
    )


def downgrade() -> None:
    if _is_sqlite():
        return

    op.drop_constraint(
        "ck_node_embedding_dimension",
        "node_embedding",
        type_="check",
    )
    op.drop_constraint(
        "ck_node_embedding_status",
        "node_embedding",
        type_="check",
    )
    op.drop_constraint(
        "fk_analysis_job_node_project",
        "analysis_job",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_merge_history_target_project",
        "node_merge_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_merge_history_source_project",
        "node_merge_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_analysis_candidate_target_project",
        "analysis_candidate",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_analysis_candidate_source_project",
        "analysis_candidate",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_b_model_result_target_project",
        "b_model_result",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_b_model_result_source_project",
        "b_model_result",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_relation_to_project",
        "relation",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_relation_from_project",
        "relation",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_relation_not_self",
        "relation",
        type_="check",
    )
    op.drop_constraint(
        "ck_relation_status",
        "relation",
        type_="check",
    )
    op.drop_constraint(
        "ck_relation_type",
        "relation",
        type_="check",
    )
    op.drop_constraint(
        "fk_node_merged_into_project",
        "node",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_node_parent_project",
        "node",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_node_not_self_merge",
        "node",
        type_="check",
    )
    op.drop_constraint(
        "ck_node_not_self_parent",
        "node",
        type_="check",
    )
    op.drop_constraint(
        "ck_node_merge_shape",
        "node",
        type_="check",
    )
    op.drop_constraint(
        "ck_node_lifecycle_by_type",
        "node",
        type_="check",
    )
    op.drop_constraint(
        "ck_node_graph_state",
        "node",
        type_="check",
    )
    op.drop_constraint("ck_node_type", "node", type_="check")
    op.drop_constraint(
        "uq_node_project_id",
        "node",
        type_="unique",
    )
