"""Category is a Graph partition and parent types are a single rule.

§3.2/§3.4 of the remediation contract: the same feature in another Category is
a separate Node. Neither a MERGE nor a parent LINK may cross that boundary, and
the type rule is Decision=root, Action→Decision, Issue→Decision|Action.

These tests exercise the boundary at the two places it has to hold: the
Retrieval scope that builds the B-model's candidate list, and the apply step
that is the last line of defence regardless of which search produced it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from data_pipeline.config import load_settings
from data_pipeline.contracts import allowed_parent_types, is_allowed_parent_type
from data_pipeline.pipeline.revisions import (
    create_node_revision,
    user_assertion_evidence,
)
from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
from data_pipeline.retrieval.search import (
    search_link_candidates,
    search_merge_candidates,
    search_scoped_candidates,
)
from data_pipeline.storage import Node, NodeEmbedding

PROJECT = "proj-partition"
OTHER_PROJECT = "proj-partition-other"


def _settings():
    load_settings.cache_clear()
    return load_settings().retrieval


def _vector() -> list[float]:
    return [1.0, *([0.0] * (_settings().embedding_dim - 1))]


def _node(
    session,
    *,
    item: str,
    node_type: str = "DECISION",
    category: str = "BACKEND",
    graph_state: str = "ACTIVE",
    project_id: str = PROJECT,
    merged_into=None,
) -> Node:
    node = Node(
        project_id=project_id,
        source_meeting_id="m-partition",
        source_item_id=item,
        node_type=node_type,
        category=category,
        title=f"{item} 제목",
        content=f"{item} 내용",
        graph_state=graph_state,
        analysis_status="PENDING",
        version=1,
        origin_type="USER_CREATED",
        last_actor_type="USER",
        consistency_status="NORMAL",
        merged_into_node_id=merged_into,
    )
    session.add(node)
    session.flush()
    create_node_revision(
        session,
        node=node,
        title=node.title,
        content=node.content,
        node_type=node_type,
        category=category,
        due_date=None,
        created_by_type="USER",
        created_by_id="tester",
        generation_run_id=None,
        evidence_specs=[user_assertion_evidence(f"{item} 근거")],
    )
    session.flush()
    settings = _settings()
    session.add(
        NodeEmbedding(
            node_id=node.id,
            embedding_version=EMBEDDING_CONTRACT_VERSION,
            embedding_model=settings.embedding_model,
            dimension=settings.embedding_dim,
            embedded_text_hash=f"hash-{item}",
            embedding=_vector(),
            status="READY",
            embedded_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
    return node


def _common(source):
    settings = _settings()
    return dict(
        project_id=PROJECT,
        source_node_id=source.id,
        embedding=_vector(),
        embedding_model=settings.embedding_model,
        embedding_version=EMBEDDING_CONTRACT_VERSION,
        embedding_dimension=settings.embedding_dim,
        top_k=10,
        min_similarity=None,
    )


def _ids(rows) -> set:
    return {row.target_node_id for row in rows}


# ----------------------------------------------- Category as a partition ---


def test_same_meaning_other_category_is_not_a_merge_candidate(session_factory):
    """The BACKEND/FRONTEND/DESIGN OAuth trio must stay three Nodes."""

    with session_factory() as session:
        backend = _node(
            session,
            item="oauth-backend",
            node_type="ACTION",
            category="BACKEND",
            graph_state="UNATTACHED",
        )
        frontend = _node(
            session, item="oauth-frontend", node_type="ACTION", category="FRONTEND"
        )
        design = _node(
            session, item="oauth-design", node_type="ACTION", category="DESIGN"
        )
        same = _node(
            session, item="oauth-backend-2", node_type="ACTION", category="BACKEND"
        )

        found = _ids(
            search_merge_candidates(
                session,
                category=backend.category,
                node_type=backend.node_type,
                **_common(backend),
            )
        )
        assert frontend.id not in found
        assert design.id not in found
        assert same.id in found


def test_same_meaning_other_category_is_not_a_parent_candidate(session_factory):
    with session_factory() as session:
        action = _node(
            session,
            item="child",
            node_type="ACTION",
            category="BACKEND",
            graph_state="UNATTACHED",
        )
        other = _node(session, item="parent-infra", category="INFRA")
        same = _node(session, item="parent-backend", category="BACKEND")

        found = _ids(
            search_link_candidates(
                session,
                category=action.category,
                parent_node_type="DECISION",
                **_common(action),
            )
        )
        assert other.id not in found
        assert same.id in found


@pytest.mark.parametrize(
    "search",
    ["merge", "link"],
)
def test_another_project_is_never_a_candidate(session_factory, search: str):
    with session_factory() as session:
        source = _node(
            session,
            item="src",
            node_type="ACTION",
            graph_state="UNATTACHED",
        )
        foreign = _node(
            session,
            item="foreign",
            node_type="ACTION" if search == "merge" else "DECISION",
            project_id=OTHER_PROJECT,
        )
        if search == "merge":
            rows = search_merge_candidates(
                session,
                category=source.category,
                node_type=source.node_type,
                **_common(source),
            )
        else:
            rows = search_link_candidates(
                session,
                category=source.category,
                parent_node_type="DECISION",
                **_common(source),
            )
        assert foreign.id not in _ids(rows)


# -------------------------------------- the single scoped candidate list ---


def test_scoped_search_gives_the_b_model_only_reachable_candidates(session_factory):
    """§5.2: no project/category/type/state violation may reach the B model."""

    with session_factory() as session:
        source = _node(
            session,
            item="src",
            node_type="ACTION",
            category="BACKEND",
            graph_state="UNATTACHED",
        )
        merge_target = _node(
            session, item="merge-ok", node_type="ACTION", category="BACKEND"
        )
        parent_target = _node(
            session, item="parent-ok", node_type="DECISION", category="BACKEND"
        )
        wrong_category = _node(
            session, item="wrong-cat", node_type="ACTION", category="INFRA"
        )
        wrong_type = _node(
            session, item="wrong-type", node_type="ISSUE", category="BACKEND"
        )
        not_active = _node(
            session,
            item="not-active",
            node_type="ACTION",
            category="BACKEND",
            graph_state="UNATTACHED",
        )
        foreign = _node(
            session,
            item="foreign",
            node_type="ACTION",
            category="BACKEND",
            project_id=OTHER_PROJECT,
        )

        found = _ids(
            search_scoped_candidates(
                session,
                category=source.category,
                node_types=(
                    source.node_type,
                    *sorted(allowed_parent_types(source.node_type)),
                ),
                **_common(source),
            )
        )
        assert merge_target.id in found      # MERGE reach
        assert parent_target.id in found     # LINK reach
        assert wrong_category.id not in found
        assert wrong_type.id not in found    # ISSUE is neither same-type nor parent
        assert not_active.id not in found
        assert foreign.id not in found


def test_scoped_search_for_an_issue_reaches_both_parent_types(session_factory):
    with session_factory() as session:
        issue = _node(
            session,
            item="issue-src",
            node_type="ISSUE",
            category="AI",
            graph_state="UNATTACHED",
        )
        decision_parent = _node(
            session, item="d-parent", node_type="DECISION", category="AI"
        )
        action_parent = _node(
            session, item="a-parent", node_type="ACTION", category="AI"
        )
        issue_peer = _node(
            session, item="i-peer", node_type="ISSUE", category="AI"
        )

        found = _ids(
            search_scoped_candidates(
                session,
                category=issue.category,
                node_types=(
                    issue.node_type,
                    *sorted(allowed_parent_types(issue.node_type)),
                ),
                **_common(issue),
            )
        )
        assert decision_parent.id in found   # ISSUE -> DECISION
        assert action_parent.id in found     # ISSUE -> ACTION
        assert issue_peer.id in found        # same type is a MERGE candidate


def test_scoped_search_for_a_decision_has_no_parent_reach(session_factory):
    """Decision is root, so its candidate set is same-type only."""

    with session_factory() as session:
        decision = _node(
            session,
            item="d-src",
            node_type="DECISION",
            category="PLANNING",
            graph_state="UNATTACHED",
        )
        peer = _node(session, item="d-peer", node_type="DECISION", category="PLANNING")
        action = _node(session, item="a", node_type="ACTION", category="PLANNING")

        assert allowed_parent_types("DECISION") == frozenset()
        found = _ids(
            search_scoped_candidates(
                session,
                category=decision.category,
                node_types=(
                    decision.node_type,
                    *sorted(allowed_parent_types(decision.node_type)),
                ),
                **_common(decision),
            )
        )
        assert peer.id in found
        assert action.id not in found


# ------------------------------------------------------- parent type rule ---


@pytest.mark.parametrize(
    ("child", "parent", "allowed"),
    [
        ("DECISION", None, True),
        ("DECISION", "DECISION", False),
        ("DECISION", "ACTION", False),
        ("ACTION", "DECISION", True),
        ("ACTION", "ACTION", False),
        ("ACTION", "ISSUE", False),
        ("ACTION", None, False),
        ("ISSUE", "DECISION", True),
        ("ISSUE", "ACTION", True),
        ("ISSUE", "ISSUE", False),
        ("ISSUE", None, False),
    ],
)
def test_parent_type_matrix(child: str, parent: str | None, allowed: bool):
    assert is_allowed_parent_type(child, parent) is allowed
