"""MERGE and LINK retrieval share a Category boundary but differ on type.

Category is a Graph partition, not a display tag: the same feature in another
Category is a separate Node, so neither MERGE nor a parent LINK may cross it.
The two searches still differ on node_type — MERGE needs the same type, LINK
needs a legal parent type.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from data_pipeline.config import load_settings
from data_pipeline.pipeline.revisions import (
    create_node_revision,
    user_assertion_evidence,
)
from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
from data_pipeline.retrieval.search import (
    search_link_candidates,
    search_merge_candidates,
)
from data_pipeline.storage import Node, NodeEmbedding

PROJECT = "proj-policy"
OTHER_PROJECT = "proj-other"


def _settings():
    load_settings.cache_clear()
    return load_settings().retrieval


def _vector(lead: float = 1.0) -> list[float]:
    dim = _settings().embedding_dim
    return [lead, *([0.0] * (dim - 1))]


def _node(
    session,
    *,
    item: str,
    node_type: str = "DECISION",
    category: str = "BACKEND",
    graph_state: str = "ACTIVE",
    project_id: str = PROJECT,
    embedded: bool = True,
    embedding_version: str | None = None,
    embedding_status: str = "READY",
    merged_into=None,
) -> Node:
    node = Node(
        project_id=project_id,
        source_meeting_id="m-policy",
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
    if embedded:
        settings = _settings()
        session.add(
            NodeEmbedding(
                node_id=node.id,
                embedding_version=embedding_version or EMBEDDING_CONTRACT_VERSION,
                embedding_model=settings.embedding_model,
                dimension=settings.embedding_dim,
                embedded_text_hash=f"hash-{item}",
                embedding=_vector(),
                status=embedding_status,
                embedded_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
    return node


def _merge_search(session, source, *, category=None, node_type=None):
    settings = _settings()
    return search_merge_candidates(
        session,
        project_id=PROJECT,
        source_node_id=source.id,
        embedding=_vector(),
        embedding_model=settings.embedding_model,
        embedding_version=EMBEDDING_CONTRACT_VERSION,
        embedding_dimension=settings.embedding_dim,
        category=category or source.category,
        node_type=node_type or source.node_type,
        top_k=10,
        min_similarity=None,
    )


def _link_search(session, source, *, parent_node_type="DECISION", category=None):
    settings = _settings()
    return search_link_candidates(
        session,
        project_id=PROJECT,
        source_node_id=source.id,
        embedding=_vector(),
        embedding_model=settings.embedding_model,
        embedding_version=EMBEDDING_CONTRACT_VERSION,
        embedding_dimension=settings.embedding_dim,
        category=category or source.category,
        parent_node_type=parent_node_type,
        top_k=10,
        min_similarity=None,
    )


def _ids(rows) -> set:
    return {row.target_node_id for row in rows}


# ------------------------------------------------------------ MERGE policy ---


def test_merge_includes_same_project_category_type_active_canonical(
    session_factory,
) -> None:
    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        target = _node(session, item="tgt")
        assert target.id in _ids(_merge_search(session, source))


def test_merge_excludes_a_different_category(session_factory) -> None:
    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        other = _node(session, item="tgt-infra", category="INFRA")
        assert other.id not in _ids(_merge_search(session, source))


def test_merge_excludes_a_different_node_type(session_factory) -> None:
    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        action = _node(session, item="tgt-action", node_type="ACTION")
        assert action.id not in _ids(_merge_search(session, source))


def test_merge_excludes_another_project(session_factory) -> None:
    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        foreign = _node(session, item="tgt-foreign", project_id=OTHER_PROJECT)
        assert foreign.id not in _ids(_merge_search(session, source))


def test_merge_excludes_an_unattached_target(session_factory) -> None:
    """Only an ACTIVE canonical Node may absorb another."""

    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        pending = _node(session, item="tgt-unattached", graph_state="UNATTACHED")
        assert pending.id not in _ids(_merge_search(session, source))


def test_merge_excludes_a_merged_non_canonical_target(session_factory) -> None:
    with session_factory() as session:
        canonical = _node(session, item="canonical")
        source = _node(session, item="src", graph_state="UNATTACHED")
        absorbed = _node(
            session,
            item="tgt-merged",
            graph_state="MERGED",
            merged_into=canonical.id,
        )
        found = _ids(_merge_search(session, source))
        assert absorbed.id not in found
        assert canonical.id in found


def test_merge_excludes_v1_embeddings(session_factory) -> None:
    """v1 and v2 vectors must never share a candidate set."""

    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        legacy = _node(session, item="tgt-v1", embedding_version="v1")
        assert legacy.id not in _ids(_merge_search(session, source))


def test_merge_excludes_stale_embeddings(session_factory) -> None:
    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        stale = _node(session, item="tgt-stale", embedding_status="STALE")
        assert stale.id not in _ids(_merge_search(session, source))


def test_merge_excludes_nodes_without_an_embedding(session_factory) -> None:
    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        bare = _node(session, item="tgt-bare", embedded=False)
        assert bare.id not in _ids(_merge_search(session, source))


def test_merge_never_returns_the_source_itself(session_factory) -> None:
    with session_factory() as session:
        source = _node(session, item="src", graph_state="UNATTACHED")
        _node(session, item="tgt")
        assert source.id not in _ids(_merge_search(session, source))


# ------------------------------------------------------------- LINK policy ---


def test_link_excludes_a_cross_category_parent(session_factory) -> None:
    """§3.4: Category is a Graph partition, so a parent may not cross it."""

    with session_factory() as session:
        action = _node(
            session,
            item="action",
            node_type="ACTION",
            category="BACKEND",
            graph_state="UNATTACHED",
        )
        infra_parent = _node(session, item="parent-infra", category="INFRA")
        same_cat_parent = _node(session, item="parent-backend", category="BACKEND")

        found = _ids(_link_search(session, action))
        assert infra_parent.id not in found
        assert same_cat_parent.id in found


def test_link_returns_only_the_requested_parent_type(session_factory) -> None:
    with session_factory() as session:
        action = _node(
            session, item="action", node_type="ACTION", graph_state="UNATTACHED"
        )
        decision = _node(session, item="parent-decision")
        other_action = _node(session, item="other-action", node_type="ACTION")

        found = _ids(_link_search(session, action, parent_node_type="DECISION"))
        assert decision.id in found
        assert other_action.id not in found


def test_link_excludes_another_project(session_factory) -> None:
    with session_factory() as session:
        action = _node(
            session, item="action", node_type="ACTION", graph_state="UNATTACHED"
        )
        foreign = _node(session, item="foreign", project_id=OTHER_PROJECT)
        assert foreign.id not in _ids(_link_search(session, action))


def test_link_excludes_merged_and_unattached_parents(session_factory) -> None:
    with session_factory() as session:
        canonical = _node(session, item="canonical")
        action = _node(
            session, item="action", node_type="ACTION", graph_state="UNATTACHED"
        )
        merged = _node(
            session,
            item="merged-parent",
            graph_state="MERGED",
            merged_into=canonical.id,
        )
        unattached = _node(
            session, item="unattached-parent", graph_state="UNATTACHED"
        )

        found = _ids(_link_search(session, action))
        assert merged.id not in found
        assert unattached.id not in found
        assert canonical.id in found


# ------------------------------------------- category projection invariant ---


def test_node_category_projection_tracks_the_current_revision(
    session_factory,
) -> None:
    """MERGE search filters on NodeRevision.category.

    The Node.category projection must stay in sync, otherwise a stale
    projection could silently widen or narrow the MERGE candidate set.
    """

    from data_pipeline.storage import NodeRevision

    with session_factory() as session:
        node = _node(session, item="proj", category="BACKEND")
        create_node_revision(
            session,
            node=node,
            title=node.title,
            content=node.content,
            node_type=node.node_type,
            category="INFRA",
            due_date=None,
            created_by_type="USER",
            created_by_id="tester",
            generation_run_id=None,
            evidence_specs=[user_assertion_evidence("proj 근거")],
        )
        session.flush()

        current = session.get(NodeRevision, node.current_revision_id)
        assert current.category == "INFRA"
        assert node.category == "INFRA"  # projection followed the revision


# ------------------------------------------------ gate defense in depth ---


def test_merge_gate_reasons_cover_category_and_state() -> None:
    """§6.4: the gate re-validates even though Retrieval already filtered.

    Retrieval is the first line of defense; if the candidate set and the target
    snapshot ever disagree, the gate must still refuse to fold two Nodes with a
    different category, or absorb into a non-ACTIVE target.
    """

    import pathlib

    source = pathlib.Path(
        "data_pipeline/pipeline/automatic_graph.py"
    ).read_text(encoding="utf-8")
    assert 'item.merge_gate_reason = "MERGE_CATEGORY_MISMATCH"' in source
    assert 'item.merge_gate_reason = "MERGE_TARGET_NOT_ACTIVE"' in source
    assert 'target.category != source.category' in source
    assert 'target.graph_state != "ACTIVE"' in source


def test_merge_search_is_the_only_retrieval_used_by_automatic_graph() -> None:
    """The automatic graph must not fall back to the unscoped search."""

    import pathlib

    source = pathlib.Path(
        "data_pipeline/pipeline/automatic_graph.py"
    ).read_text(encoding="utf-8")
    assert "search_merge_candidates(" in source
    assert "search_similar_nodes(" not in source
