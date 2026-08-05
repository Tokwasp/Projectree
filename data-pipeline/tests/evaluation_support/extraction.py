"""Deterministic, content-free pilot case extraction."""

from __future__ import annotations

from sqlalchemy import select

from data_pipeline.storage import Node

from .contracts import EvaluationCase, LabelStatus

_TYPE_QUOTAS = {"DECISION": 15, "ACTION": 20, "ISSUE": 10}


def extract_pilot_cases(
    session,
    *,
    project_id: str,
    limit: int = 45,
) -> list[EvaluationCase]:
    if not project_id.strip():
        raise ValueError("project_id must not be empty")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")

    selected: list[Node] = []
    selected_ids = set()
    for node_type, quota in _TYPE_QUOTAS.items():
        rows = session.execute(
            select(Node)
            .where(
                Node.project_id == project_id,
                Node.node_type == node_type,
                Node.graph_state.in_(("ACTIVE", "UNATTACHED")),
                Node.merged_into_node_id.is_(None),
            )
            .order_by(Node.id.asc())
            .limit(min(quota, limit - len(selected)))
        ).scalars()
        for row in rows:
            selected.append(row)
            selected_ids.add(row.id)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        rows = session.execute(
            select(Node)
            .where(
                Node.project_id == project_id,
                Node.graph_state.in_(("ACTIVE", "UNATTACHED")),
                Node.merged_into_node_id.is_(None),
                Node.id.not_in(selected_ids) if selected_ids else True,
            )
            .order_by(Node.id.asc())
            .limit(limit - len(selected))
        ).scalars()
        selected.extend(rows)

    return [
        EvaluationCase(
            caseId=f"pilot-{index:03d}",
            projectId=project_id,
            sourceNodeId=node.id,
            sourceNodeType=node.node_type,
            labelStatus=LabelStatus.UNREVIEWED,
        )
        for index, node in enumerate(selected, start=1)
    ]


__all__ = ["extract_pilot_cases"]
