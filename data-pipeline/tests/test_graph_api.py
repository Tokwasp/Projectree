from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from data_pipeline.api.app import create_app
from data_pipeline.api.dependencies import get_session_factory
from data_pipeline.storage import Evidence, Node, NodeRevision

HEADERS = {
    "X-Project-Id": "graph-api-project",
    "X-Actor-Id": "spring-user",
    "X-Request-Id": "spring-request-graph-1",
}


@pytest.fixture()
def client(session_factory):
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_user_node_create_list_and_edit_use_revision_evidence(
    client,
    session_factory,
):
    created = client.post(
        "/api/v1/nodes",
        headers=HEADERS,
        json={
            "nodeType": "DECISION",
            "category": "BACKEND",
            "title": "사용자 결정",
            "content": "처음 본문",
            "evidenceAssertion": "사용자가 직접 확인한 결정",
        },
    )
    assert created.status_code == 200, created.text
    node_id = created.json()["nodeId"]
    assert created.json()["version"] == 1

    listed = client.get(
        "/api/v1/nodes?graphState=ACTIVE,UNATTACHED",
        headers=HEADERS,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["nodes"][0]["evidence"][0]["sourceType"] == "USER_ASSERTION"

    edited = client.patch(
        f"/api/v1/nodes/{node_id}",
        headers=HEADERS,
        json={
            "expectedVersion": 1,
            "title": "사용자 결정 수정",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2

    with session_factory() as session:
        node = session.execute(
            select(Node).where(Node.id == uuid.UUID(node_id))
        ).scalar_one()
        assert node.title == "사용자 결정 수정"
        revisions = list(
            session.execute(
                select(NodeRevision)
                .where(NodeRevision.node_id == node.id)
                .order_by(NodeRevision.version)
            ).scalars()
        )
        assert [row.version for row in revisions] == [1, 2]
        assert session.execute(select(Evidence)).scalars().one().source_type == "USER_ASSERTION"


def test_graph_api_project_scope_hides_other_project(client, session_factory):
    created = client.post(
        "/api/v1/nodes",
        headers=HEADERS,
        json={
            "nodeType": "DECISION",
            "category": "BACKEND",
            "title": "프로젝트 A",
            "evidenceAssertion": "프로젝트 A 근거",
        },
    )
    node_id = created.json()["nodeId"]
    other = client.get(
        f"/api/v1/nodes/{node_id}",
        headers={
            "X-Project-Id": "graph-api-project-b",
            "X-Actor-Id": "other-user",
        },
    )
    assert other.status_code == 422
    with session_factory() as session:
        assert session.execute(
            select(Node).where(Node.id == uuid.UUID(node_id))
        ).scalar_one().title == "프로젝트 A"


def test_user_type_change_reconciles_structural_parent_state(
    client,
    session_factory,
):
    created = client.post(
        "/api/v1/nodes",
        headers=HEADERS,
        json={
            "nodeType": "DECISION",
            "category": "BACKEND",
            "title": "유형 변경 노드",
            "evidenceAssertion": "유형 변경 사용자 근거",
        },
    )
    node_id = created.json()["nodeId"]
    to_action = client.patch(
        f"/api/v1/nodes/{node_id}",
        headers=HEADERS,
        json={"expectedVersion": 1, "nodeType": "ACTION"},
    )
    assert to_action.status_code == 200, to_action.text
    assert to_action.json()["graphState"] == "UNATTACHED"
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        assert node.parent_id is None
        assert node.consistency_status == "NEEDS_ATTENTION"

    to_decision = client.patch(
        f"/api/v1/nodes/{node_id}",
        headers=HEADERS,
        json={"expectedVersion": 2, "nodeType": "DECISION"},
    )
    assert to_decision.status_code == 200, to_decision.text
    assert to_decision.json()["graphState"] == "ACTIVE"
    with session_factory() as session:
        node = session.get(Node, uuid.UUID(node_id))
        assert node.parent_id is None
