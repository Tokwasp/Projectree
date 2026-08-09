from __future__ import annotations

from sqlalchemy import select

from data_pipeline.api.graph_services import create_relation
from data_pipeline.pipeline.errors import NodeHasChildrenError
from data_pipeline.pipeline.user_graph import (
    create_user_node,
    delete_node,
    user_merge_nodes,
)
from data_pipeline.storage import Node, ProjectGraphState


def _node(session_factory, *, project: str, node_type: str, title: str):
    return create_user_node(
        session_factory,
        project_id=project,
        actor_id="tester",
        request_id=title,
        node_type=node_type,
        category="BACKEND",
        title=title,
        content=title,
        due_date=None,
        evidence_assertion=f"evidence for {title}",
        external_meeting_id="USER_CREATED",
    )


def test_delete_rejects_representative_with_structural_children(session_factory):
    project = "leaf-delete-child"
    parent = _node(
        session_factory, project=project, node_type="DECISION", title="parent"
    )
    child = _node(
        session_factory, project=project, node_type="ACTION", title="child"
    )
    create_relation(
        session_factory,
        project_id=project,
        actor_id="tester",
        from_node_id=child.node_id,
        to_node_id=parent.node_id,
        relation_type="ATTACHED_TO",
        from_expected_version=child.version,
        to_expected_version=parent.version,
    )
    with session_factory() as session:
        actual_version = session.get(Node, parent.node_id).version
    try:
        delete_node(
            session_factory,
            project_id=project,
            node_id=parent.node_id,
            actor_id="tester",
            request_id="delete-parent",
            expected_version=actual_version,
        )
        raise AssertionError("delete should reject a non-leaf")
    except NodeHasChildrenError as exc:
        assert str(exc) == "NODE_HAS_CHILDREN"
    with session_factory() as session:
        assert session.get(Node, parent.node_id).graph_state == "ACTIVE"
        assert session.get(Node, child.node_id).graph_state == "ACTIVE"


def test_delete_representative_cascades_connected_merged_sources_once(session_factory):
    project = "leaf-delete-merged"
    source = _node(
        session_factory, project=project, node_type="DECISION", title="source"
    )
    target = _node(
        session_factory, project=project, node_type="DECISION", title="target"
    )
    user_merge_nodes(
        session_factory,
        project_id=project,
        source_node_id=source.node_id,
        target_node_id=target.node_id,
        source_expected_version=source.version,
        target_expected_version=target.version,
        actor_id="tester",
        reason="legacy setup",
    )
    with session_factory() as session:
        target_row = session.get(Node, target.node_id)
        before_graph_version = session.get(ProjectGraphState, project).graph_version
        target_version = target_row.version
    result = delete_node(
        session_factory,
        project_id=project,
        node_id=target.node_id,
        actor_id="tester",
        request_id="delete-representative",
        expected_version=target_version,
    )
    assert result.graph_state == "DELETED"
    with session_factory() as session:
        source_row = session.get(Node, source.node_id)
        target_row = session.get(Node, target.node_id)
        assert source_row.graph_state == "DELETED"
        assert source_row.deleted_at is not None
        assert source_row.merged_into_node_id is None
        assert target_row.graph_state == "DELETED"
        assert target_row.deleted_at is not None
        assert (
            session.get(ProjectGraphState, project).graph_version
            == before_graph_version + 1
        )
