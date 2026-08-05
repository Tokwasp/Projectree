from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from data_pipeline.api.app import create_app
from data_pipeline.api.dependencies import get_session_factory
from data_pipeline.jobs.outbox import OutboxMessage
from data_pipeline.jobs.outbox import _to_message
from data_pipeline.pipeline.event_contract import (
    canonical_storage_identifier,
    public_identifier,
    stage_project_graph_changed,
)
from data_pipeline.storage import Node, ProjectGraphState


FIXTURES = Path(__file__).parents[1] / "docs" / "contracts" / "fixtures" / "event-v1"
EVENT_FIXTURES = (
    "graph-create-link.json",
    "graph-unattached.json",
    "graph-merge.json",
    "graph-soft-delete.json",
    "meeting-summary-ready.json",
    "analysis-processing.json",
    "analysis-succeeded.json",
    "analysis-failed.json",
    "category-cascade.json",
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_event_v1_golden_fixtures_equal_actual_outbox_serializer():
    for name in EVENT_FIXTURES:
        expected = _load(name)
        message = OutboxMessage(
            event_id=expected["eventId"],
            event_type=expected["eventType"],
            aggregate_type="fixture",
            aggregate_id="fixture",
            project_id=str(expected["projectId"]),
            schema_version="1",
            occurred_at=datetime.fromisoformat(
                expected["occurredAt"].replace("Z", "+00:00")
            ),
            payload=expected["payload"],
        )
        assert message.as_dict() == expected, name
        assert message.as_dict()["occurredAt"].endswith("Z")
        assert "startMs" not in json.dumps(message.as_dict(), ensure_ascii=False)
        if expected["eventType"] == "PROJECT_GRAPH_CHANGED":
            assert "upsertedNodes" in expected["payload"]
            assert "deletedNodes" in expected["payload"]


def test_graph_snapshot_golden_fixture_equals_actual_api(session_factory):
    expected = _load("graph-snapshot.json")
    with session_factory() as session:
        session.add(ProjectGraphState(project_id="10", graph_version=25))
        session.commit()

    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as client:
        response = client.get("/internal/projects/10/graph-snapshot")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == expected


def test_graph_create_link_fixture_equals_actual_staged_event(session_factory):
    expected = _load("graph-create-link.json")
    fixed = datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc)
    decision = Node(
        id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        project_id="10",
        source_meeting_id="501",
        source_item_id="d1",
        node_type="DECISION",
        category="BACKEND",
        title="Choose PostgreSQL",
        content="Canonical database",
        graph_state="ACTIVE",
        analysis_status="PENDING",
        version=1,
        origin_type="LLM_GENERATED",
        last_actor_type="SYSTEM",
        consistency_status="NORMAL",
        created_at=fixed,
        updated_at=fixed,
    )
    action = Node(
        id=uuid.UUID("10000000-0000-0000-0000-000000000002"),
        project_id="10",
        source_meeting_id="501",
        source_item_id="a1",
        node_type="ACTION",
        category="BACKEND",
        title="Create migration",
        content="Add schema",
        parent_id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        graph_state="ACTIVE",
        analysis_status="PENDING",
        version=2,
        origin_type="LLM_GENERATED",
        last_actor_type="SYSTEM",
        consistency_status="NORMAL",
        created_at=fixed,
        updated_at=fixed,
    )
    with session_factory() as session:
        session.add(ProjectGraphState(project_id="10", graph_version=19))
        session.add(decision)
        session.flush()
        session.add(action)
        session.flush()
        event, version = stage_project_graph_changed(
            session,
            project_id="10",
            upserted_nodes=[action, decision],
        )
        assert version == 20
        event.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        event.created_at = fixed
        session.flush()
        actual = _to_message(event).as_dict()
        assert actual == expected


def test_signed_long_id_boundary_and_external_identifier_coexistence():
    assert canonical_storage_identifier(2**63 - 1, field="projectId") == str(2**63 - 1)
    assert canonical_storage_identifier(str(-(2**63)), field="projectId") == str(-(2**63))
    assert canonical_storage_identifier("room-alpha-001", field="meetingId") == "room-alpha-001"
    assert public_identifier(str(2**63 - 1)) == 2**63 - 1
    assert public_identifier("room-alpha-001") == "room-alpha-001"
    for invalid in (2**63, -(2**63) - 1, "01", "+1", "1.0", "1e3", " 1"):
        try:
            canonical_storage_identifier(invalid, field="projectId")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid numeric identifier accepted: {invalid!r}")
