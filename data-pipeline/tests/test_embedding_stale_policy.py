"""Hash-based embedding invalidation.

A Revision is not automatically a re-embedding. Only a change to the canonical
v2 meaning (node_type/title/content/evidence) may move a vector to STALE;
Category-only, parent-only and evidence-reordering edits must keep it READY
so no provider call is ever spent on them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from data_pipeline.config import load_settings
from data_pipeline.pipeline.revisions import (
    create_node_revision,
    reconcile_embedding_status_after_revision,
    user_assertion_evidence,
)
from data_pipeline.retrieval.embedding import (
    load_current_revision_embedding_input,
)
from data_pipeline.storage import Node, NodeEmbedding

PROJECT = "proj-stale"


def _dim() -> int:
    load_settings.cache_clear()
    return load_settings().retrieval.embedding_dim


def _seed_node_with_ready_embedding(session, *, category="BACKEND"):
    """One Node with a current Revision and a READY v2 embedding."""

    node = Node(
        project_id=PROJECT,
        source_meeting_id="m-stale",
        source_item_id=f"item-{category}-{uuid.uuid4().hex[:8]}",
        node_type="ACTION",
        category=category,
        title="RDS 연결을 구성한다",
        content="EC2에서 RDS 연결을 구성한다.",
        graph_state="UNATTACHED",
        analysis_status="PENDING",
        version=1,
        origin_type="USER_CREATED",
        last_actor_type="USER",
        consistency_status="NORMAL",
    )
    session.add(node)
    session.flush()
    create_node_revision(
        session,
        node=node,
        title=node.title,
        content=node.content,
        node_type=node.node_type,
        category=category,
        due_date=None,
        created_by_type="USER",
        created_by_id="tester",
        generation_run_id=None,
        evidence_specs=[user_assertion_evidence("RDS 연결 구성 근거")],
    )
    session.flush()

    settings = load_settings().retrieval
    current = load_current_revision_embedding_input(session, node=node)
    session.add(
        NodeEmbedding(
            node_id=node.id,
            embedding_version=settings.embedding_version,
            embedding_model=settings.embedding_model,
            dimension=settings.embedding_dim,
            embedded_text_hash=current.text_hash,
            embedding=[1.0, *([0.0] * (settings.embedding_dim - 1))],
            status="READY",
            embedded_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
    return node, current.text_hash


def _revise(session, node, **overrides):
    values = {
        "title": node.title,
        "content": node.content,
        "node_type": node.node_type,
        "category": node.category,
        "due_date": node.due_date,
        "evidence_specs": [user_assertion_evidence("RDS 연결 구성 근거")],
    }
    values.update(overrides)
    create_node_revision(
        session,
        node=node,
        created_by_type="USER",
        created_by_id="tester",
        generation_run_id=None,
        **values,
    )
    session.flush()
    return reconcile_embedding_status_after_revision(session, node=node)


def _status(session, node) -> str:
    return session.execute(
        select(NodeEmbedding).where(NodeEmbedding.node_id == node.id)
    ).scalar_one().status


# ------------------------------------------------------- hash unchanged ---


def test_category_only_revision_keeps_the_embedding_ready(session_factory) -> None:
    """The headline v2 guarantee: re-categorising costs no provider call."""

    with session_factory() as session:
        node, before = _seed_node_with_ready_embedding(session)
        result = _revise(session, node, category="INFRA")

        assert node.category == "INFRA"          # metadata did change
        assert result.current_hash == before     # meaning did not
        assert result.reason == "HASH_UNCHANGED"
        assert result.invalidated == 0
        assert result.reembedding_required is False
        assert _status(session, node) == "READY"


def test_parent_only_revision_keeps_the_embedding_ready(session_factory) -> None:
    """§3.6: parent 변경은 의미가 아니므로 재임베딩하지 않는다."""

    with session_factory() as session:
        node, before = _seed_node_with_ready_embedding(session)
        parent = _seed_node_with_ready_embedding(session, category="BACKEND")[0]
        node.parent_id = parent.id
        session.flush()
        result = reconcile_embedding_status_after_revision(session, node=node)

        assert node.parent_id == parent.id       # structure did change
        assert result.current_hash == before     # meaning did not
        assert result.reason == "HASH_UNCHANGED"
        assert result.invalidated == 0
        assert _status(session, node) == "READY"


def test_due_date_only_revision_keeps_the_embedding_ready(session_factory) -> None:
    with session_factory() as session:
        node, before = _seed_node_with_ready_embedding(session)
        result = _revise(session, node, due_date="2026-09-01")

        assert result.current_hash == before
        assert _status(session, node) == "READY"


def test_evidence_reordering_keeps_the_embedding_ready(session_factory) -> None:
    with session_factory() as session:
        node, _ = _seed_node_with_ready_embedding(session)
        specs = [
            user_assertion_evidence("근거 A"),
            user_assertion_evidence("근거 B"),
        ]
        _revise(session, node, evidence_specs=specs)
        hash_after_first = session.execute(
            select(NodeEmbedding).where(NodeEmbedding.node_id == node.id)
        ).scalar_one()
        # Re-point the vector at the new meaning, then reorder only.
        current = load_current_revision_embedding_input(session, node=node)
        hash_after_first.embedded_text_hash = current.text_hash
        hash_after_first.status = "READY"
        session.flush()

        result = _revise(session, node, evidence_specs=list(reversed(specs)))

        assert result.reason == "HASH_UNCHANGED"
        assert _status(session, node) == "READY"


# --------------------------------------------------------- hash changed ---


@pytest.mark.parametrize(
    "override",
    [
        {"title": "제목이 바뀌었다"},
        {"content": "내용이 바뀌었다"},
        {"node_type": "ISSUE"},
        {"evidence_specs": [user_assertion_evidence("완전히 다른 근거")]},
    ],
)
def test_meaning_change_marks_the_embedding_stale(
    session_factory, override: dict
) -> None:
    with session_factory() as session:
        node, before = _seed_node_with_ready_embedding(session)
        result = _revise(session, node, **override)

        assert result.current_hash != before
        assert result.reason == "HASH_CHANGED"
        assert result.invalidated == 1
        assert result.reembedding_required is True
        assert _status(session, node) == "STALE"


def test_added_evidence_marks_the_embedding_stale(session_factory) -> None:
    """Action MERGE folds Evidence into the target - that must re-embed."""

    with session_factory() as session:
        node, before = _seed_node_with_ready_embedding(session)
        result = _revise(
            session,
            node,
            evidence_specs=[
                user_assertion_evidence("RDS 연결 구성 근거"),
                user_assertion_evidence("병합으로 합류한 근거"),
            ],
        )
        assert result.current_hash != before
        assert _status(session, node) == "STALE"


# ------------------------------------------------------------- edge cases ---


def test_reconcile_is_a_no_op_without_a_ready_embedding(session_factory) -> None:
    with session_factory() as session:
        node, _ = _seed_node_with_ready_embedding(session)
        session.execute(
            select(NodeEmbedding).where(NodeEmbedding.node_id == node.id)
        ).scalar_one().status = "STALE"
        session.flush()

        result = reconcile_embedding_status_after_revision(session, node=node)
        assert result.reason == "NO_READY_EMBEDDING"
        assert result.invalidated == 0


def test_unprovable_current_revision_fails_safe_to_stale(session_factory) -> None:
    """If the current Revision cannot be loaded we must not claim READY."""

    with session_factory() as session:
        node, _ = _seed_node_with_ready_embedding(session)
        node.current_revision_id = None
        session.flush()

        result = reconcile_embedding_status_after_revision(session, node=node)
        assert result.reason == "NO_CURRENT_REVISION"
        assert result.invalidated == 1
        assert _status(session, node) == "STALE"


def test_a_stale_row_is_not_resurrected_by_a_matching_hash(session_factory) -> None:
    with session_factory() as session:
        node, _ = _seed_node_with_ready_embedding(session)
        row = session.execute(
            select(NodeEmbedding).where(NodeEmbedding.node_id == node.id)
        ).scalar_one()
        row.status = "STALE"
        session.flush()

        _revise(session, node, category="INFRA")
        assert _status(session, node) == "STALE"
