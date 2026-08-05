from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from data_pipeline.api.app import create_app
from data_pipeline.api.dependencies import get_session_factory
from data_pipeline.jobs.outbox import _to_message
from data_pipeline.storage import Node, OutboxEvent, ProjectGraphState, Relation


PROJECT = "1001"
HEADERS = {
    "X-Project-Id": PROJECT,
    "X-Actor-Id": "user-77",
    "X-Request-Id": "p0-contract-test",
}


@pytest.fixture()
def client(session_factory):
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create(client, *, node_type: str, category: str, title: str) -> dict:
    response = client.post(
        "/api/v1/nodes",
        headers=HEADERS,
        json={
            "nodeType": node_type,
            "category": category,
            "title": title,
            "evidenceAssertion": f"evidence for {title}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _attach(client, child: dict, parent: dict) -> dict:
    response = client.post(
        "/api/v1/relations",
        headers=HEADERS,
        json={
            "fromNodeId": child["nodeId"],
            "toNodeId": parent["nodeId"],
            "relationType": "ATTACHED_TO",
            "fromExpectedVersion": child["version"],
            "toExpectedVersion": parent["version"],
        },
    )
    assert response.status_code == 200, response.text
    child["version"] += 1
    child["graphState"] = "ACTIVE"
    return response.json()


def test_decision_category_change_cascades_active_subtree_once(
    client,
    session_factory,
):
    root = _create(client, node_type="DECISION", category="BACKEND", title="root")
    action = _create(client, node_type="ACTION", category="BACKEND", title="action")
    _attach(client, action, root)
    issue = _create(client, node_type="ISSUE", category="BACKEND", title="issue")
    _attach(client, issue, action)

    with session_factory() as session:
        before = session.get(ProjectGraphState, PROJECT).graph_version

    changed = client.patch(
        f"/api/v1/nodes/{root['nodeId']}",
        headers=HEADERS,
        json={"expectedVersion": root["version"], "category": "INFRA"},
    )
    assert changed.status_code == 200, changed.text

    with session_factory() as session:
        rows = list(
            session.execute(
                select(Node).where(
                    Node.id.in_(
                        [
                            uuid.UUID(root["nodeId"]),
                            uuid.UUID(action["nodeId"]),
                            uuid.UUID(issue["nodeId"]),
                        ]
                    )
                )
            ).scalars()
        )
        assert {row.category for row in rows} == {"INFRA"}
        assert all(row.graph_state == "ACTIVE" for row in rows)
        assert session.get(ProjectGraphState, PROJECT).graph_version == before + 1
        event = session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.project_id == PROJECT,
                OutboxEvent.event_type == "PROJECT_GRAPH_CHANGED",
            )
            .order_by(OutboxEvent.created_at.desc())
            .limit(1)
        ).scalar_one()
        assert len(event.payload["upsertedNodes"]) == 3
        assert event.payload["deletedNodes"] == []


def test_action_category_change_requires_valid_parent_and_rolls_back(
    client,
    session_factory,
):
    old_parent = _create(
        client, node_type="DECISION", category="BACKEND", title="old-parent"
    )
    action = _create(client, node_type="ACTION", category="BACKEND", title="move-me")
    _attach(client, action, old_parent)
    child = _create(client, node_type="ISSUE", category="BACKEND", title="child")
    _attach(client, child, action)
    new_parent = _create(
        client, node_type="DECISION", category="INFRA", title="new-parent"
    )

    rejected = client.patch(
        f"/api/v1/nodes/{action['nodeId']}",
        headers=HEADERS,
        json={"expectedVersion": action["version"], "category": "INFRA"},
    )
    assert rejected.status_code == 422
    assert "CATEGORY_REPARENT_REQUIRED" in rejected.text
    with session_factory() as session:
        unchanged = session.get(Node, uuid.UUID(action["nodeId"]))
        assert unchanged.category == "BACKEND"
        assert unchanged.version == action["version"]

    moved = client.patch(
        f"/api/v1/nodes/{action['nodeId']}",
        headers=HEADERS,
        json={
            "expectedVersion": action["version"],
            "category": "INFRA",
            "newParentNodeId": new_parent["nodeId"],
        },
    )
    assert moved.status_code == 200, moved.text
    with session_factory() as session:
        action_row = session.get(Node, uuid.UUID(action["nodeId"]))
        child_row = session.get(Node, uuid.UUID(child["nodeId"]))
        assert action_row.category == child_row.category == "INFRA"
        assert action_row.parent_id == uuid.UUID(new_parent["nodeId"])
        assert action_row.graph_state == child_row.graph_state == "ACTIVE"
        attached = session.execute(
            select(Relation).where(
                Relation.project_id == PROJECT,
                Relation.from_node_id == action_row.id,
                Relation.relation_type == "ATTACHED_TO",
                Relation.status == "CONFIRMED",
                Relation.valid_to.is_(None),
            )
        ).scalar_one()
        assert attached.to_node_id == uuid.UUID(new_parent["nodeId"])


def test_soft_delete_rejects_a_node_with_structural_children(
    client,
    session_factory,
):
    parent = _create(client, node_type="DECISION", category="BACKEND", title="delete")
    child = _create(client, node_type="ACTION", category="BACKEND", title="survivor")
    _attach(client, child, parent)
    grandchild = _create(client, node_type="ISSUE", category="BACKEND", title="nested")
    _attach(client, grandchild, child)

    deleted = client.request(
        "DELETE",
        f"/api/v1/nodes/{parent['nodeId']}",
        headers=HEADERS,
        json={"expectedVersion": parent["version"]},
    )
    assert deleted.status_code == 409, deleted.text
    assert deleted.json()["error"]["code"] == "NODE_HAS_CHILDREN"

    with session_factory() as session:
        parent_row = session.get(Node, uuid.UUID(parent["nodeId"]))
        child_row = session.get(Node, uuid.UUID(child["nodeId"]))
        assert parent_row.deleted_at is None
        assert child_row.parent_id == parent_row.id
        assert child_row.version == child["version"]
